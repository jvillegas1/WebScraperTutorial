"""
Scraper para InfoCasas Venezuela.
Portal con HTML estático, usa requests + BeautifulSoup.
"""

import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from datetime import datetime
import structlog

from .base_scraper import BaseScraper
from ..parsers.property_parser import Property, PropertyParser
from ..config import PORTAL_URLS

logger = structlog.get_logger(__name__)


class InfoCasasScraper(BaseScraper):
    """Scraper para InfoCasas Venezuela."""
    
    name = "infocasas"
    region = "venezuela"
    base_url = PORTAL_URLS.get("infocasas", "https://www.infocasas.com.ve")
    
    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """
        Construye URL de búsqueda para InfoCasas.
        
        Formato: https://www.infocasas.com.ve/venta/inmuebles/maracaibo/pagina-2
        """
        operation_map = {
            "venta": "venta",
            "alquiler": "alquiler",
            "rent": "alquiler",
            "sale": "venta",
        }
        city_slug = city.lower().replace(" ", "-") if city else ""

        scope = self.config.get("scope", "national")
        if scope == "national" or not city_slug:
            url = f"{self.base_url}/{op}/inmuebles/"
        else:
            url = f"{self.base_url}/{op}/inmuebles/{city_slug}"
        
        if page > 1:
            url = f"{url}/pagina-{page}"
        
        return url
    
    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrae listados de una página de resultados."""
        listings = []
        
        # Selectores para InfoCasas
        item_selectors = [
            '.property-item',
            '.listing-item',
            '.result-card',
            'article.property',
            '[data-property-id]',
            '.search-result-item',
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
        link = item.select_one('a[href*="/inmueble/"], a[href*="/propiedad/"], a.property-link')
        if not link:
            link = item.select_one('a')
        
        if link and link.get('href'):
            href = link['href']
            if not href.startswith('http'):
                href = f"{self.base_url}{href}"
            data['url'] = href
            
            # Extraer ID
            id_match = re.search(r'/(?:inmueble|propiedad)/(\d+)', href)
            if id_match:
                data['id_externo'] = f"IC-{id_match.group(1)}"
        
        if not data.get('url'):
            return None
        
        if not data.get('id_externo'):
            data_id = item.get('data-property-id') or item.get('data-id')
            if data_id:
                data['id_externo'] = f"IC-{data_id}"
            else:
                url_hash = hash(data['url']) % 10000000
                data['id_externo'] = f"IC-{url_hash}"
        
        # Título
        title_selectors = ['.property-title', 'h2', 'h3', '.title', '[class*="title"]']
        for selector in title_selectors:
            title = item.select_one(selector)
            if title:
                data['titulo'] = title.get_text(strip=True)
                break
        
        # Precio
        price_selectors = ['.property-price', '.price', '[class*="price"]', '.valor']
        for selector in price_selectors:
            price = item.select_one(selector)
            if price:
                data['precio_raw'] = price.get_text(strip=True)
                break
        
        # Ubicación
        location_selectors = ['.property-location', '.location', '.address', '.ubicacion']
        for selector in location_selectors:
            location = item.select_one(selector)
            if location:
                data['ubicacion'] = location.get_text(strip=True)
                break
        
        # Tipo de propiedad
        type_selectors = ['.property-type', '.tipo', '[class*="type"]']
        for selector in type_selectors:
            ptype = item.select_one(selector)
            if ptype:
                data['tipo_raw'] = ptype.get_text(strip=True)
                break
        
        # Características
        features = item.select('[class*="feature"], [class*="caracteristica"], .specs span')
        for feature in features:
            text = feature.get_text(strip=True).lower()
            if 'm²' in text or 'mts' in text or 'm2' in text:
                data['metros_raw'] = feature.get_text(strip=True)
            elif 'hab' in text or 'dorm' in text:
                data['habitaciones_raw'] = feature.get_text(strip=True)
            elif 'baño' in text:
                data['banos_raw'] = feature.get_text(strip=True)
            elif 'estac' in text or 'parking' in text:
                data['estacionamientos_raw'] = feature.get_text(strip=True)
        
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
            
            tipo_text = raw_data.get('tipo_raw', '') or raw_data.get('titulo', '')
            tipo_inmueble = PropertyParser.normalize_property_type(tipo_text)
            
            ubicacion = PropertyParser.normalize_location(
                raw_data.get('ubicacion', ''),
                self.config.get('location_label', 'Venezuela')
            )
            
            metros = PropertyParser.extract_area(raw_data.get('metros_raw', ''))
            habitaciones = PropertyParser.extract_number(raw_data.get('habitaciones_raw', ''))
            banos = PropertyParser.extract_number(raw_data.get('banos_raw', ''))
            estacionamientos = PropertyParser.extract_number(raw_data.get('estacionamientos_raw', ''))
            imagenes = [raw_data['imagen']] if raw_data.get('imagen') else []
            
            return Property(
                id_externo=raw_data['id_externo'],
                source=self.name,
                region=self.region,
                titulo=PropertyParser.clean_text(raw_data.get('titulo', '')),
                precio=precio,
                moneda=moneda,
                ubicacion=ubicacion,
                tipo_inmueble=tipo_inmueble,
                url=raw_data['url'],
                fecha_scraping=datetime.now(),
                metros_cuadrados=metros,
                habitaciones=habitaciones,
                banos=banos,
                estacionamientos=estacionamientos,
                imagenes=imagenes,
            )
            
        except Exception as e:
            logger.error("property_normalization_error", error=str(e))
            return None
    
    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """Verifica si hay más páginas."""
        # Buscar enlace de siguiente página
        next_link = soup.select_one(
            f'a[href*="pagina-{current_page + 1}"], '
            'a.next-page, '
            'a[rel="next"]'
        )
        
        return next_link is not None



