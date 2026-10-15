"""
Scraper para OLX Venezuela.
Portal con contenido dinámico, usa Playwright.
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


class OLXScraper(PlaywrightBaseScraper):
    """Scraper para OLX Venezuela."""
    
    name = "olx"
    region = "venezuela"
    base_url = PORTAL_URLS.get("olx", "https://www.olx.com.ve")
    
    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """
        Construye URL de búsqueda para OLX.
        
        Formato: https://www.olx.com.ve/inmuebles/venta/maracaibo?page=2
        """
        operation_map = {
            "venta": "venta",
            "alquiler": "alquiler",
            "rent": "alquiler",
            "sale": "venta",
        }
        city_slug = city.lower().replace(" ", "-") if city else ""
        op = operation_map.get(operation.lower(), "venta")

        scope = self.config.get("scope", "national")
        if scope == "national" or not city_slug:
            url = f"{self.base_url}/inmuebles/venta/"
        else:
            url = f"{self.base_url}/inmuebles/{city_slug}_g"
        
        params = []
        if op == "venta":
            params.append("filter=venta")
        elif op == "alquiler":
            params.append("filter=alquiler")
        
        if page > 1:
            params.append(f"page={page}")
        
        if params:
            url = f"{url}?{'&'.join(params)}"
        
        return url
    
    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrae listados de una página de resultados."""
        listings = []
        
        # Selectores para OLX (pueden variar)
        item_selectors = [
            '[data-aut-id="itemBox"]',
            '.EIR5N',  # Clase típica de OLX
            '.IKo3_',
            'li[data-testid="ad-item"]',
            '.ad-listing-item',
        ]
        
        items = []
        for selector in item_selectors:
            items = soup.select(selector)
            if items:
                break
        
        for item in items:
            try:
                listing = self._extract_listing_data(item)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.debug("listing_extraction_error", error=str(e))
        
        return listings
    
    def _extract_listing_data(self, item: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Extrae datos crudos de un elemento de listado."""
        data = {}
        
        # URL del anuncio
        link = item.select_one('a[href*="/item/"], a[href*="/iid-"]')
        if not link:
            link = item.select_one('a')
        
        if link and link.get('href'):
            href = link['href']
            if not href.startswith('http'):
                href = f"{self.base_url}{href}"
            data['url'] = href
            
            # Extraer ID
            id_match = re.search(r'iid-(\d+)', href) or re.search(r'/item/(\w+)', href)
            if id_match:
                data['id_externo'] = f"OLX-{id_match.group(1)}"
        
        if not data.get('url'):
            return None
        
        if not data.get('id_externo'):
            url_hash = hash(data['url']) % 10000000
            data['id_externo'] = f"OLX-{url_hash}"
        
        # Título
        title_selectors = ['[data-aut-id="itemTitle"]', '.title', 'h2', 'h3', '[class*="title"]']
        for selector in title_selectors:
            title = item.select_one(selector)
            if title:
                data['titulo'] = title.get_text(strip=True)
                break
        
        # Precio
        price_selectors = ['[data-aut-id="itemPrice"]', '.price', '[class*="price"]']
        for selector in price_selectors:
            price = item.select_one(selector)
            if price:
                data['precio_raw'] = price.get_text(strip=True)
                break
        
        # Ubicación
        location_selectors = ['[data-aut-id="item-location"]', '.location', '[class*="location"]']
        for selector in location_selectors:
            location = item.select_one(selector)
            if location:
                data['ubicacion'] = location.get_text(strip=True)
                break
        
        # Imagen
        img = item.select_one('img')
        if img:
            data['imagen'] = img.get('data-src') or img.get('src')
        
        return data
    
    def _parse_property_detail(self, raw_data: Dict[str, Any]) -> Optional[Property]:
        """Normaliza los datos crudos a un objeto Property."""
        try:
            precio, moneda = PropertyParser.normalize_price(raw_data.get('precio_raw', ''))
            if precio is None:
                return None
            
            titulo = raw_data.get('titulo', '')
            tipo_inmueble = PropertyParser.normalize_property_type(titulo)
            
            ubicacion = PropertyParser.normalize_location(
                raw_data.get('ubicacion', ''),
                self.config.get('location_label', 'Venezuela')
            )
            
            # Extraer características del título
            metros = PropertyParser.extract_area(titulo)
            
            hab_match = re.search(r'(\d+)\s*(?:hab|dorm|cuarto)', titulo, re.IGNORECASE)
            habitaciones = int(hab_match.group(1)) if hab_match else None
            
            bano_match = re.search(r'(\d+)\s*baño', titulo, re.IGNORECASE)
            banos = int(bano_match.group(1)) if bano_match else None
            
            imagenes = [raw_data['imagen']] if raw_data.get('imagen') else []
            
            return Property(
                id_externo=raw_data['id_externo'],
                source=self.name,
                region=self.region,
                titulo=PropertyParser.clean_text(titulo),
                precio=precio,
                moneda=moneda,
                ubicacion=ubicacion,
                tipo_inmueble=tipo_inmueble,
                url=raw_data['url'],
                fecha_scraping=datetime.now(),
                metros_cuadrados=metros,
                habitaciones=habitaciones,
                banos=banos,
                imagenes=imagenes,
            )
            
        except Exception as e:
            logger.error("property_normalization_error", error=str(e))
            return None
    
    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """Verifica si hay más páginas."""
        next_selectors = [
            f'a[href*="page={current_page + 1}"]',
            'button[data-aut-id="btnLoadMore"]',
            'a[data-aut-id="btnNext"]',
        ]
        
        for selector in next_selectors:
            if soup.select_one(selector):
                return True
        
        return False
    
