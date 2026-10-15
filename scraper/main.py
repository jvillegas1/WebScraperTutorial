#!/usr/bin/env python3
"""
Web Scraper de Inmuebles - Maracaibo, Venezuela

Sistema automatizado para recolectar inmuebles en venta desde múltiples portales,
detectar oportunidades de precio y enviar alertas automáticas.

Uso:
    python main.py --run-now          # Ejecutar scraping inmediato
    python main.py --start-scheduler  # Iniciar scheduler automático
    python main.py --test-alerts      # Probar sistema de alertas
    python main.py --stats            # Ver estadísticas
    python main.py --debug            # Modo debug
"""

import sys
import time
import signal
from pathlib import Path
from datetime import datetime

import click
import structlog

# Configurar path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.config import (
    DEBUG, DB_PATH, LOGS_DIR, DEFAULT_REGION, EMAIL_CONFIG, TELEGRAM_CONFIG
)
from scraper.regions import REGIONS, get_region_config, get_active_sources, list_regions
from scraper.storage.database import Database
from scraper.scheduler.job_scheduler import JobScheduler
from scraper.alerts.alert_manager import AlertManager
from scraper.alerts.email_alert import EmailAlert
from scraper.alerts.telegram_alert import TelegramAlert
from scraper.detection.opportunity_detector import OpportunityDetector
from scraper.sources import get_scraper_registry, get_scraper_class, list_sources


def setup_logging(debug: bool = False):
    """Configura el sistema de logging."""
    log_level = "DEBUG" if debug else "INFO"
    
    # Crear directorio de logs
    LOGS_DIR.mkdir(exist_ok=True)
    
    # Configurar structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configurar logging estándar
    import logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level),
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS_DIR / "scraper.log", encoding="utf-8")
        ]
    )


def create_app_components():
    """Crea e inicializa los componentes principales."""
    db = Database(DB_PATH)
    email_alert = EmailAlert()
    telegram_alert = TelegramAlert()
    alert_manager = AlertManager(db, email_alert, telegram_alert)
    scheduler = JobScheduler(db, alert_manager)
    detector = OpportunityDetector(db)
    
    return {
        "db": db,
        "email": email_alert,
        "telegram": telegram_alert,
        "alerts": alert_manager,
        "scheduler": scheduler,
        "detector": detector,
    }


@click.group(invoke_without_command=True)
@click.option("--debug", is_flag=True, help="Activar modo debug")
@click.pass_context
def cli(ctx, debug):
    """Web Scraper de Inmuebles - Maracaibo, Venezuela"""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug or DEBUG
    setup_logging(ctx.obj["debug"])
    
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("--source", "-s", help="Scraper específico a ejecutar")
@click.option("--region", "-r", default=DEFAULT_REGION, type=click.Choice(list_regions()), help="Región a scrapear")
@click.option(
    "--operation", "-o",
    type=click.Choice(["venta", "alquiler", "all"]),
    default="all",
    help="Tipo de operación (default: ambas)",
)
@click.pass_context
def run(ctx, source, region, operation):
    """Ejecuta el scraping inmediatamente."""
    logger = structlog.get_logger()
    logger.info("starting_manual_run", source=source or "all", region=region, operation=operation)
    
    components = create_app_components()
    scheduler = components["scheduler"]
    registry = get_scraper_registry(region)
    operations = None if operation == "all" else [operation]
    
    if source:
        if source not in registry:
            click.echo(f"Error: Scraper '{source}' no encontrado en {region}.")
            click.echo(f"Disponibles: {', '.join(registry.keys())}")
            return
        
        log = scheduler.run_scraper(source, region=region, operations=operations)
        click.echo(f"\nResultado para {region}/{source}:")
        click.echo(f"  Estado: {log.status}")
        click.echo(f"  Encontrados: {log.properties_found}")
        click.echo(f"  Nuevos: {log.properties_new}")
        click.echo(f"  Actualizados: {log.properties_updated}")
        click.echo(f"  Duración: {log.duration_seconds:.2f}s")
        
        if log.error_message:
            click.echo(f"  Error: {log.error_message}")
    else:
        logs = scheduler.run_all_scrapers(region=region, operations=operations)
        
        click.echo("\n" + "=" * 50)
        click.echo(f"RESUMEN DE SCRAPING - {region.upper()}")
        click.echo("=" * 50)
        
        total_found = 0
        total_new = 0
        total_updated = 0
        
        for log in logs:
            status_icon = "[OK]" if log.status == "success" else "[FAIL]"
            click.echo(f"\n{status_icon} {log.source}:")
            click.echo(f"    Encontrados: {log.properties_found}")
            click.echo(f"    Nuevos: {log.properties_new}")
            click.echo(f"    Actualizados: {log.properties_updated}")
            click.echo(f"    Duracion: {log.duration_seconds:.2f}s")
            
            if log.error_message:
                click.echo(f"    Error: {log.error_message}")
            
            total_found += log.properties_found
            total_new += log.properties_new
            total_updated += log.properties_updated
        
        click.echo("\n" + "-" * 50)
        click.echo(f"TOTAL: {total_found} encontrados, {total_new} nuevos, {total_updated} actualizados")


@cli.command()
@click.pass_context
def scheduler(ctx):
    """Inicia el scheduler para ejecución automática."""
    logger = structlog.get_logger()
    logger.info("starting_scheduler")
    
    components = create_app_components()
    job_scheduler = components["scheduler"]
    
    # Manejar señales de terminación
    def signal_handler(sig, frame):
        click.echo("\nDeteniendo scheduler...")
        job_scheduler.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    click.echo("Iniciando scheduler...")
    click.echo("Presiona Ctrl+C para detener.\n")
    
    job_scheduler.start()
    
    # Mostrar información de los jobs
    status = job_scheduler.get_status()
    click.echo("Jobs programados:")
    for job in status["jobs"]:
        click.echo(f"  - {job['name']}: próxima ejecución {job['next_run']}")
    
    click.echo("\n" + "=" * 50)
    
    # Mantener el proceso corriendo
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        job_scheduler.stop()


@cli.command()
@click.option("--region", "-r", default=None, type=click.Choice(list_regions()), help="Filtrar por región")
@click.pass_context
def stats(ctx, region):
    """Muestra estadísticas del sistema."""
    components = create_app_components()
    db = components["db"]
    detector = components["detector"]
    
    db_stats = db.get_stats(region=region)
    
    click.echo("\n" + "=" * 50)
    title = f"ESTADÍSTICAS - {region.upper()}" if region else "ESTADÍSTICAS DEL SISTEMA"
    click.echo(title)
    click.echo("=" * 50)
    
    click.echo(f"\nPropiedades:")
    click.echo(f"  Total: {db_stats['total_properties']}")
    click.echo(f"  Activas: {db_stats['active_properties']}")
    click.echo(f"  Oportunidades: {db_stats['opportunities']}")
    
    click.echo(f"\nPor fuente:")
    for source, count in db_stats.get('by_source', {}).items():
        click.echo(f"  {source}: {count}")
    
    click.echo(f"\nPor tipo:")
    for tipo, count in db_stats.get('by_type', {}).items():
        click.echo(f"  {tipo}: {count}")
    
    click.echo(f"\nAlertas enviadas (últimos 7 días): {db_stats.get('alerts_last_week', 0)}")
    
    # Resumen de oportunidades
    opp_summary = detector.get_summary()
    if opp_summary['total_opportunities'] > 0:
        click.echo(f"\nOportunidades actuales:")
        click.echo(f"  Precio promedio: ${opp_summary['avg_price']:,.0f}")
        click.echo(f"  Precio mínimo: ${opp_summary['min_price']:,.0f}")
        click.echo(f"  Precio máximo: ${opp_summary['max_price']:,.0f}")


@cli.command()
@click.option("--region", "-r", default=None, type=click.Choice(list_regions()), help="Filtrar por región")
@click.pass_context
def opportunities(ctx, region):
    """Lista las oportunidades detectadas."""
    components = create_app_components()
    db = components["db"]
    
    properties = db.get_all_properties(region=region, only_opportunities=True, only_active=True)
    
    if not properties:
        click.echo("No hay oportunidades detectadas actualmente.")
        return
    
    click.echo(f"\n{'=' * 70}")
    click.echo(f"OPORTUNIDADES DETECTADAS ({len(properties)} total)")
    click.echo(f"{'=' * 70}\n")
    
    for prop in properties[:20]:  # Mostrar maximo 20
        click.echo(f"* {prop.titulo[:60]}...")
        click.echo(f"   Precio: {prop.moneda} ${prop.precio:,.0f}")
        click.echo(f"   Tipo: {prop.tipo_inmueble} | Ubicacion: {prop.ubicacion}")
        click.echo(f"   Portal: {prop.source}")
        click.echo(f"   URL: {prop.url}")
        click.echo()
    
    if len(properties) > 20:
        click.echo(f"... y {len(properties) - 20} más.")


@cli.command()
@click.pass_context
def test_alerts(ctx):
    """Envía una alerta de prueba."""
    components = create_app_components()
    alert_manager = components["alerts"]
    
    click.echo("Enviando alerta de prueba...")
    
    success = alert_manager.send_test_alert()
    
    if success:
        click.echo("[OK] Alerta de prueba enviada correctamente.")
    else:
        click.echo("[FAIL] Error al enviar alerta de prueba.")
        click.echo("  Verifica la configuracion de email/telegram en config.py")


@cli.command()
@click.option("--region", "-r", default=DEFAULT_REGION, type=click.Choice(list_regions()), help="Región a probar")
@click.pass_context  
def test_connections(ctx, region):
    """Prueba las conexiones a portales y servicios."""
    click.echo(f"\nProbando conexiones ({region})...\n")
    region_config = get_region_config(region)
    registry = get_scraper_registry(region)
    
    click.echo("PORTALES:")
    for name, scraper_class in registry.items():
        if not region_config["active_sources"].get(name, False):
            click.echo(f"  {name}: [SKIP] desactivado")
            continue
        
        try:
            with scraper_class(config=region_config["scraping"]) as scraper:
                if scraper.test_connection():
                    click.echo(f"  {name}: [OK] conectado")
                else:
                    click.echo(f"  {name}: [FAIL] sin respuesta")
        except Exception as e:
            click.echo(f"  {name}: [FAIL] error ({str(e)[:30]})")
    
    # Probar alertas
    click.echo("\nSERVICIOS DE ALERTA:")
    
    email = EmailAlert()
    if EMAIL_CONFIG.get("enabled"):
        if email.test_connection():
            click.echo("  Email (SMTP): [OK] conectado")
        else:
            click.echo("  Email (SMTP): [FAIL] error de conexion")
    else:
        click.echo("  Email (SMTP): [SKIP] desactivado")
    
    telegram = TelegramAlert()
    if TELEGRAM_CONFIG.get("enabled"):
        if telegram.test_connection():
            click.echo("  Telegram: [OK] conectado")
        else:
            click.echo("  Telegram: [FAIL] error de conexion")
    else:
        click.echo("  Telegram: [SKIP] desactivado")


@cli.command()
@click.pass_context
def logs(ctx):
    """Muestra los logs recientes de scraping."""
    components = create_app_components()
    scheduler = components["scheduler"]
    
    recent_logs = scheduler.get_recent_logs(20)
    
    if not recent_logs:
        click.echo("No hay logs de ejecución.")
        return
    
    click.echo(f"\n{'=' * 70}")
    click.echo("LOGS RECIENTES DE SCRAPING")
    click.echo(f"{'=' * 70}\n")
    
    for log in recent_logs:
        status_icon = "[OK]" if log.status == "success" else "[FAIL]"
        click.echo(f"{status_icon} [{log.fecha_ejecucion.strftime('%Y-%m-%d %H:%M')}] {log.source}")
        click.echo(f"   Encontrados: {log.properties_found} | Nuevos: {log.properties_new} | Actualizados: {log.properties_updated}")
        if log.error_message:
            click.echo(f"   Error: {log.error_message[:50]}...")
        click.echo()


@cli.command()
@click.pass_context
def version(ctx):
    """Muestra la versión del sistema."""
    click.echo("\nWeb Scraper de Inmuebles v2.0.0")
    click.echo("Tiers: Venezuela (nacional) | Argentina (mercado dinámico)")
    for region in list_regions():
        cfg = get_region_config(region)
        click.echo(f"\n{cfg['flag']} {cfg['label']}:")
        for name, active in cfg["active_sources"].items():
            status = "[ON]" if active else "[OFF]"
            click.echo(f"  {status} {name}")


if __name__ == "__main__":
    cli()

