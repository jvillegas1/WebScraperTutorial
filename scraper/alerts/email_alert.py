"""
Módulo de alertas por correo electrónico.
Envía notificaciones de oportunidades via SMTP.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from datetime import datetime
import structlog

from ..config import EMAIL_CONFIG
from ..detection.opportunity_detector import Opportunity

logger = structlog.get_logger(__name__)


class EmailAlert:
    """
    Gestor de alertas por correo electrónico.
    Usa SMTP para enviar notificaciones de oportunidades.
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Inicializa el gestor de alertas email.
        
        Args:
            config: Configuración SMTP. Usa EMAIL_CONFIG si no se especifica.
        """
        self.config = config or EMAIL_CONFIG
        self.enabled = self.config.get("enabled", False)
        
        if self.enabled:
            logger.info(
                "email_alert_initialized",
                smtp_server=self.config.get("smtp_server"),
                from_email=self.config.get("from_email"),
                to_emails=len(self.config.get("to_emails", []))
            )
        else:
            logger.info("email_alert_disabled")
    
    def _create_html_template(self, opportunity: Opportunity) -> str:
        """Crea el contenido HTML del email."""
        prop = opportunity.property
        
        # Determinar color según tipo de oportunidad
        type_colors = {
            "relative_low": "#28a745",  # Verde
            "price_drop": "#dc3545",    # Rojo
            "absolute_low": "#007bff",  # Azul
            "new_listing": "#ffc107",   # Amarillo
        }
        color = type_colors.get(opportunity.opportunity_type.value, "#6c757d")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f8f9fa; padding: 20px; border: 1px solid #ddd; }}
                .property-title {{ font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }}
                .price {{ font-size: 24px; color: {color}; font-weight: bold; }}
                .price-old {{ font-size: 16px; color: #999; text-decoration: line-through; }}
                .details {{ margin: 15px 0; }}
                .detail-row {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
                .label {{ font-weight: bold; color: #666; }}
                .btn {{ display: inline-block; padding: 12px 24px; background-color: {color}; color: white; text-decoration: none; border-radius: 5px; margin-top: 15px; }}
                .footer {{ text-align: center; padding: 15px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏠 OPORTUNIDAD DETECTADA</h1>
                    <p>{opportunity.opportunity_type.value.replace('_', ' ').upper()}</p>
                </div>
                <div class="content">
                    <div class="property-title">{prop.titulo}</div>
                    
                    <div class="price">
                        {prop.moneda} ${prop.precio:,.0f}
                    </div>
                    
                    {"<div class='price-old'>Precio anterior: $" + f"{opportunity.reference_price:,.0f}</div>" if opportunity.reference_price and opportunity.opportunity_type.value == "price_drop" else ""}
                    
                    <p style="color: {color}; font-weight: bold;">
                        {opportunity.reason}
                    </p>
                    
                    <div class="details">
                        <div class="detail-row">
                            <span class="label">Tipo:</span> {prop.tipo_inmueble}
                        </div>
                        <div class="detail-row">
                            <span class="label">Ubicación:</span> {prop.ubicacion}
                        </div>
                        <div class="detail-row">
                            <span class="label">Portal:</span> {prop.source}
                        </div>
                        <div class="detail-row">
                            <span class="label">Detectado:</span> {opportunity.detected_at.strftime('%d/%m/%Y %H:%M')}
                        </div>
                    </div>
                    
                    <a href="{prop.url}" class="btn">Ver Anuncio →</a>
                </div>
                <div class="footer">
                    <p>Web Scraper de Inmuebles - Maracaibo, Venezuela</p>
                    <p>Este es un mensaje automático. No responder.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def _create_text_template(self, opportunity: Opportunity) -> str:
        """Crea el contenido de texto plano del email."""
        prop = opportunity.property
        
        text = f"""
=================================
OPORTUNIDAD DETECTADA
=================================

{opportunity.opportunity_type.value.replace('_', ' ').upper()}

Título: {prop.titulo}
Precio: {prop.moneda} ${prop.precio:,.0f}
{"Precio anterior: $" + f"{opportunity.reference_price:,.0f}" if opportunity.reference_price else ""}

Razón: {opportunity.reason}

Detalles:
- Tipo: {prop.tipo_inmueble}
- Ubicación: {prop.ubicacion}
- Portal: {prop.source}
- Detectado: {opportunity.detected_at.strftime('%d/%m/%Y %H:%M')}

Ver anuncio: {prop.url}

=================================
Web Scraper de Inmuebles
Maracaibo, Venezuela
"""
        return text
    
    def send_single(self, opportunity: Opportunity) -> bool:
        """
        Envía una alerta individual.
        
        Args:
            opportunity: Oportunidad a notificar
            
        Returns:
            True si se envió correctamente
        """
        if not self.enabled:
            logger.debug("email_alert_skipped", reason="disabled")
            return False
        
        to_emails = self.config.get("to_emails", [])
        if not to_emails:
            logger.warning("email_alert_no_recipients")
            return False
        
        try:
            # Crear mensaje
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🏠 Oportunidad: {opportunity.property.titulo[:50]}..."
            msg["From"] = self.config["from_email"]
            msg["To"] = ", ".join(to_emails)
            
            # Agregar versiones text y HTML
            text_content = self._create_text_template(opportunity)
            html_content = self._create_html_template(opportunity)
            
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            
            # Enviar
            with smtplib.SMTP(
                self.config["smtp_server"],
                self.config["smtp_port"]
            ) as server:
                server.starttls()
                server.login(
                    self.config["smtp_user"],
                    self.config["smtp_password"]
                )
                server.send_message(msg)
            
            logger.info(
                "email_sent",
                property_id=opportunity.property_id,
                to=to_emails
            )
            return True
            
        except Exception as e:
            logger.error(
                "email_send_error",
                error=str(e),
                property_id=opportunity.property_id
            )
            return False
    
    def send_batch(self, opportunities: List[Opportunity]) -> int:
        """
        Envía múltiples oportunidades en un solo email.
        
        Args:
            opportunities: Lista de oportunidades
            
        Returns:
            Número de emails enviados correctamente
        """
        if not self.enabled:
            return 0
        
        if not opportunities:
            return 0
        
        to_emails = self.config.get("to_emails", [])
        if not to_emails:
            return 0
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🏠 {len(opportunities)} Oportunidades Detectadas"
            msg["From"] = self.config["from_email"]
            msg["To"] = ", ".join(to_emails)
            
            # Crear contenido del resumen
            html_items = []
            text_items = []
            
            for opp in opportunities:
                html_items.append(f"""
                <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;">
                    <h3 style="margin: 0 0 10px 0;">{opp.property.titulo}</h3>
                    <p style="font-size: 20px; color: #28a745; margin: 5px 0;">
                        {opp.property.moneda} ${opp.property.precio:,.0f}
                    </p>
                    <p style="color: #666;">{opp.reason}</p>
                    <p>
                        <strong>Ubicación:</strong> {opp.property.ubicacion}<br>
                        <strong>Tipo:</strong> {opp.property.tipo_inmueble}<br>
                        <strong>Portal:</strong> {opp.property.source}
                    </p>
                    <a href="{opp.property.url}" style="color: #007bff;">Ver anuncio →</a>
                </div>
                """)
                
                text_items.append(f"""
---
{opp.property.titulo}
Precio: {opp.property.moneda} ${opp.property.precio:,.0f}
Razón: {opp.reason}
Ubicación: {opp.property.ubicacion}
Portal: {opp.property.source}
URL: {opp.property.url}
""")
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: Arial, sans-serif;">
                <h1 style="color: #333;">🏠 {len(opportunities)} Oportunidades Detectadas</h1>
                <p>Se han detectado las siguientes oportunidades de inversión:</p>
                {"".join(html_items)}
                <hr>
                <p style="color: #666; font-size: 12px;">Web Scraper de Inmuebles - Maracaibo, Venezuela</p>
            </body>
            </html>
            """
            
            text_content = f"""
{len(opportunities)} OPORTUNIDADES DETECTADAS
{'=' * 40}

{"".join(text_items)}

---
Web Scraper de Inmuebles - Maracaibo, Venezuela
"""
            
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            
            with smtplib.SMTP(
                self.config["smtp_server"],
                self.config["smtp_port"]
            ) as server:
                server.starttls()
                server.login(
                    self.config["smtp_user"],
                    self.config["smtp_password"]
                )
                server.send_message(msg)
            
            logger.info(
                "batch_email_sent",
                opportunities_count=len(opportunities),
                to=to_emails
            )
            return 1
            
        except Exception as e:
            logger.error("batch_email_error", error=str(e))
            return 0
    
    def test_connection(self) -> bool:
        """
        Prueba la conexión SMTP.
        
        Returns:
            True si la conexión es exitosa
        """
        if not self.enabled:
            return False
        
        try:
            with smtplib.SMTP(
                self.config["smtp_server"],
                self.config["smtp_port"]
            ) as server:
                server.starttls()
                server.login(
                    self.config["smtp_user"],
                    self.config["smtp_password"]
                )
            
            logger.info("smtp_connection_test_success")
            return True
            
        except Exception as e:
            logger.error("smtp_connection_test_failed", error=str(e))
            return False



