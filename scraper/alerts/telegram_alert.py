"""
Módulo de alertas por Telegram.
Envía notificaciones de oportunidades via Telegram Bot.
"""

import asyncio
from typing import List, Optional
from datetime import datetime
import structlog

from ..config import TELEGRAM_CONFIG
from ..detection.opportunity_detector import Opportunity

logger = structlog.get_logger(__name__)


class TelegramAlert:
    """
    Gestor de alertas por Telegram.
    Usa la API de Telegram Bot para enviar notificaciones.
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Inicializa el gestor de alertas Telegram.
        
        Args:
            config: Configuración del bot. Usa TELEGRAM_CONFIG si no se especifica.
        """
        self.config = config or TELEGRAM_CONFIG
        self.enabled = self.config.get("enabled", False)
        self.bot_token = self.config.get("bot_token", "")
        self.chat_ids = self.config.get("chat_ids", [])
        self._bot = None
        
        if self.enabled and self.bot_token:
            logger.info(
                "telegram_alert_initialized",
                chat_ids_count=len(self.chat_ids)
            )
        else:
            logger.info("telegram_alert_disabled")
    
    async def _get_bot(self):
        """Obtiene o crea la instancia del bot."""
        if self._bot is None and self.enabled:
            try:
                from telegram import Bot
                self._bot = Bot(token=self.bot_token)
            except ImportError:
                logger.error("telegram_library_not_installed")
                self.enabled = False
        return self._bot
    
    def _format_message(self, opportunity: Opportunity) -> str:
        """
        Formatea el mensaje de Telegram con Markdown.
        
        Args:
            opportunity: Oportunidad a notificar
            
        Returns:
            Mensaje formateado en Markdown
        """
        prop = opportunity.property
        
        # Emoji según tipo de oportunidad
        type_emojis = {
            "relative_low": "📉",
            "price_drop": "🔻",
            "absolute_low": "💰",
            "new_listing": "🆕",
        }
        emoji = type_emojis.get(opportunity.opportunity_type.value, "🏠")
        
        # Construir mensaje
        lines = [
            f"{emoji} *OPORTUNIDAD DETECTADA*",
            "",
            f"*{self._escape_markdown(prop.titulo)}*",
            "",
            f"💵 *Precio:* {prop.moneda} ${prop.precio:,.0f}",
        ]
        
        # Agregar precio anterior si es bajada de precio
        if opportunity.reference_price and opportunity.opportunity_type.value == "price_drop":
            lines.append(f"📊 *Precio anterior:* ${opportunity.reference_price:,.0f}")
            lines.append(f"📉 *Bajada:* {opportunity.price_difference:.1f}%")
        
        lines.extend([
            "",
            f"📍 *Ubicación:* {self._escape_markdown(prop.ubicacion)}",
            f"🏢 *Tipo:* {self._escape_markdown(prop.tipo_inmueble)}",
            f"🌐 *Portal:* {prop.source}",
            "",
            f"ℹ️ _{self._escape_markdown(opportunity.reason)}_",
            "",
            f"🔗 [Ver anuncio]({prop.url})",
        ])
        
        return "\n".join(lines)
    
    def _escape_markdown(self, text: str) -> str:
        """Escapa caracteres especiales de Markdown."""
        if not text:
            return ""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    async def _send_message_async(self, chat_id: str, message: str) -> bool:
        """
        Envía un mensaje a un chat específico.
        
        Args:
            chat_id: ID del chat de Telegram
            message: Mensaje a enviar
            
        Returns:
            True si se envió correctamente
        """
        bot = await self._get_bot()
        if not bot:
            return False
        
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="MarkdownV2",
                disable_web_page_preview=False
            )
            return True
        except Exception as e:
            # Intentar sin Markdown si falla
            try:
                # Limpiar mensaje de Markdown
                clean_message = message.replace('*', '').replace('_', '').replace('[', '').replace(']', '')
                await bot.send_message(
                    chat_id=chat_id,
                    text=clean_message,
                    disable_web_page_preview=False
                )
                return True
            except Exception as e2:
                logger.error(
                    "telegram_send_error",
                    chat_id=chat_id,
                    error=str(e2)
                )
                return False
    
    def send_single(self, opportunity: Opportunity) -> bool:
        """
        Envía una alerta individual a todos los chats configurados.
        
        Args:
            opportunity: Oportunidad a notificar
            
        Returns:
            True si se envió al menos a un chat
        """
        if not self.enabled:
            logger.debug("telegram_alert_skipped", reason="disabled")
            return False
        
        if not self.chat_ids:
            logger.warning("telegram_alert_no_chat_ids")
            return False
        
        message = self._format_message(opportunity)
        
        async def _send_all():
            results = []
            for chat_id in self.chat_ids:
                result = await self._send_message_async(chat_id, message)
                results.append(result)
            return results
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(_send_all())
        success = any(results)
        
        if success:
            logger.info(
                "telegram_sent",
                property_id=opportunity.property_id,
                chats_sent=sum(results),
                chats_total=len(self.chat_ids)
            )
        
        return success
    
    def send_batch(self, opportunities: List[Opportunity]) -> int:
        """
        Envía múltiples oportunidades.
        
        Args:
            opportunities: Lista de oportunidades
            
        Returns:
            Número de mensajes enviados correctamente
        """
        if not self.enabled or not opportunities:
            return 0
        
        # Para Telegram, enviamos mensajes individuales
        # (mejor experiencia de usuario que un mensaje gigante)
        sent = 0
        
        for opp in opportunities:
            if self.send_single(opp):
                sent += 1
            # Pequeño delay entre mensajes para evitar rate limiting
            import time
            time.sleep(0.5)
        
        return sent
    
    def send_summary(self, opportunities: List[Opportunity]) -> bool:
        """
        Envía un resumen de oportunidades.
        
        Args:
            opportunities: Lista de oportunidades
            
        Returns:
            True si se envió correctamente
        """
        if not self.enabled or not opportunities:
            return False
        
        lines = [
            "📊 *RESUMEN DE OPORTUNIDADES*",
            "",
            f"Se detectaron *{len(opportunities)}* oportunidades:",
            "",
        ]
        
        # Agrupar por tipo
        by_type = {}
        for opp in opportunities:
            otype = opp.opportunity_type.value
            if otype not in by_type:
                by_type[otype] = []
            by_type[otype].append(opp)
        
        type_names = {
            "relative_low": "📉 Precio bajo relativo",
            "price_drop": "🔻 Bajada de precio",
            "absolute_low": "💰 Precio bajo absoluto",
            "new_listing": "🆕 Nuevo listado",
        }
        
        for otype, opps in by_type.items():
            name = type_names.get(otype, otype)
            lines.append(f"{name}: *{len(opps)}*")
        
        lines.extend([
            "",
            "_Use /oportunidades para ver el listado completo_"
        ])
        
        message = "\n".join(lines)
        
        async def _send_all():
            results = []
            for chat_id in self.chat_ids:
                result = await self._send_message_async(chat_id, message)
                results.append(result)
            return results
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(_send_all())
        return any(results)
    
    async def test_connection_async(self) -> bool:
        """Prueba la conexión al bot de Telegram."""
        bot = await self._get_bot()
        if not bot:
            return False
        
        try:
            me = await bot.get_me()
            logger.info(
                "telegram_connection_test_success",
                bot_username=me.username
            )
            return True
        except Exception as e:
            logger.error("telegram_connection_test_failed", error=str(e))
            return False
    
    def test_connection(self) -> bool:
        """
        Prueba la conexión al bot de Telegram.
        
        Returns:
            True si la conexión es exitosa
        """
        if not self.enabled:
            return False
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.test_connection_async())



