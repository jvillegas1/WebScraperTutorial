"""
Módulo de detección de oportunidades de compra.
Implementa reglas configurables para identificar precios bajos.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import structlog

from ..config import OPPORTUNITY_RULES
from ..storage.database import Database
from ..storage.models import PropertyModel

logger = structlog.get_logger(__name__)


class OpportunityType(str, Enum):
    """Tipos de oportunidad detectadas."""
    RELATIVE_LOW = "relative_low"  # Precio bajo relativo al promedio
    PRICE_DROP = "price_drop"  # Bajada de precio
    ABSOLUTE_LOW = "absolute_low"  # Precio bajo absoluto
    NEW_LISTING = "new_listing"  # Nuevo listado con precio atractivo


@dataclass
class Opportunity:
    """Representa una oportunidad detectada."""
    property_id: int
    property: PropertyModel
    opportunity_type: OpportunityType
    reason: str
    price_difference: Optional[float] = None  # Diferencia en porcentaje
    reference_price: Optional[float] = None  # Precio de referencia
    detected_at: datetime = None
    
    def __post_init__(self):
        if self.detected_at is None:
            self.detected_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la oportunidad a diccionario."""
        return {
            "property_id": self.property_id,
            "titulo": self.property.titulo,
            "precio": self.property.precio,
            "moneda": self.property.moneda,
            "ubicacion": self.property.ubicacion,
            "tipo_inmueble": self.property.tipo_inmueble,
            "url": self.property.url,
            "source": self.property.source,
            "opportunity_type": self.opportunity_type.value,
            "reason": self.reason,
            "price_difference": self.price_difference,
            "reference_price": self.reference_price,
            "detected_at": self.detected_at.isoformat(),
        }


class OpportunityDetector:
    """
    Detector de oportunidades de compra de inmuebles.
    
    Implementa tres tipos de detección:
    1. Precio bajo relativo: precio < promedio del tipo - X%
    2. Bajada de precio: precio actual < precio anterior - Y%
    3. Precio absoluto: precio < umbral definido por tipo
    """
    
    def __init__(self, database: Database, rules: Optional[Dict] = None):
        """
        Inicializa el detector.
        
        Args:
            database: Instancia de Database para consultas
            rules: Reglas de detección (usa OPPORTUNITY_RULES si no se especifica)
        """
        self.db = database
        self.rules = rules or OPPORTUNITY_RULES
        
        logger.info(
            "opportunity_detector_initialized",
            rules=self.rules
        )
    
    def detect_opportunities(
        self,
        property_ids: Optional[List[int]] = None
    ) -> List[Opportunity]:
        """
        Detecta oportunidades en las propiedades especificadas.
        
        Args:
            property_ids: Lista de IDs a evaluar. Si es None, evalúa todas las activas.
            
        Returns:
            Lista de Opportunity detectadas
        """
        opportunities = []
        
        # Obtener propiedades a evaluar
        if property_ids:
            properties = [
                self.db.get_property_by_id(pid)
                for pid in property_ids
            ]
            properties = [p for p in properties if p is not None]
        else:
            properties = self.db.get_all_properties(only_active=True)
        
        logger.info(
            "detecting_opportunities",
            total_properties=len(properties)
        )
        
        for prop in properties:
            prop_opportunities = self._evaluate_property(prop)
            opportunities.extend(prop_opportunities)
            
            # Marcar como oportunidad en la base de datos
            if prop_opportunities:
                self.db.mark_as_opportunity(prop.id, True)
            else:
                self.db.mark_as_opportunity(prop.id, False)
        
        logger.info(
            "opportunities_detected",
            total=len(opportunities),
            by_type={
                ot.value: len([o for o in opportunities if o.opportunity_type == ot])
                for ot in OpportunityType
            }
        )
        
        return opportunities
    
    def _evaluate_property(self, prop: PropertyModel) -> List[Opportunity]:
        """
        Evalúa una propiedad contra todas las reglas.
        
        Args:
            prop: Propiedad a evaluar
            
        Returns:
            Lista de oportunidades detectadas para esta propiedad
        """
        opportunities = []
        
        # Solo evaluar propiedades con precio válido en USD
        if prop.precio is None or prop.precio <= 0:
            return opportunities
        
        # Verificar moneda (preferimos USD para comparaciones)
        if prop.moneda != "USD":
            logger.debug(
                "skipping_non_usd_property",
                property_id=prop.id,
                moneda=prop.moneda
            )
            return opportunities
        
        # 1. Verificar precio bajo relativo
        relative_opp = self._check_relative_price(prop)
        if relative_opp:
            opportunities.append(relative_opp)
        
        # 2. Verificar bajada de precio
        drop_opp = self._check_price_drop(prop)
        if drop_opp:
            opportunities.append(drop_opp)
        
        # 3. Verificar precio absoluto
        absolute_opp = self._check_absolute_price(prop)
        if absolute_opp:
            opportunities.append(absolute_opp)
        
        return opportunities
    
    def _check_relative_price(self, prop: PropertyModel) -> Optional[Opportunity]:
        """
        Verifica si el precio está por debajo del promedio del tipo.
        
        Regla: precio < promedio_tipo * (1 - threshold)
        """
        threshold = self.rules.get("relative_threshold", 0.15)
        
        # Obtener precio promedio del tipo
        avg_price = self.db.get_average_price_by_type(prop.tipo_inmueble, region=getattr(prop, 'region', None))
        
        if avg_price is None or avg_price <= 0:
            return None
        
        # Calcular umbral
        price_threshold = avg_price * (1 - threshold)
        
        if prop.precio < price_threshold:
            difference = ((avg_price - prop.precio) / avg_price) * 100
            
            return Opportunity(
                property_id=prop.id,
                property=prop,
                opportunity_type=OpportunityType.RELATIVE_LOW,
                reason=f"Precio {difference:.1f}% por debajo del promedio de {prop.tipo_inmueble}",
                price_difference=difference,
                reference_price=avg_price,
            )
        
        return None
    
    def _check_price_drop(self, prop: PropertyModel) -> Optional[Opportunity]:
        """
        Verifica si hubo una bajada de precio significativa.
        
        Regla: precio_actual < precio_anterior * (1 - threshold)
        """
        threshold = self.rules.get("price_drop_threshold", 0.05)
        
        # Obtener precio anterior
        previous_price = self.db.get_previous_price(prop.id)
        
        if previous_price is None:
            return None
        
        # Calcular umbral de bajada
        price_threshold = previous_price.precio * (1 - threshold)
        
        if prop.precio < price_threshold:
            difference = ((previous_price.precio - prop.precio) / previous_price.precio) * 100
            
            return Opportunity(
                property_id=prop.id,
                property=prop,
                opportunity_type=OpportunityType.PRICE_DROP,
                reason=f"Bajada de precio: ${previous_price.precio:,.0f} → ${prop.precio:,.0f} (-{difference:.1f}%)",
                price_difference=difference,
                reference_price=previous_price.precio,
            )
        
        return None
    
    def _check_absolute_price(self, prop: PropertyModel) -> Optional[Opportunity]:
        """
        Verifica si el precio está por debajo del umbral absoluto.
        
        Regla: precio < umbral_definido_por_tipo
        """
        thresholds = self.rules.get("absolute_thresholds", {})
        
        # Obtener umbral para el tipo de inmueble
        tipo = prop.tipo_inmueble.lower() if prop.tipo_inmueble else "default"
        threshold = thresholds.get(tipo, thresholds.get("default", 40000))
        
        if prop.precio < threshold:
            difference = ((threshold - prop.precio) / threshold) * 100
            
            return Opportunity(
                property_id=prop.id,
                property=prop,
                opportunity_type=OpportunityType.ABSOLUTE_LOW,
                reason=f"Precio por debajo de ${threshold:,.0f} (umbral para {prop.tipo_inmueble})",
                price_difference=difference,
                reference_price=threshold,
            )
        
        return None
    
    def get_new_opportunities_since(
        self,
        since: datetime,
        exclude_alerted: bool = True
    ) -> List[Opportunity]:
        """
        Obtiene oportunidades nuevas desde una fecha.
        
        Args:
            since: Fecha desde la cual buscar
            exclude_alerted: Excluir propiedades ya alertadas
            
        Returns:
            Lista de nuevas oportunidades
        """
        # Obtener propiedades marcadas como oportunidad
        properties = self.db.get_all_properties(
            only_active=True,
            only_opportunities=True
        )
        
        opportunities = []
        
        for prop in properties:
            # Filtrar por fecha
            if prop.fecha_ultima_vista < since:
                continue
            
            # Verificar si ya se alertó
            if exclude_alerted and self.db.was_alert_sent_recently(prop.id):
                continue
            
            # Re-evaluar para obtener detalles de la oportunidad
            prop_opportunities = self._evaluate_property(prop)
            opportunities.extend(prop_opportunities)
        
        return opportunities
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Obtiene un resumen de oportunidades actuales.
        
        Returns:
            Diccionario con estadísticas de oportunidades
        """
        properties = self.db.get_all_properties(
            only_active=True,
            only_opportunities=True
        )
        
        summary = {
            "total_opportunities": len(properties),
            "by_type": {},
            "by_source": {},
            "avg_price": 0,
            "min_price": None,
            "max_price": None,
        }
        
        prices = []
        
        for prop in properties:
            # Por tipo de inmueble
            tipo = prop.tipo_inmueble or "otro"
            summary["by_type"][tipo] = summary["by_type"].get(tipo, 0) + 1
            
            # Por fuente
            source = prop.source
            summary["by_source"][source] = summary["by_source"].get(source, 0) + 1
            
            # Precios
            if prop.precio and prop.moneda == "USD":
                prices.append(prop.precio)
        
        if prices:
            summary["avg_price"] = sum(prices) / len(prices)
            summary["min_price"] = min(prices)
            summary["max_price"] = max(prices)
        
        return summary



