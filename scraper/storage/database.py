"""
Módulo de base de datos SQLite para persistencia de inmuebles.
Implementa lógica de upsert y trazabilidad de precios.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from contextlib import contextmanager
import structlog

from .models import PropertyModel, PriceHistoryModel, AlertSentModel, ScrapingLogModel
from ..parsers.property_parser import Property

logger = structlog.get_logger(__name__)


class Database:
    """
    Gestor de base de datos SQLite para el scraper de inmuebles.
    Maneja conexiones, esquemas y operaciones CRUD.
    """
    
    def __init__(self, db_path: Path):
        """
        Inicializa la conexión a la base de datos.
        
        Args:
            db_path: Ruta al archivo de base de datos SQLite
        """
        self.db_path = db_path
        self._ensure_directory()
        self._initialize_schema()
        logger.info("database_initialized", path=str(db_path))
    
    def _ensure_directory(self):
        """Asegura que el directorio de la base de datos existe."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def _get_connection(self):
        """Context manager para conexiones a la base de datos."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error("database_error", error=str(e))
            raise
        finally:
            conn.close()
    
    def _initialize_schema(self):
        """Crea las tablas si no existen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla principal de propiedades
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_externo TEXT NOT NULL,
                    source TEXT NOT NULL,
                    region TEXT DEFAULT 'venezuela',
                    titulo TEXT,
                    precio REAL,
                    moneda TEXT DEFAULT 'USD',
                    ubicacion TEXT,
                    tipo_inmueble TEXT,
                    url TEXT,
                    descripcion TEXT,
                    metros_cuadrados REAL,
                    habitaciones INTEGER,
                    banos INTEGER,
                    estacionamientos INTEGER,
                    fecha_primera_vista DATETIME DEFAULT CURRENT_TIMESTAMP,
                    fecha_ultima_vista DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    is_opportunity BOOLEAN DEFAULT 0,
                    UNIQUE(id_externo, source)
                )
            ''')

            # Migración: agregar columna region en bases de datos existentes
            cursor.execute("PRAGMA table_info(properties)")
            columns = {row[1] for row in cursor.fetchall()}
            if 'region' not in columns:
                cursor.execute(
                    "ALTER TABLE properties ADD COLUMN region TEXT DEFAULT 'venezuela'"
                )
                cursor.execute(
                    "UPDATE properties SET region = 'venezuela' WHERE region IS NULL"
                )
                logger.info("migration_added_region_column")

            cursor.execute("PRAGMA table_info(properties)")
            columns = {row[1] for row in cursor.fetchall()}
            geo_columns = {
                'estado_provincia': "TEXT DEFAULT ''",
                'localidad': "TEXT DEFAULT ''",
                'sub_localidad': "TEXT DEFAULT ''",
            }
            for col_name, col_def in geo_columns.items():
                if col_name not in columns:
                    cursor.execute(f"ALTER TABLE properties ADD COLUMN {col_name} {col_def}")
                    logger.info("migration_added_geo_column", column=col_name)
                    columns.add(col_name)

            if 'operacion' not in columns:
                cursor.execute("ALTER TABLE properties ADD COLUMN operacion TEXT DEFAULT 'venta'")
                cursor.execute(
                    "UPDATE properties SET operacion = 'venta' WHERE operacion IS NULL OR operacion = ''"
                )
                logger.info("migration_added_operacion_column")
                columns.add('operacion')

            cursor.execute('DROP INDEX IF EXISTS idx_properties_unique')
            cursor.execute(
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_unique '
                'ON properties(id_externo, source, region, operacion)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_properties_operacion ON properties(operacion)'
            )

            # Índices (después de asegurar que las columnas existen)
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_properties_source ON properties(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_properties_tipo ON properties(tipo_inmueble)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_properties_precio ON properties(precio)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_properties_opportunity ON properties(is_opportunity)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_properties_region ON properties(region)')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_properties_estado ON properties(estado_provincia)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_properties_sub_localidad ON properties(sub_localidad)'
            )
            
            # Historial de precios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id INTEGER NOT NULL,
                    precio REAL NOT NULL,
                    moneda TEXT DEFAULT 'USD',
                    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_history_property ON price_history(property_id)')
            
            # Registro de alertas enviadas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts_sent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id INTEGER NOT NULL,
                    alert_type TEXT NOT NULL,
                    message TEXT,
                    fecha_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_property ON alerts_sent(property_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_fecha ON alerts_sent(fecha_envio)')
            
            # Log de ejecuciones del scraper
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scraping_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    properties_found INTEGER DEFAULT 0,
                    properties_new INTEGER DEFAULT 0,
                    properties_updated INTEGER DEFAULT 0,
                    error_message TEXT,
                    duration_seconds REAL DEFAULT 0,
                    fecha_ejecucion DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            logger.debug("schema_initialized")
    
    def upsert_property(self, prop: Property) -> Tuple[int, str]:
        """
        Inserta o actualiza una propiedad.
        Si el precio cambió, guarda el historial.
        
        Args:
            prop: Propiedad a guardar
            
        Returns:
            Tupla (property_id, action) donde action es 'inserted', 'updated' o 'unchanged'
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Buscar si existe
            cursor.execute(
                'SELECT id, precio, moneda FROM properties '
                'WHERE id_externo = ? AND source = ? AND region = ? AND operacion = ?',
                (prop.id_externo, prop.source, prop.region, prop.operacion or 'venta')
            )
            existing = cursor.fetchone()
            
            now = datetime.now().isoformat()
            
            if existing is None:
                # Insertar nueva propiedad
                cursor.execute('''
                    INSERT INTO properties (
                        id_externo, source, region, operacion,
                        estado_provincia, localidad, sub_localidad,
                        titulo, precio, moneda, ubicacion,
                        tipo_inmueble, url, descripcion, metros_cuadrados,
                        habitaciones, banos, estacionamientos,
                        fecha_primera_vista, fecha_ultima_vista
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    prop.id_externo, prop.source, prop.region, prop.operacion or 'venta',
                    prop.estado_provincia, prop.localidad, prop.sub_localidad,
                    prop.titulo, prop.precio, prop.moneda,
                    prop.ubicacion, prop.tipo_inmueble, prop.url, prop.descripcion,
                    prop.metros_cuadrados, prop.habitaciones, prop.banos,
                    prop.estacionamientos, now, now
                ))
                
                property_id = cursor.lastrowid
                
                # Registrar precio inicial en historial
                cursor.execute('''
                    INSERT INTO price_history (property_id, precio, moneda, fecha_registro)
                    VALUES (?, ?, ?, ?)
                ''', (property_id, prop.precio, prop.moneda, now))
                
                logger.debug("property_inserted", id_externo=prop.id_externo, source=prop.source)
                return property_id, 'inserted'
            
            else:
                property_id = existing[0]
                old_precio = existing[1]
                old_moneda = existing[2]
                
                # Verificar si el precio cambió
                price_changed = (old_precio != prop.precio) or (old_moneda != prop.moneda)
                
                if price_changed:
                    # Guardar precio anterior en historial
                    cursor.execute('''
                        INSERT INTO price_history (property_id, precio, moneda, fecha_registro)
                        VALUES (?, ?, ?, ?)
                    ''', (property_id, prop.precio, prop.moneda, now))
                    
                    logger.info(
                        "price_changed",
                        id_externo=prop.id_externo,
                        old_precio=old_precio,
                        new_precio=prop.precio
                    )
                
                # Actualizar propiedad
                cursor.execute('''
                    UPDATE properties SET
                        titulo = ?, precio = ?, moneda = ?, ubicacion = ?,
                        estado_provincia = ?, localidad = ?, sub_localidad = ?,
                        tipo_inmueble = ?, url = ?, descripcion = ?,
                        metros_cuadrados = ?, habitaciones = ?, banos = ?,
                        estacionamientos = ?, fecha_ultima_vista = ?, is_active = 1
                    WHERE id = ?
                ''', (
                    prop.titulo, prop.precio, prop.moneda, prop.ubicacion,
                    prop.estado_provincia, prop.localidad, prop.sub_localidad,
                    prop.tipo_inmueble, prop.url, prop.descripcion,
                    prop.metros_cuadrados, prop.habitaciones, prop.banos,
                    prop.estacionamientos, now, property_id
                ))
                
                return property_id, 'updated' if price_changed else 'unchanged'
    
    def get_property_by_id(self, property_id: int) -> Optional[PropertyModel]:
        """Obtiene una propiedad por su ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM properties WHERE id = ?', (property_id,))
            row = cursor.fetchone()
            return PropertyModel.from_row(tuple(row)) if row else None
    
    def get_property_by_external_id(self, id_externo: str, source: str, region: str = "venezuela") -> Optional[PropertyModel]:
        """Obtiene una propiedad por su ID externo, fuente y región."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM properties WHERE id_externo = ? AND source = ? AND region = ?',
                (id_externo, source, region)
            )
            row = cursor.fetchone()
            return PropertyModel.from_row(tuple(row)) if row else None
    
    def get_all_properties(
        self,
        source: Optional[str] = None,
        tipo_inmueble: Optional[str] = None,
        region: Optional[str] = None,
        only_active: bool = True,
        only_opportunities: bool = False,
        limit: int = 1000
    ) -> List[PropertyModel]:
        """
        Obtiene propiedades con filtros opcionales.
        
        Args:
            source: Filtrar por portal
            tipo_inmueble: Filtrar por tipo
            only_active: Solo propiedades activas
            only_opportunities: Solo oportunidades
            limit: Máximo de resultados
            
        Returns:
            Lista de PropertyModel
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM properties WHERE 1=1'
            params = []
            
            if source:
                query += ' AND source = ?'
                params.append(source)
            
            if tipo_inmueble:
                query += ' AND tipo_inmueble = ?'
                params.append(tipo_inmueble)

            if region:
                query += ' AND region = ?'
                params.append(region)
            
            if only_active:
                query += ' AND is_active = 1'
            
            if only_opportunities:
                query += ' AND is_opportunity = 1'
            
            query += ' ORDER BY fecha_ultima_vista DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            return [PropertyModel.from_row(tuple(row)) for row in cursor.fetchall()]
    
    def get_price_history(self, property_id: int) -> List[PriceHistoryModel]:
        """Obtiene el historial de precios de una propiedad."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM price_history WHERE property_id = ? ORDER BY fecha_registro DESC',
                (property_id,)
            )
            return [PriceHistoryModel.from_row(tuple(row)) for row in cursor.fetchall()]
    
    def get_last_price(self, property_id: int) -> Optional[PriceHistoryModel]:
        """Obtiene el último precio registrado de una propiedad."""
        history = self.get_price_history(property_id)
        return history[0] if history else None
    
    def get_previous_price(self, property_id: int) -> Optional[PriceHistoryModel]:
        """Obtiene el precio anterior (no el actual) de una propiedad."""
        history = self.get_price_history(property_id)
        return history[1] if len(history) > 1 else None
    
    def get_average_price_by_type(self, tipo_inmueble: str, region: Optional[str] = None) -> Optional[float]:
        """Calcula el precio promedio de un tipo de inmueble."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = '''SELECT AVG(precio) FROM properties 
                   WHERE tipo_inmueble = ? AND is_active = 1'''
            params = [tipo_inmueble]
            if region:
                query += ' AND region = ?'
                params.append(region)
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
    
    def mark_as_opportunity(self, property_id: int, is_opportunity: bool = True):
        """Marca o desmarca una propiedad como oportunidad."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE properties SET is_opportunity = ? WHERE id = ?',
                (is_opportunity, property_id)
            )
    
    def mark_inactive_properties(
        self,
        source: str,
        active_ids: List[str],
        region: str = "venezuela",
        operacion: str = "venta",
    ):
        """
        Marca como inactivas las propiedades que ya no están en el portal.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if active_ids:
                placeholders = ','.join(['?' for _ in active_ids])
                cursor.execute(f'''
                    UPDATE properties SET is_active = 0
                    WHERE source = ? AND region = ? AND operacion = ?
                    AND id_externo NOT IN ({placeholders})
                ''', [source, region, operacion] + active_ids)
            else:
                cursor.execute(
                    'UPDATE properties SET is_active = 0 '
                    'WHERE source = ? AND region = ? AND operacion = ?',
                    (source, region, operacion)
                )
    
    def record_alert_sent(self, property_id: int, alert_type: str, message: str = ""):
        """Registra que se envió una alerta para una propiedad."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alerts_sent (property_id, alert_type, message, fecha_envio)
                VALUES (?, ?, ?, ?)
            ''', (property_id, alert_type, message, datetime.now().isoformat()))
    
    def was_alert_sent_recently(self, property_id: int, hours: int = 168) -> bool:
        """
        Verifica si se envió una alerta recientemente para esta propiedad.
        
        Args:
            property_id: ID de la propiedad
            hours: Período de cooldown en horas (default: 168 = 7 días)
            
        Returns:
            True si se envió alerta en el período especificado
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            cursor.execute('''
                SELECT COUNT(*) FROM alerts_sent
                WHERE property_id = ? AND fecha_envio > ?
            ''', (property_id, cutoff))
            count = cursor.fetchone()[0]
            return count > 0
    
    def log_scraping_run(self, log: ScrapingLogModel):
        """Registra una ejecución del scraper."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scraping_logs (
                    source, status, properties_found, properties_new,
                    properties_updated, error_message, duration_seconds, fecha_ejecucion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                log.source, log.status, log.properties_found, log.properties_new,
                log.properties_updated, log.error_message, log.duration_seconds,
                log.fecha_ejecucion.isoformat()
            ))
    
    def get_recent_logs(self, limit: int = 50) -> List[ScrapingLogModel]:
        """Obtiene los logs más recientes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM scraping_logs ORDER BY fecha_ejecucion DESC LIMIT ?',
                (limit,)
            )
            return [ScrapingLogModel.from_row(tuple(row)) for row in cursor.fetchall()]
    
    def get_stats(self, region: Optional[str] = None) -> Dict[str, Any]:
        """Obtiene estadísticas generales de la base de datos."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            region_filter = ' AND region = ?' if region else ''
            region_params = [region] if region else []

            stats = {}

            cursor.execute(f'SELECT COUNT(*) FROM properties WHERE 1=1{region_filter}', region_params)
            stats['total_properties'] = cursor.fetchone()[0]

            cursor.execute(f'SELECT COUNT(*) FROM properties WHERE is_active = 1{region_filter}', region_params)
            stats['active_properties'] = cursor.fetchone()[0]

            cursor.execute(
                f'SELECT COUNT(*) FROM properties WHERE is_opportunity = 1 AND is_active = 1{region_filter}',
                region_params
            )
            stats['opportunities'] = cursor.fetchone()[0]

            cursor.execute(f'''
                SELECT source, COUNT(*) as count
                FROM properties WHERE is_active = 1{region_filter}
                GROUP BY source
            ''', region_params)
            stats['by_source'] = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(f'''
                SELECT tipo_inmueble, COUNT(*) as count
                FROM properties WHERE is_active = 1{region_filter}
                GROUP BY tipo_inmueble
            ''', region_params)
            stats['by_type'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Alertas enviadas (últimos 7 días)
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            cursor.execute(
                'SELECT COUNT(*) FROM alerts_sent WHERE fecha_envio > ?',
                (week_ago,)
            )
            stats['alerts_last_week'] = cursor.fetchone()[0]
            
            return stats



