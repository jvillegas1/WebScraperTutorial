"""
Scraper para RE/MAX Venezuela.
URL: https://www.remax.com.ve
Requiere Playwright porque el contenido se carga con JavaScript.
"""

import re
import asyncio
from typing import List, Dict, Any, Optional, Generator
from bs4 import BeautifulSoup
from datetime import datetime
import structlog

from .base_scraper import PlaywrightBaseScraper
from ..parsers.property_parser import Property, PropertyParser
from ..config import PORTAL_URLS

logger = structlog.get_logger(__name__)


class RemaxScraper(PlaywrightBaseScraper):
    """Scraper para RE/MAX Venezuela."""
    
    name = "remax"
    region = "venezuela"
    base_url = PORTAL_URLS.get("remax", "https://www.remax.com.ve")
    
    def _location_ubi(self, city: str) -> str:
        loc = self.config.get('current_location')
        if loc:
            slug = (loc.get('slug') or {}).get('remax') or (loc.get('slug') or {}).get('default', '')
            if slug:
                return slug.replace('-', '+')
        scope = self.config.get("scope", "national")
        if scope == "national" or not city:
            return "Venezuela"
        return f"{city.replace(' ', '+')}%2C+Zulia%2C+VEN"

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """Construye URL de búsqueda para RE/MAX."""
        op = "venta" if operation.lower() in ["venta", "sale"] else "alquiler"
        ubi = self._location_ubi(city)
        url = f"{self.base_url}/inmuebles/casa-o-townhouse/{op}?ubi={ubi}"
        if page > 1:
            url = f"{url}&pagina={page}"
        return url

    def _get_search_urls_for_types(self, city: str, operation: str) -> List[str]:
        """Genera URLs para diferentes tipos de propiedades."""
        op = "venta" if operation.lower() in ["venta", "sale"] else "alquiler"
        ubi = self._location_ubi(city)
        
        property_types = [
            "casa-o-townhouse",
            "apartamento",
            "terreno",
            "local-comercial",
            "oficina",
        ]
        
        return [f"{self.base_url}/inmuebles/{ptype}/{op}?ubi={ubi}" for ptype in property_types]
    
    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrae listados de una página de RE/MAX."""
        listings = []
        seen_ids = set()
        
        page_text = soup.get_text()
        
        # Buscar bloques individuales de propiedades
        # Cada propiedad tiene: Precio $ XXX.XXX ... Código RE/MAX: XXXXXX
        
        # Primero encontrar todos los códigos RE/MAX con su contexto
        # Patrón: buscar desde $ PRECIO hasta el código RE/MAX
        property_blocks = re.findall(
            r'\$\s*([\d\.,]+).*?'  # Precio
            r'(?:RE/MAX[:\s*]*|Código\s*RE/MAX[:\s*]*)(\d{6})',  # Código (6 dígitos)
            page_text,
            re.IGNORECASE | re.DOTALL
        )
        
        logger.debug("remax_blocks_found", count=len(property_blocks))
        
        for match in property_blocks:
            try:
                precio_str = match[0]
                code = match[1]
                
                if code in seen_ids:
                    continue
                seen_ids.add(code)
                
                # Limpiar precio
                precio_str = precio_str.replace('.', '').replace(',', '.')
                precio = float(precio_str)
                
                if precio <= 0:
                    continue
                
                listings.append({
                    'id_externo': f"REMAX-{code}",
                    'precio': precio,
                    'moneda': 'USD',
                    'url': f"{self.base_url}/inmueble/{code}",
                })
                
                logger.debug("listing_extracted", id=f"REMAX-{code}", precio=precio)
                
            except (ValueError, IndexError) as e:
                logger.debug("extraction_error", error=str(e))
        
        # Si no encontramos con el patrón, intentar método alternativo
        if not listings:
            listings = self._extract_from_structured_html(soup, seen_ids)
        
        return listings
    
    def _extract_from_structured_html(self, soup: BeautifulSoup, seen_ids: set) -> List[Dict[str, Any]]:
        """Extrae propiedades de la estructura HTML."""
        listings = []
        
        # Buscar elementos que contengan código RE/MAX
        code_elements = soup.find_all(string=re.compile(r'RE/MAX.*?\d{6}', re.IGNORECASE))
        
        for elem in code_elements:
            try:
                # Extraer código
                code_match = re.search(r'(\d{6})', elem)
                if not code_match:
                    continue
                
                code = code_match.group(1)
                if code in seen_ids:
                    continue
                seen_ids.add(code)
                
                # Buscar contenedor padre
                parent = elem.find_parent(['div', 'article', 'li', 'section'])
                if not parent:
                    continue
                
                # Buscar hasta 5 niveles arriba para encontrar el precio
                for _ in range(5):
                    parent_text = parent.get_text()
                    price_match = re.search(r'\$\s*([\d\.,]+)', parent_text)
                    if price_match:
                        break
                    parent = parent.find_parent(['div', 'article', 'li', 'section'])
                    if not parent:
                        break
                
                if not price_match:
                    continue
                
                precio_str = price_match.group(1).replace('.', '').replace(',', '.')
                precio = float(precio_str)
                
                if precio <= 0:
                    continue
                
                listings.append({
                    'id_externo': f"REMAX-{code}",
                    'precio': precio,
                    'moneda': 'USD',
                    'url': f"{self.base_url}/inmueble/{code}",
                })
                
            except Exception as e:
                logger.debug("html_extraction_error", error=str(e))
        
        return listings
    
    def _extract_type_from_url(self, url: str) -> str:
        """Extrae el tipo de inmueble de la URL."""
        if "casa-o-townhouse" in url:
            return "casa"
        elif "apartamento" in url:
            return "apartamento"
        elif "terreno" in url:
            return "terreno"
        elif "local-comercial" in url:
            return "local"
        elif "oficina" in url:
            return "oficina"
        return "otro"
    
    def _parse_property_detail(self, raw_data: Dict[str, Any], tipo: str = "otro") -> Optional[Property]:
        """Normaliza datos crudos a Property."""
        try:
            precio = raw_data.get('precio')
            if not precio or precio <= 0:
                return None
            
            ubicacion = self.config.get('location_label', 'Venezuela')
            titulo = f"{tipo.capitalize()} en Venta - {ubicacion}"

            return Property(
                id_externo=raw_data['id_externo'],
                source=self.name,
                region=self.region,
                titulo=titulo,
                precio=precio,
                moneda=raw_data.get('moneda', 'USD'),
                ubicacion=ubicacion,
                tipo_inmueble=tipo,
                url=raw_data['url'],
                fecha_scraping=datetime.now(),
                metros_cuadrados=raw_data.get('metros_construccion'),
                habitaciones=raw_data.get('habitaciones'),
                banos=raw_data.get('banos'),
                estacionamientos=raw_data.get('estacionamientos'),
            )
        except Exception as e:
            logger.error("normalization_error", error=str(e))
            return None
    
    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """Verifica si hay más páginas."""
        # Buscar enlace a siguiente página o ícono de navegación
        page_text = soup.get_text()
        
        # Buscar "chevron_right" o número de página siguiente
        if 'chevron_right' in page_text:
            return True
        
        # Buscar si existe la página siguiente en la paginación
        if f'pagina={current_page + 1}' in str(soup):
            return True
        
        # Verificar paginación numérica
        pagination = soup.select('nav a, .pagination a, [class*="page"] a')
        for link in pagination:
            text = link.get_text(strip=True)
            if text == str(current_page + 1):
                return True
        
        return False
    
    def scrape(
        self,
        city: str = "",
        operation: str = "venta"
    ) -> Generator[Property, None, None]:
        """Ejecuta el scraping con Playwright por localidad."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        targets = self._resolve_scrape_targets()
        saved_location = self.config.get('current_location')

        for location in targets:
            self.config['current_location'] = location
            city_slug = (
                (location.get('slug') or {}).get('remax')
                or (location.get('slug') or {}).get('default')
                or city
            )
            results = loop.run_until_complete(self._async_scrape(city_slug, operation))
            for prop in results:
                if location:
                    self._enrich_with_location(prop, location)
                yield prop

        if saved_location is not None:
            self.config['current_location'] = saved_location
        else:
            self.config.pop('current_location', None)
    
    async def _async_scrape(self, city: str, operation: str) -> List[Property]:
        """Scraping asíncrono con Playwright."""
        results = []
        all_seen_ids = set()
        
        self._start_time = datetime.now()
        self._request_count = 0
        
        logger.info("scraping_started", scraper=self.name, city=city, operation=operation)
        
        try:
            await self._init_browser()
            
            search_urls = self._get_search_urls_for_types(city, operation)
            
            for base_url in search_urls:
                tipo = self._extract_type_from_url(base_url)
                page = 1
                max_pages = min(self.config.get('max_pages_per_source', 10), 6)  # RE/MAX tiene ~6 páginas
                
                while page <= max_pages:
                    url = base_url if page == 1 else f"{base_url}&pagina={page}"
                    
                    logger.debug("fetching_url", url=url, page=page, tipo=tipo)
                    
                    soup = await self._get_soup_async(url)
                    
                    if soup is None:
                        break
                    
                    listings = self._parse_listing_page(soup)
                    
                    if not listings:
                        break
                    
                    logger.debug("page_scraped", url=url, listings=len(listings))
                    
                    new_count = 0
                    for raw_data in listings:
                        try:
                            id_ext = raw_data.get('id_externo')
                            if id_ext and id_ext not in all_seen_ids:
                                all_seen_ids.add(id_ext)
                                
                                prop = self._parse_property_detail(raw_data, tipo)
                                if prop:
                                    is_valid, errors = PropertyParser.validate_property(prop)
                                    if is_valid:
                                        results.append(prop)
                                        new_count += 1
                                    else:
                                        logger.debug("validation_failed", id=id_ext, errors=errors)
                        except Exception as e:
                            logger.error("property_error", error=str(e))
                    
                    logger.debug("new_properties", count=new_count)
                    
                    if not self._has_next_page(soup, page):
                        break
                    
                    page += 1
                    await asyncio.sleep(self.config.get('delay_between_requests', 3))
            
        finally:
            await self._close_browser()
        
        duration = (datetime.now() - self._start_time).total_seconds()
        logger.info(
            "scraping_completed",
            scraper=self.name,
            total_properties=len(results),
            duration_seconds=duration
        )
        
        return results
