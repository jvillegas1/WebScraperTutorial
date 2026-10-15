"""
Scraper para RentaHouse Venezuela.
Requiere Playwright porque el contenido se carga con JavaScript.
URL: https://rentahouse.com.ve
"""

import re
import asyncio
from typing import List, Dict, Any, Optional, Generator
from bs4 import BeautifulSoup
from datetime import datetime
import structlog
import time

from .base_scraper import PlaywrightBaseScraper
from ..parsers.property_parser import Property, PropertyParser
from ..config import PORTAL_URLS

logger = structlog.get_logger(__name__)


class RentaHouseScraper(PlaywrightBaseScraper):
    """Scraper para RentaHouse Venezuela - requiere JavaScript."""
    
    name = "rentahouse"
    region = "venezuela"
    base_url = PORTAL_URLS.get("rentahouse", "https://rentahouse.com.ve")
    
    def _location_slug(self, city: str) -> str:
        loc = self.config.get('current_location')
        if loc:
            slug = (loc.get('slug') or {}).get('rentahouse') or (loc.get('slug') or {}).get('default', '')
            if slug:
                return slug.replace('-', '_')
        return city.lower().replace(" ", "_") if city else ""

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """Construye URL de búsqueda."""
        op = "venta" if operation.lower() in ["venta", "sale"] else "alquiler"
        city_slug = self._location_slug(city)
        if not city_slug:
            url = f"{self.base_url}/casa_en_{op}.html"
        else:
            url = f"{self.base_url}/casa_en_{op}_en_{city_slug}.html"
        if page > 1:
            url = f"{url}?page={page}"
        return url

    def _get_property_type_urls(self, city: str, operation: str) -> List[str]:
        """Genera URLs para diferentes tipos de propiedades."""
        op = "venta" if operation.lower() in ["venta", "sale"] else "alquiler"
        property_types = ["casa", "apartamento", "terreno", "townhouse"]
        city_slug = self._location_slug(city)
        if not city_slug:
            return [f"{self.base_url}/{pt}_en_{op}.html" for pt in property_types]
        return [f"{self.base_url}/{pt}_en_{op}_en_{city_slug}.html" for pt in property_types]
    
    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrae listados de una página de resultados."""
        listings = []
        seen_ids = set()
        
        page_text = soup.get_text()
        
        # Buscar todos los códigos RAH únicos
        rah_codes = list(set(re.findall(r'RAH[:\s]*VE\s*(\d+-\d+)', page_text, re.IGNORECASE)))
        logger.debug("rah_codes_found", count=len(rah_codes))
        
        for rah_code in rah_codes:
            if rah_code in seen_ids:
                continue
            seen_ids.add(rah_code)
            
            # Patrón para extraer información
            pattern = re.compile(
                rf'USD[\s\xa0]*([\d\.,]+).*?'
                rf'(Casa|Apartamento|Terreno).*?en\s+(Venta|Alquiler).*?'
                rf'([A-Za-z\s]+),\s*(\w+).*?'
                rf'RAH[:\s]*VE\s*{re.escape(rah_code)}',
                re.IGNORECASE | re.DOTALL
            )
            
            match = pattern.search(page_text)
            
            if match:
                try:
                    precio_str = match.group(1).replace('.', '').replace(',', '.')
                    precio = float(precio_str)
                    
                    # Contexto para extraer habitaciones, baños, metros
                    context = page_text[match.start():match.end()]
                    
                    # Metros cuadrados
                    metros_matches = re.findall(r'([\d\.,]+)\s*m2', context, re.IGNORECASE)
                    metros = None
                    if metros_matches:
                        try:
                            metros = float(metros_matches[0].replace('.', '').replace(',', '.'))
                        except ValueError:
                            pass
                    
                    # Números antes de m2 (habitaciones, baños, etc)
                    nums = re.findall(r'\b(\d+)\b', context[:200])  # Limitamos el contexto
                    habitaciones = int(nums[0]) if nums else None
                    banos = int(nums[1]) if len(nums) > 1 else None
                    
                    ubicacion = f"{match.group(4).strip()}, {match.group(5)}"
                    ubicacion = re.sub(r'\s+', ' ', ubicacion).strip()
                    
                    listings.append({
                        'id_externo': f"RAH-VE-{rah_code}",
                        'precio': precio,
                        'moneda': 'USD',
                        'tipo_raw': match.group(2),
                        'ubicacion': ubicacion,
                        'habitaciones': habitaciones,
                        'banos': banos,
                        'metros_construccion': metros,
                        'url': f"{self.base_url}",
                    })
                    
                    logger.debug("listing_extracted", id=f"RAH-VE-{rah_code}", precio=precio)
                    
                except (ValueError, IndexError) as e:
                    logger.debug("extraction_error", rah=rah_code, error=str(e))
        
        return listings
    
    def _parse_property_detail(self, raw_data: Dict[str, Any]) -> Optional[Property]:
        """Normaliza datos crudos a Property."""
        try:
            precio = raw_data.get('precio')
            if not precio or precio <= 0:
                return None
            
            tipo = PropertyParser.normalize_property_type(raw_data.get('tipo_raw', ''))
            ubicacion = PropertyParser.normalize_location(
                raw_data.get('ubicacion', ''),
                self.config.get('location_label', 'Venezuela'),
            )

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
            )
        except Exception as e:
            logger.error("normalization_error", error=str(e))
            return None
    
    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """Verifica si hay más páginas."""
        next_link = soup.find('a', string=re.compile(r'Siguiente', re.IGNORECASE))
        if next_link:
            return True
        
        pagination = soup.select('.pagination a, ul.pagination li a')
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
        """Ejecuta scraping con Playwright por localidad."""
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
                (location.get('slug') or {}).get('rentahouse')
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
            
            property_urls = self._get_property_type_urls(city, operation)
            
            for base_url in property_urls:
                page = 1
                max_pages = self.config.get('max_pages_per_source', 10)
                
                while page <= max_pages:
                    url = base_url if page == 1 else f"{base_url}?page={page}"
                    
                    logger.debug("fetching_url", url=url, page=page)
                    
                    soup = await self._get_soup_async(url)
                    
                    if soup is None:
                        break
                    
                    listings = self._parse_listing_page(soup)
                    
                    if not listings:
                        break
                    
                    logger.debug("page_scraped", url=url, listings=len(listings))
                    
                    for raw_data in listings:
                        try:
                            id_ext = raw_data.get('id_externo')
                            if id_ext and id_ext not in all_seen_ids:
                                all_seen_ids.add(id_ext)
                                
                                prop = self._parse_property_detail(raw_data)
                                if prop:
                                    is_valid, _ = PropertyParser.validate_property(prop)
                                    if is_valid:
                                        results.append(prop)
                        except Exception as e:
                            logger.error("property_error", error=str(e))
                    
                    if not self._has_next_page(soup, page):
                        break
                    
                    page += 1
                    
                    # Delay entre páginas
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
