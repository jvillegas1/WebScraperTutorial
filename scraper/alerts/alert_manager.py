"""
Gestor central de alertas.
Coordina el envío de notificaciones por múltiples canales.
"""

from typing import List, Optional
from datetime import datetime, timedelta
import structlog

from ..config import ALERT_CONFIG
from ..storage.database import Database
from ..detection.opportunity_detector import Opportunity, OpportunityDetector
from .email_alert import EmailAlert
from .telegram_alert import TelegramAlert

logger = structlog.get_logger(__name__)


class AlertManager:
    """
    Gestor central de alertas que coordina múltiples canales de notificación.
    
    Características:
    - Control anti-spam (cooldown entre alertas del mismo inmueble)
    - Agrupación de alertas (batch) si hay muchas en poco tiempo
    - Registro de alertas enviadas
    - Soporte para múltiples canales (email, telegram)
    """
    
    def __init__(
        self,
        database: Database,
        email_alert: Optional[EmailAlert] = None,
        telegram_alert: Optional[TelegramAlert] = None,
        config: Optional[dict] = None
    ):
        """
        Inicializa el gestor de alertas.
        
        Args:
            database: Instancia de Database para registrar alertas
            email_alert: Instancia de EmailAlert (opcional)
            telegram_alert: Instancia de TelegramAlert (opcional)
            config: Configuración de alertas
        """
        self.db = database
        self.email = email_alert or EmailAlert()
        self.telegram = telegram_alert or TelegramAlert()
        self.config = config or ALERT_CONFIG
        
        self._pending_alerts: List[Opportunity] = []
        self._last_batch_time: Optional[datetime] = None
        
        logger.info(
            "alert_manager_initialized",
            email_enabled=self.email.enabled,
            telegram_enabled=self.telegram.enabled,
            cooldown_hours=self.config.get("cooldown_hours", 168)
        )
    
    def should_send_alert(self, opportunity: Opportunity) -> bool:
        """
        Verifica si se debe enviar una alerta para esta oportunidad.
        
        Args:
            opportunity: Oportunidad a evaluar
            
        Returns:
            True si se debe enviar la alerta
        """
        # Verificar cooldown
        cooldown_hours = self.config.get("cooldown_hours", 168)
        
        if self.db.was_alert_sent_recently(opportunity.property_id, cooldown_hours):
            logger.debug(
                "alert_skipped_cooldown",
                property_id=opportunity.property_id,
                cooldown_hours=cooldown_hours
            )
            return False
        
        return True
    
    def send_alert(self, opportunity: Opportunity, force: bool = False) -> bool:
        """
        Envía una alerta individual.
        
        Args:
            opportunity: Oportunidad a notificar
            force: Si True, ignora el cooldown
            
        Returns:
            True si se envió al menos por un canal
        """
        # Verificar si se debe enviar
        if not force and not self.should_send_alert(opportunity):
            return False
        
        sent = False
        channels_sent = []
        
        # Enviar por email
        if self.email.enabled:
            if self.email.send_single(opportunity):
                sent = True
                channels_sent.append("email")
        
        # Enviar por Telegram
        if self.telegram.enabled:
            if self.telegram.send_single(opportunity):
                sent = True
                channels_sent.append("telegram")
        
        # Registrar en base de datos
        if sent:
            self.db.record_alert_sent(
                property_id=opportunity.property_id,
                alert_type=opportunity.opportunity_type.value,
                message=opportunity.reason
            )
            
            logger.info(
                "alert_sent",
                property_id=opportunity.property_id,
                channels=channels_sent,
                opportunity_type=opportunity.opportunity_type.value
            )
        
        return sent
    
    def queue_alert(self, opportunity: Opportunity):
        """
        Agrega una alerta a la cola para envío en batch.
        
        Args:
            opportunity: Oportunidad a encolar
        """
        if not self.should_send_alert(opportunity):
            return
        
        self._pending_alerts.append(opportunity)
        
        logger.debug(
            "alert_queued",
            property_id=opportunity.property_id,
            queue_size=len(self._pending_alerts)
        )
    
    def process_queue(self, force: bool = False) -> int:
        """
        Procesa la cola de alertas pendientes.
        
        Args:
            force: Si True, envía inmediatamente sin esperar
            
        Returns:
            Número de alertas enviadas
        """
        if not self._pending_alerts:
            return 0
        
        batch_threshold = self.config.get("batch_threshold", 10)
        batch_delay = self.config.get("batch_delay_minutes", 30)
        
        # Verificar si debemos esperar más alertas
        if not force and len(self._pending_alerts) < batch_threshold:
            if self._last_batch_time:
                elapsed = (datetime.now() - self._last_batch_time).total_seconds() / 60
                if elapsed < batch_delay:
                    logger.debug(
                        "batch_waiting",
                        pending=len(self._pending_alerts),
                        minutes_elapsed=elapsed,
                        threshold=batch_threshold
                    )
                    return 0
        
        # Decidir si enviar en batch o individual
        if len(self._pending_alerts) >= batch_threshold:
            return self._send_batch()
        else:
            return self._send_individual()
    
    def _send_batch(self) -> int:
        """Envía alertas agrupadas en un solo mensaje."""
        sent = 0
        
        # Email batch
        if self.email.enabled:
            sent += self.email.send_batch(self._pending_alerts)
        
        # Telegram - enviar resumen + individuales más importantes
        if self.telegram.enabled:
            # Enviar resumen
            self.telegram.send_summary(self._pending_alerts)
            
            # Enviar las 5 mejores oportunidades individualmente
            top_opportunities = sorted(
                self._pending_alerts,
                key=lambda x: x.price_difference or 0,
                reverse=True
            )[:5]
            
            sent += self.telegram.send_batch(top_opportunities)
        
        # Registrar todas como enviadas
        for opp in self._pending_alerts:
            self.db.record_alert_sent(
                property_id=opp.property_id,
                alert_type=opp.opportunity_type.value,
                message=f"[BATCH] {opp.reason}"
            )
        
        logger.info(
            "batch_alerts_sent",
            total_opportunities=len(self._pending_alerts),
            messages_sent=sent
        )
        
        # Limpiar cola
        self._pending_alerts = []
        self._last_batch_time = datetime.now()
        
        return sent
    
    def _send_individual(self) -> int:
        """Envía alertas individualmente."""
        sent = 0
        
        for opp in self._pending_alerts:
            if self.send_alert(opp, force=True):
                sent += 1
        
        # Limpiar cola
        self._pending_alerts = []
        self._last_batch_time = datetime.now()
        
        return sent
    
    def process_new_opportunities(self, opportunities: List[Opportunity]) -> int:
        """
        Procesa una lista de nuevas oportunidades.
        
        Args:
            opportunities: Lista de oportunidades detectadas
            
        Returns:
            Número de alertas enviadas
        """
        if not opportunities:
            return 0
        
        logger.info(
            "processing_opportunities",
            total=len(opportunities)
        )
        
        # Filtrar las que ya fueron alertadas
        to_alert = [
            opp for opp in opportunities
            if self.should_send_alert(opp)
        ]
        
        logger.info(
            "opportunities_to_alert",
            total=len(to_alert),
            filtered=len(opportunities) - len(to_alert)
        )
        
        if not to_alert:
            return 0
        
        # Decidir estrategia según cantidad
        batch_threshold = self.config.get("batch_threshold", 10)
        
        if len(to_alert) >= batch_threshold:
            # Muchas alertas: enviar en batch
            self._pending_alerts = to_alert
            return self._send_batch()
        else:
            # Pocas alertas: enviar individualmente
            sent = 0
            for opp in to_alert:
                if self.send_alert(opp):
                    sent += 1
            return sent
    
    def send_test_alert(self) -> bool:
        """
        Envía una alerta de prueba.
        
        Returns:
            True si se envió correctamente
        """
        from ..storage.models import PropertyModel
        
        # Crear oportunidad de prueba
        test_property = PropertyModel(
            id=0,
            id_externo="TEST-001",
            source="test",
            titulo="Propiedad de Prueba - Verificación de Alertas",
            precio=50000,
            moneda="USD",
            ubicacion="Maracaibo, Zulia",
            tipo_inmueble="casa",
            url="https://example.com/test",
        )
        
        test_opportunity = Opportunity(
            property_id=0,
            property=test_property,
            opportunity_type=OpportunityDetector.OpportunityType.PRICE_DROP if hasattr(OpportunityDetector, 'OpportunityType') else "price_drop",
            reason="Esta es una alerta de prueba para verificar la configuración",
            price_difference=15.0,
            reference_price=60000,
        )
        
        # Para el test, importamos el tipo correcto
        from ..detection.opportunity_detector import OpportunityType
        test_opportunity.opportunity_type = OpportunityType.PRICE_DROP
        
        sent = False
        
        if self.email.enabled:
            sent = self.email.send_single(test_opportunity) or sent
        
        if self.telegram.enabled:
            sent = self.telegram.send_single(test_opportunity) or sent
        
        logger.info("test_alert_sent", success=sent)
        return sent
    
    def get_stats(self) -> dict:
        """
        Obtiene estadísticas de alertas.
        
        Returns:
            Diccionario con estadísticas
        """
        return {
            "pending_alerts": len(self._pending_alerts),
            "email_enabled": self.email.enabled,
            "telegram_enabled": self.telegram.enabled,
            "cooldown_hours": self.config.get("cooldown_hours", 168),
            "batch_threshold": self.config.get("batch_threshold", 10),
        }



