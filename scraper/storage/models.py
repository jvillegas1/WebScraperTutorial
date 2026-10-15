"""
Modelos de datos para el almacenamiento en SQLite.
Define las estructuras de las tablas y operaciones CRUD.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class PropertyModel:
    """Modelo para la tabla properties."""
    id: Optional[int] = None
    id_externo: str = ""
    source: str = ""
    region: str = "venezuela"
    estado_provincia: str = ""
    localidad: str = ""
    sub_localidad: str = ""
    operacion: str = "venta"
    titulo: str = ""
    precio: float = 0.0
    moneda: str = "USD"
    ubicacion: str = ""
    tipo_inmueble: str = ""
    url: str = ""
    descripcion: Optional[str] = None
    metros_cuadrados: Optional[float] = None
    habitaciones: Optional[int] = None
    banos: Optional[int] = None
    estacionamientos: Optional[int] = None
    fecha_primera_vista: datetime = field(default_factory=datetime.now)
    fecha_ultima_vista: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    is_opportunity: bool = False

    @classmethod
    def from_row(cls, row) -> 'PropertyModel':
        """Crea un PropertyModel desde una fila de SQLite."""
        if hasattr(row, 'keys'):
            keys = row.keys()
            region = row['region'] if 'region' in keys else 'venezuela'
            return cls(
                id=row['id'],
                id_externo=row['id_externo'],
                source=row['source'],
                region=region,
                estado_provincia=row['estado_provincia'] if 'estado_provincia' in keys else '',
                localidad=row['localidad'] if 'localidad' in keys else '',
                sub_localidad=row['sub_localidad'] if 'sub_localidad' in keys else '',
                operacion=row['operacion'] if 'operacion' in keys else 'venta',
                titulo=row['titulo'],
                precio=row['precio'],
                moneda=row['moneda'],
                ubicacion=row['ubicacion'],
                tipo_inmueble=row['tipo_inmueble'],
                url=row['url'],
                descripcion=row['descripcion'],
                metros_cuadrados=row['metros_cuadrados'],
                habitaciones=row['habitaciones'],
                banos=row['banos'],
                estacionamientos=row['estacionamientos'],
                fecha_primera_vista=datetime.fromisoformat(row['fecha_primera_vista']) if row['fecha_primera_vista'] else datetime.now(),
                fecha_ultima_vista=datetime.fromisoformat(row['fecha_ultima_vista']) if row['fecha_ultima_vista'] else datetime.now(),
                is_active=bool(row['is_active']),
                is_opportunity=bool(row['is_opportunity']),
            )

        # Fallback para tuplas legacy (sin columnas geo)
        if len(row) > 21:
            return cls(
                id=row[0], id_externo=row[1], source=row[2], region=row[3],
                estado_provincia=row[4], localidad=row[5], sub_localidad=row[6],
                titulo=row[7], precio=row[8], moneda=row[9], ubicacion=row[10],
                tipo_inmueble=row[11], url=row[12], descripcion=row[13],
                metros_cuadrados=row[14], habitaciones=row[15], banos=row[16],
                estacionamientos=row[17],
                fecha_primera_vista=datetime.fromisoformat(row[18]) if row[18] else datetime.now(),
                fecha_ultima_vista=datetime.fromisoformat(row[19]) if row[19] else datetime.now(),
                is_active=bool(row[20]), is_opportunity=bool(row[21]),
            )

        if len(row) > 18:
            return cls(
                id=row[0], id_externo=row[1], source=row[2], region=row[3],
                titulo=row[4], precio=row[5], moneda=row[6], ubicacion=row[7],
                tipo_inmueble=row[8], url=row[9], descripcion=row[10],
                metros_cuadrados=row[11], habitaciones=row[12], banos=row[13],
                estacionamientos=row[14],
                fecha_primera_vista=datetime.fromisoformat(row[15]) if row[15] else datetime.now(),
                fecha_ultima_vista=datetime.fromisoformat(row[16]) if row[16] else datetime.now(),
                is_active=bool(row[17]), is_opportunity=bool(row[18]),
            )

        return cls(
            id=row[0], id_externo=row[1], source=row[2], region='venezuela',
            titulo=row[3], precio=row[4], moneda=row[5], ubicacion=row[6],
            tipo_inmueble=row[7], url=row[8], descripcion=row[9],
            metros_cuadrados=row[10], habitaciones=row[11], banos=row[12],
            estacionamientos=row[13],
            fecha_primera_vista=datetime.fromisoformat(row[14]) if row[14] else datetime.now(),
            fecha_ultima_vista=datetime.fromisoformat(row[15]) if row[15] else datetime.now(),
            is_active=bool(row[16]), is_opportunity=bool(row[17]),
        )


@dataclass
class PriceHistoryModel:
    """Modelo para la tabla price_history."""
    id: Optional[int] = None
    property_id: int = 0
    precio: float = 0.0
    moneda: str = "USD"
    fecha_registro: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_row(cls, row: tuple) -> 'PriceHistoryModel':
        """Crea un PriceHistoryModel desde una fila de SQLite."""
        return cls(
            id=row[0],
            property_id=row[1],
            precio=row[2],
            moneda=row[3],
            fecha_registro=datetime.fromisoformat(row[4]) if row[4] else datetime.now(),
        )


@dataclass
class AlertSentModel:
    """Modelo para la tabla alerts_sent."""
    id: Optional[int] = None
    property_id: int = 0
    alert_type: str = ""
    message: str = ""
    fecha_envio: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_row(cls, row: tuple) -> 'AlertSentModel':
        """Crea un AlertSentModel desde una fila de SQLite."""
        return cls(
            id=row[0],
            property_id=row[1],
            alert_type=row[2],
            message=row[3] if len(row) > 3 else "",
            fecha_envio=datetime.fromisoformat(row[4 if len(row) > 4 else 3]) if row[3 if len(row) <= 4 else 4] else datetime.now(),
        )


@dataclass
class ScrapingLogModel:
    """Modelo para registrar ejecuciones del scraper."""
    id: Optional[int] = None
    source: str = ""
    status: str = ""
    properties_found: int = 0
    properties_new: int = 0
    properties_updated: int = 0
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    fecha_ejecucion: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_row(cls, row: tuple) -> 'ScrapingLogModel':
        """Crea un ScrapingLogModel desde una fila de SQLite."""
        return cls(
            id=row[0],
            source=row[1],
            status=row[2],
            properties_found=row[3],
            properties_new=row[4],
            properties_updated=row[5],
            error_message=row[6],
            duration_seconds=row[7],
            fecha_ejecucion=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
        )
