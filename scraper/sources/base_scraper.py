"""
Clase base abstracta para todos los scrapers de portales inmobiliarios.
Define la interfaz común y funcionalidades compartidas.
"""

import time
import random
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Generator
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import structlog

from ..config import SCRAPING_CONFIG, USER_AGENTS, DEBUG
from ..parsers.property_parser import Property, PropertyParser

logger = structlog.get_logger(__name__)


class BaseScraper(ABC):
    """
    Clase base abstracta para scrapers de portales inmobiliarios.
    
    Implementa funcionalidades comunes:
    - Manejo de sesiones HTTP con reintentos
    - Headers con User-Agent rotativo
    - Delays entre requests
    - Logging estructurado
    - Manejo de errores
    
    Cada portal debe implementar:
    - name: Nombre identificador del portal
    - base_url: URL base del portal
    - scrape(): Método principal de scraping
    - _parse_listing(): Parser de cada listado
    """
    
    # Debe ser sobrescrito por cada scraper
    name: str = "base"
    base_url: str = ""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Inicializa el scraper con configuración opcional.
        
        Args:
            config: Diccionario de configuración que sobrescribe SCRAPING_CONFIG
        """
        self.config = {**SCRAPING_CONFIG, **(config or {})}
        self.session = self._create_session()
        self.parser = PropertyParser()
        self._request_count = 0
        self._start_time = None
        
        logger.info(
            "scraper_initialized",
            name=self.name,
            base_url=self.base_url
        )
    
    def _create_session(self) -> requests.Session:
        """
        Crea una sesión HTTP con reintentos automáticos.
        
        Returns:
            Sesión configurada con reintentos y timeouts
        """
        session = requests.Session()
        
        # Configurar reintentos
        retry_strategy = Retry(
            total=self.config['max_retries'],
            backoff_factor=self.config['retry_backoff_factor'],
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Genera headers HTTP con User-Agent rotativo.
        
        Returns:
            Diccionario de headers
        """
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
    
    def _delay(self):
        """Aplica delay entre requests con variación aleatoria."""
        base_delay = self.config['delay_between_requests']
        jitter = random.uniform(0, self.config.get('delay_jitter', 2))
        total_delay = base_delay + jitter
        
        if DEBUG:
            logger.debug("applying_delay", seconds=total_delay)
        
        time.sleep(total_delay)
    
    def _make_request(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Optional[requests.Response]:
        """
        Realiza una petición HTTP con manejo de errores.
        
        Args:
            url: URL a consultar
            method: Método HTTP (GET, POST)
            params: Parámetros de query string
            data: Datos para POST
            headers: Headers adicionales
            
        Returns:
            Response object o None si falla
        """
        # Aplicar delay (excepto primera request)
        if self._request_count > 0:
            self._delay()
        
        self._request_count += 1
        
        # Combinar headers
        request_headers = self._get_headers()
        if headers:
            request_headers.update(headers)
        
        try:
            logger.debug(
                "making_request",
                url=url,
                method=method,
                request_number=self._request_count
            )
            
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                headers=request_headers,
                timeout=self.config['timeout'],
            )
            
            response.raise_for_status()
            
            logger.debug(
                "request_success",
                url=url,
                status_code=response.status_code,
                content_length=len(response.content)
            )
            
            return response
            
        except requests.exceptions.HTTPError as e:
            logger.warning(
                "http_error",
                url=url,
                status_code=e.response.status_code if e.response else None,
                error=str(e)
            )
            return None
            
        except requests.exceptions.ConnectionError as e:
            logger.error("connection_error", url=url, error=str(e))
            return None
            
        except requests.exceptions.Timeout as e:
            logger.error("timeout_error", url=url, error=str(e))
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error("request_error", url=url, error=str(e))
            return None
    
    def _get_soup(self, url: str, **kwargs) -> Optional[BeautifulSoup]:
        """
        Obtiene y parsea una página HTML.
        
        Args:
            url: URL de la página
            **kwargs: Argumentos adicionales para _make_request
            
        Returns:
            BeautifulSoup object o None si falla
        """
        response = self._make_request(url, **kwargs)
        
        if response is None:
            return None
        
        try:
            return BeautifulSoup(response.content, 'lxml')
        except Exception as e:
            logger.error("parsing_error", url=url, error=str(e))
            return None
    
    @abstractmethod
    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """
        Construye la URL de búsqueda para el portal.
        
        Args:
            city: Ciudad de búsqueda
            operation: Tipo de operación (venta, alquiler)
            page: Número de página
            
        Returns:
            URL de búsqueda
        """
        pass
    
    @abstractmethod
    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Extrae los datos básicos de los listados de una página.
        
        Args:
            soup: BeautifulSoup de la página de listados
            
        Returns:
            Lista de diccionarios con datos crudos de cada listado
        """
        pass
    
    @abstractmethod
    def _parse_property_detail(self, raw_data: Dict[str, Any]) -> Optional[Property]:
        """
        Parsea y normaliza los datos de una propiedad.
        
        Args:
            raw_data: Datos crudos del listado
            
        Returns:
            Property normalizado o None si no es válido
        """
        pass
    
    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """
        Verifica si hay más páginas de resultados.
        Puede ser sobrescrito por cada portal.
        
        Args:
            soup: BeautifulSoup de la página actual
            current_page: Número de página actual
            
        Returns:
            True si hay más páginas
        """
        # Implementación por defecto: buscar enlaces de paginación
        # Cada portal puede sobrescribir esto
        return False

    def _resolve_scrape_targets(self) -> List[dict]:
        """Objetivos geográficos para esta ejecución."""
        from ..geo.locations import get_scrape_targets

        if self.config.get('scrape_targets'):
            return self.config['scrape_targets']
        if self.config.get('current_location'):
            return [self.config['current_location']]

        location_ids = self.config.get('location_ids')
        region = getattr(self, 'region', self.config.get('region', 'venezuela'))
        if self.config.get('scope') == 'national' or location_ids:
            return get_scrape_targets(region, location_ids)

        return [{
            'id': f'{region}_all',
            'region': region,
            'estado_provincia': '',
            'localidad': '',
            'sub_localidad': '',
            'slug': {'default': ''},
        }]

    def _pages_limit(self) -> int:
        """Páginas por localidad cuando hay muchos objetivos."""
        if self.config.get('current_location') and not self.config.get('scrape_targets'):
            return self.config.get(
                'max_pages_per_location',
                self.config.get('max_pages_per_source', 50),
            )
        targets = self._resolve_scrape_targets()
        if len(targets) > 1:
            return self.config.get('max_pages_per_location', 3)
        return self.config.get('max_pages_per_source', 50)

    def _resolve_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """URL de búsqueda según localidad activa o fallback del portal."""
        loc = self.config.get('current_location')
        if loc:
            from ..geo.url_builders import build_search_url
            region = getattr(self, 'region', self.config.get('region', 'venezuela'))
            return build_search_url(
                self.name, region, loc, self.base_url, operation, page
            )
        return self._build_search_url(city, operation, page)

    def _enrich_with_location(self, prop: Property, location: dict) -> Property:
        from ..geo.url_builders import apply_location_to_property
        apply_location_to_property(prop, location)
        return prop

    def _scrape_single_location(
        self,
        city: str,
        operation: str,
    ) -> Generator[Property, None, None]:
        """Scraping paginado para la localidad en config['current_location']."""
        page = 1
        max_pages = self._pages_limit()
        location = self.config.get('current_location') or {}
        loc_label = location.get('estado_provincia') or location.get('localidad') or city or 'national'

        logger.info(
            "scraping_location_started",
            scraper=self.name,
            location=loc_label,
            operation=operation,
        )

        while page <= max_pages:
            url = self._resolve_search_url(city, operation, page)
            soup = self._get_soup(url)

            if soup is None:
                logger.warning(
                    "page_fetch_failed",
                    scraper=self.name,
                    page=page,
                    url=url,
                    location=loc_label,
                )
                break

            listings = self._parse_listing_page(soup)

            if not listings:
                logger.info(
                    "no_more_listings",
                    scraper=self.name,
                    last_page=page,
                    location=loc_label,
                )
                break

            logger.debug(
                "listings_found",
                scraper=self.name,
                page=page,
                count=len(listings),
                location=loc_label,
            )

            for raw_data in listings:
                try:
                    prop = self._parse_property_detail(raw_data)

                    if prop is not None:
                        is_valid, errors = PropertyParser.validate_property(prop)

                        if is_valid:
                            prop.operacion = PropertyParser.normalize_operation(operation)
                            if location:
                                self._enrich_with_location(prop, location)
                            yield prop
                        elif DEBUG:
                            logger.debug(
                                "invalid_property",
                                scraper=self.name,
                                errors=errors,
                            )

                except Exception as e:
                    logger.error(
                        "property_parse_error",
                        scraper=self.name,
                        error=str(e),
                        raw_data=str(raw_data)[:200],
                    )

            if not self._has_next_page(soup, page):
                break

            page += 1
    
    def scrape(
        self,
        city: str = "Maracaibo",
        operation: str = "venta"
    ) -> Generator[Property, None, None]:
        """
        Ejecuta el scraping completo del portal.
        
        Args:
            city: Ciudad de búsqueda
            operation: Tipo de operación
            
        Yields:
            Property objects normalizados
        """
        self._start_time = datetime.now()
        self._request_count = 0
        total_found = 0
        targets = self._resolve_scrape_targets()
        saved_location = self.config.get('current_location')

        logger.info(
            "scraping_started",
            scraper=self.name,
            city=city,
            operation=operation,
            locations=len(targets),
        )

        for location in targets:
            loc_op = location.get("operacion")
            if loc_op and PropertyParser.normalize_operation(operation) != loc_op:
                continue
            self.config['current_location'] = location
            for prop in self._scrape_single_location(city, operation):
                total_found += 1
                yield prop

        if saved_location is not None:
            self.config['current_location'] = saved_location
        else:
            self.config.pop('current_location', None)
        
        duration = (datetime.now() - self._start_time).total_seconds()
        
        logger.info(
            "scraping_completed",
            scraper=self.name,
            city=city,
            operation=operation,
            locations=len(targets),
            total_properties=total_found,
            total_requests=self._request_count,
            duration_seconds=duration
        )
    
    def test_connection(self) -> bool:
        """
        Prueba la conexión al portal.
        
        Returns:
            True si la conexión es exitosa
        """
        response = self._make_request(self.base_url)
        return response is not None and response.status_code == 200
    
    def close(self):
        """Cierra la sesión HTTP."""
        self.session.close()
        logger.debug("session_closed", scraper=self.name)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class PlaywrightBaseScraper(BaseScraper):
    """
    Clase base para scrapers que requieren JavaScript (contenido dinámico).
    Usa Playwright en lugar de requests.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Inicializa el scraper con Playwright."""
        super().__init__(config)
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
    
    async def _init_browser(self):
        """Inicializa el navegador Playwright con contexto anti-detección."""
        import random
        from playwright.async_api import async_playwright
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ],
        )
        self._context = await self._browser.new_context(
            locale='es-AR',
            timezone_id='America/Argentina/Buenos_Aires',
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True,
            extra_http_headers=self._get_headers(),
        )
        self._page = await self._context.new_page()
        await self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        
        logger.info("playwright_browser_initialized", scraper=self.name)
    
    async def _close_browser(self):
        """Cierra el navegador Playwright."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        
        logger.debug("playwright_browser_closed", scraper=self.name)
    
    async def _get_page_content(self, url: str) -> Optional[str]:
        """
        Obtiene el contenido de una página usando Playwright con reintentos.
        """
        import asyncio

        if self._page is None:
            await self._init_browser()
        
        if self._request_count > 0:
            self._delay()
        
        self._request_count += 1
        
        timeout_ms = self.config.get('timeout', 45) * 1000
        wait_until = self.config.get('playwright_wait_until', 'domcontentloaded')
        max_attempts = self.config.get('max_retries', 3)
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    await asyncio.sleep(min(2 ** attempt, 8))
                    logger.debug(
                        "playwright_retry",
                        url=url,
                        attempt=attempt + 1,
                        scraper=self.name,
                    )

                response = await self._page.goto(
                    url,
                    wait_until=wait_until,
                    timeout=timeout_ms,
                )

                if response and response.status >= 400:
                    logger.warning(
                        "playwright_http_status",
                        url=url,
                        status=response.status,
                        scraper=self.name,
                    )

                await self._page.wait_for_timeout(
                    self.config.get('playwright_render_wait_ms', 1500)
                )
                content = await self._page.content()
                
                logger.debug(
                    "playwright_page_loaded",
                    url=url,
                    content_length=len(content),
                    scraper=self.name,
                )
                
                return content
                
            except Exception as e:
                error_msg = str(e)
                is_last = attempt == max_attempts - 1
                log_fn = logger.error if is_last else logger.warning
                log_fn(
                    "playwright_error",
                    url=url,
                    error=error_msg,
                    attempt=attempt + 1,
                    scraper=self.name,
                )
                if is_last:
                    return None
        
        return None
    
    async def _get_soup_async(self, url: str) -> Optional[BeautifulSoup]:
        """
        Obtiene y parsea una página HTML usando Playwright.
        
        Args:
            url: URL de la página
            
        Returns:
            BeautifulSoup object o None si falla
        """
        content = await self._get_page_content(url)
        
        if content is None:
            return None
        
        try:
            return BeautifulSoup(content, 'lxml')
        except Exception as e:
            logger.error("parsing_error", url=url, error=str(e))
            return None

    def scrape(
        self,
        city: str = "",
        operation: str = "venta",
    ) -> Generator[Property, None, None]:
        """Scraping con Playwright iterando por localidades geográficas."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _async_scrape_all() -> List[Property]:
            await self._init_browser()
            results: List[Property] = []
            try:
                self._start_time = datetime.now()
                self._request_count = 0
                targets = self._resolve_scrape_targets()
                saved_location = self.config.get('current_location')

                logger.info(
                    "scraping_started",
                    scraper=self.name,
                    city=city,
                    operation=operation,
                    locations=len(targets),
                )

                for location in targets:
                    loc_op = location.get("operacion")
                    if loc_op and PropertyParser.normalize_operation(operation) != loc_op:
                        continue
                    self.config['current_location'] = location
                    page = 1
                    max_pages = self._pages_limit()
                    loc_label = (
                        location.get('estado_provincia')
                        or location.get('sub_localidad')
                        or city
                        or 'national'
                    )

                    while page <= max_pages:
                        url = self._resolve_search_url(city, operation, page)
                        soup = await self._get_soup_async(url)

                        if soup is None:
                            logger.warning(
                                "page_fetch_failed",
                                scraper=self.name,
                                page=page,
                                location=loc_label,
                            )
                            break

                        listings = self._parse_listing_page(soup)
                        if not listings:
                            logger.info(
                                "no_listings_on_page",
                                scraper=self.name,
                                page=page,
                                location=loc_label,
                                url=url,
                            )
                            break

                        page_valid = 0
                        for raw_data in listings:
                            try:
                                prop = self._parse_property_detail(raw_data)
                                if prop:
                                    valid, errors = PropertyParser.validate_property(prop)
                                    if valid:
                                        prop.operacion = PropertyParser.normalize_operation(operation)
                                        if location:
                                            self._enrich_with_location(prop, location)
                                        results.append(prop)
                                        page_valid += 1
                                    elif self.name == "zonaprop":
                                        logger.debug(
                                            "zonaprop_invalid_property",
                                            errors=errors,
                                            url=raw_data.get("url"),
                                        )
                            except Exception as e:
                                logger.error(
                                    "property_parse_error",
                                    scraper=self.name,
                                    error=str(e),
                                )
                        logger.info(
                            "listings_parsed",
                            scraper=self.name,
                            page=page,
                            location=loc_label,
                            raw=len(listings),
                            valid=page_valid,
                        )

                        if not self._has_next_page(soup, page):
                            break
                        page += 1

                if saved_location is not None:
                    self.config['current_location'] = saved_location
                else:
                    self.config.pop('current_location', None)

                duration = (datetime.now() - self._start_time).total_seconds()
                logger.info(
                    "scraping_completed",
                    scraper=self.name,
                    locations=len(targets),
                    total_properties=len(results),
                    duration_seconds=duration,
                )
                return results
            finally:
                await self._close_browser()

        for prop in loop.run_until_complete(_async_scrape_all()):
            yield prop

