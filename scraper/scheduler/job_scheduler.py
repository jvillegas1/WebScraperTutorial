"""
Módulo de programación de tareas automáticas.
Gestiona la ejecución periódica del scraping y detección de oportunidades.
"""

import time
from datetime import datetime
from typing import Optional, List, Callable
from pathlib import Path
import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from ..config import (
    SCHEDULER_CONFIG, DB_PATH, LOGS_DIR, DEBUG, DEFAULT_REGION
)
from ..regions import REGIONS, get_region_config, list_regions, get_scraping_operations
from ..parsers.property_parser import PropertyParser
from ..storage.database import Database
from ..storage.models import ScrapingLogModel
from ..sources import get_scraper_registry, get_scraper_class
from ..detection.opportunity_detector import OpportunityDetector
from ..alerts.alert_manager import AlertManager

logger = structlog.get_logger(__name__)


class JobScheduler:
    """
    Programador de tareas para el sistema de scraping.
    
    Funcionalidades:
    - Ejecución automática cada X horas
    - Ejecución manual bajo demanda
    - Logging de resultados
    - Manejo de errores con reintentos
    """
    
    def __init__(
        self,
        database: Optional[Database] = None,
        alert_manager: Optional[AlertManager] = None,
        config: Optional[dict] = None
    ):
        """
        Inicializa el scheduler.
        
        Args:
            database: Instancia de Database
            alert_manager: Instancia de AlertManager
            config: Configuración del scheduler
        """
        self.config = config or SCHEDULER_CONFIG
        self.db = database or Database(DB_PATH)
        self.alert_manager = alert_manager
        self.detector = OpportunityDetector(self.db)
        
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_listener(
            self._job_listener,
            EVENT_JOB_ERROR | EVENT_JOB_EXECUTED
        )
        
        self._is_running = False
        
        logger.info(
            "scheduler_initialized",
            scraping_interval_hours=self.config.get("scraping_interval_hours", 6)
        )
    
    def _job_listener(self, event):
        """Listener para eventos de jobs."""
        if event.exception:
            logger.error(
                "job_error",
                job_id=event.job_id,
                error=str(event.exception)
            )
        else:
            logger.debug(
                "job_executed",
                job_id=event.job_id,
                run_time=event.scheduled_run_time
            )
    
    def _get_active_scrapers(self, region: str = DEFAULT_REGION) -> List[str]:
        """Obtiene la lista de scrapers activos para una región."""
        region_config = get_region_config(region)
        registry = get_scraper_registry(region)
        return [
            name for name, active in region_config["active_sources"].items()
            if active and name in registry
        ]

    def run_scraper(
        self,
        source_name: str,
        region: str = DEFAULT_REGION,
        operations: Optional[List[str]] = None,
    ) -> ScrapingLogModel:
        """
        Ejecuta un scraper específico.
        
        Args:
            source_name: Nombre del portal a scrapear
            
        Returns:
            Log de la ejecución
        """
        log = ScrapingLogModel(
            source=f"{region}:{source_name}",
            status="running",
            fecha_ejecucion=datetime.now()
        )
        
        start_time = time.time()
        region_config = get_region_config(region)
        scraping_config = region_config["scraping"]
        
        try:
            scraper_class = get_scraper_class(region, source_name)
            if not scraper_class:
                raise ValueError(f"Scraper no encontrado: {region}/{source_name}")

            from ..geo.locations import get_scrape_targets

            scraping_config = dict(scraping_config)
            location_ids = scraping_config.get('location_ids')
            scrape_targets = get_scrape_targets(region, location_ids)
            scraping_config['scrape_targets'] = scrape_targets
            scraping_config['scope'] = 'national'
            if operations:
                scraping_config['operations'] = operations
            operations = get_scraping_operations(scraping_config)
            
            logger.info(
                "scraper_starting",
                source=source_name,
                region=region,
                locations=len(scrape_targets),
                operations=operations,
            )

            all_properties = []
            new_count = 0
            updated_count = 0

            with scraper_class(config=scraping_config) as scraper:
                for operation in operations:
                    op_norm = PropertyParser.normalize_operation(operation)
                    properties = list(scraper.scrape(
                        city=scraping_config.get("city", ""),
                        operation=op_norm,
                    ))
                    active_ids = []

                    for prop in properties:
                        prop.operacion = op_norm
                        property_id, action = self.db.upsert_property(prop)
                        active_ids.append(prop.id_externo)
                        all_properties.append(prop)

                        if action == 'inserted':
                            new_count += 1
                        elif action == 'updated':
                            updated_count += 1

                    self.db.mark_inactive_properties(
                        source_name, active_ids, region=region, operacion=op_norm
                    )

                    logger.info(
                        "scraper_operation_completed",
                        source=source_name,
                        region=region,
                        operation=op_norm,
                        found=len(properties),
                    )
            
            # Actualizar log
            log.status = "success"
            log.properties_found = len(all_properties)
            log.properties_new = new_count
            log.properties_updated = updated_count
            
            logger.info(
                "scraper_completed",
                source=source_name,
                found=len(all_properties),
                new=new_count,
                updated=updated_count,
                operations=operations,
            )
            
        except Exception as e:
            log.status = "error"
            log.error_message = str(e)
            
            logger.error(
                "scraper_failed",
                source=source_name,
                error=str(e)
            )
        
        finally:
            log.duration_seconds = time.time() - start_time
            self.db.log_scraping_run(log)
        
        return log
    
    def run_all_scrapers(
        self,
        region: Optional[str] = None,
        operations: Optional[List[str]] = None,
    ) -> List[ScrapingLogModel]:
        """
        Ejecuta todos los scrapers activos.
        Si region es None, ejecuta todas las regiones configuradas.
        """
        logs = []
        regions = [region] if region else list_regions()

        for current_region in regions:
            active_scrapers = self._get_active_scrapers(current_region)
            logger.info(
                "running_all_scrapers",
                region=current_region,
                active_count=len(active_scrapers),
                scrapers=active_scrapers
            )

            for source_name in active_scrapers:
                try:
                    log = self.run_scraper(source_name, region=current_region, operations=operations)
                    logs.append(log)
                except Exception as e:
                    logger.error(
                        "scraper_execution_failed",
                        region=current_region,
                        source=source_name,
                        error=str(e)
                    )

            self._detect_and_alert(current_region)

        return logs

    def _detect_and_alert(self, region: str = DEFAULT_REGION):
        """Detecta oportunidades y envía alertas para una región."""
        try:
            logger.info("detecting_opportunities", region=region)
            region_rules = get_region_config(region)["opportunity_rules"]
            detector = OpportunityDetector(self.db, rules=region_rules)
            properties = self.db.get_all_properties(region=region, only_active=True)
            property_ids = [p.id for p in properties]
            opportunities = detector.detect_opportunities(property_ids=property_ids)
            
            if opportunities and self.alert_manager:
                sent = self.alert_manager.process_new_opportunities(opportunities)
                logger.info(
                    "alerts_processed",
                    opportunities_found=len(opportunities),
                    alerts_sent=sent
                )
            
        except Exception as e:
            logger.error("opportunity_detection_failed", error=str(e))
    
    def run_opportunity_check(self, region: Optional[str] = None):
        """Ejecuta detección de oportunidades por región."""
        if region:
            self._detect_and_alert(region)
        else:
            for current_region in list_regions():
                self._detect_and_alert(current_region)
    
    def _scraping_job(self):
        """Job interno para scraping de Venezuela."""
        logger.info("scheduled_scraping_started", region="venezuela")
        self.run_all_scrapers(region="venezuela")
        logger.info("scheduled_scraping_completed", region="venezuela")
    
    def _opportunity_job(self):
        """Job interno para detección de oportunidades."""
        logger.info("scheduled_opportunity_check_started")
        self.run_opportunity_check()
        logger.info("scheduled_opportunity_check_completed")
    
    def start(self):
        """Inicia el scheduler con los jobs configurados."""
        if self._is_running:
            logger.warning("scheduler_already_running")
            return
        
        # Job de scraping
        scraping_interval = self.config.get("scraping_interval_hours", 6)
        self._scheduler.add_job(
            self._scraping_job,
            trigger=IntervalTrigger(hours=scraping_interval),
            id="scraping_job_ve",
            name="Scraping Venezuela",
            replace_existing=True
        )

        ar_interval = REGIONS["argentina"]["scraping_interval_hours"]
        self._scheduler.add_job(
            lambda: self.run_all_scrapers(region="argentina"),
            trigger=IntervalTrigger(hours=ar_interval),
            id="scraping_job_ar",
            name="Scraping Argentina",
            replace_existing=True
        )
        
        # Job de detección de oportunidades (más frecuente)
        opportunity_interval = self.config.get("opportunity_check_interval_hours", 1)
        self._scheduler.add_job(
            self._opportunity_job,
            trigger=IntervalTrigger(hours=opportunity_interval),
            id="opportunity_job",
            name="Detección de oportunidades",
            replace_existing=True
        )
        
        self._scheduler.start()
        self._is_running = True
        
        logger.info(
            "scheduler_started",
            scraping_interval_hours=scraping_interval,
            opportunity_interval_hours=opportunity_interval,
            jobs=len(self._scheduler.get_jobs())
        )
    
    def stop(self):
        """Detiene el scheduler."""
        if not self._is_running:
            return
        
        self._scheduler.shutdown(wait=True)
        self._is_running = False
        
        logger.info("scheduler_stopped")
    
    def run_now(self, include_scraping: bool = True, include_detection: bool = True):
        """
        Ejecuta manualmente los jobs.
        
        Args:
            include_scraping: Si ejecutar el scraping
            include_detection: Si ejecutar la detección de oportunidades
        """
        if include_scraping:
            self.run_all_scrapers()
        elif include_detection:
            self.run_opportunity_check()
    
    def get_status(self) -> dict:
        """
        Obtiene el estado actual del scheduler.
        
        Returns:
            Diccionario con información del estado
        """
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        
        return {
            "is_running": self._is_running,
            "jobs": jobs,
            "active_scrapers": {
                region: self._get_active_scrapers(region)
                for region in list_regions()
            },
        }
    
    def get_recent_logs(self, limit: int = 20) -> List[ScrapingLogModel]:
        """
        Obtiene los logs recientes de ejecución.
        
        Args:
            limit: Número máximo de logs
            
        Returns:
            Lista de logs
        """
        return self.db.get_recent_logs(limit)
    
    def add_custom_job(
        self,
        job_id: str,
        func: Callable,
        trigger: str = "interval",
        **trigger_args
    ):
        """
        Agrega un job personalizado.
        
        Args:
            job_id: ID único del job
            func: Función a ejecutar
            trigger: Tipo de trigger ("interval" o "cron")
            **trigger_args: Argumentos del trigger
        """
        if trigger == "interval":
            trigger_obj = IntervalTrigger(**trigger_args)
        elif trigger == "cron":
            trigger_obj = CronTrigger(**trigger_args)
        else:
            raise ValueError(f"Trigger no soportado: {trigger}")
        
        self._scheduler.add_job(
            func,
            trigger=trigger_obj,
            id=job_id,
            replace_existing=True
        )
        
        logger.info(
            "custom_job_added",
            job_id=job_id,
            trigger=trigger
        )
    
    def remove_job(self, job_id: str):
        """Elimina un job."""
        try:
            self._scheduler.remove_job(job_id)
            logger.info("job_removed", job_id=job_id)
        except Exception as e:
            logger.error("job_removal_failed", job_id=job_id, error=str(e))



