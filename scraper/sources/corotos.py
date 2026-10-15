"""
Scraper para Corotos.com.ve - Clasificados de Venezuela.
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


class CorotosScraper(BaseScraper):
    """Scraper para Corotos.com.ve."""
    
    name = "corotos"
    region = "venezuela"
    base_url = PORTAL_URLS.get("corotos", "https://www.corotos.com.ve")
    
    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """
        Construye URL de búsqueda para Corotos.
        
        Formato: https://www.corotos.com.ve/inmuebles/venta/maracaibo?page=2
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
            url = f"{self.base_url}/inmuebles/{op}/"
        else:
            url = f"{self.base_url}/inmuebles/{op}/{city_slug}"
        
        if page > 1:
            url = f"{url}?page={page}"
        
        return url
    
    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrae listados de una página de resultados."""
        listings = []
        
        # Selectores para Corotos
        item_selectors = [
            '.ad-card',
            '.listing-card',
            '.classified-item',
            'article.ad',
            '[data-ad-id]',
            '.item-list article',
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
        link = item.select_one('a[href*="/anuncio/"], a[href*="/ad/"], a.ad-link')
        if not link:
            link = item.select_one('a')
        
        if link and link.get('href'):
            href = link['href']
            if not href.startswith('http'):
                href = f"{self.base_url}{href}"
            data['url'] = href
            
            # Extraer ID de la URL
            id_match = re.search(r'/(?:anuncio|ad)/(\w+)', href)
            if id_match:
                data['id_externo'] = f"COR-{id_match.group(1)}"
        
        if not data.get('url'):
            return None
        
        if not data.get('id_externo'):
            data_id = item.get('data-ad-id') or item.get('data-id')
            if data_id:
                data['id_externo'] = f"COR-{data_id}"
            else:
                # Generar ID desde URL
                url_hash = hash(data['url']) % 10000000
                data['id_externo'] = f"COR-{url_hash}"
        
        # Título
        title_selectors = ['.ad-title', 'h2', 'h3', '.title', '[class*="title"]']
        for selector in title_selectors:
            title = item.select_one(selector)
            if title:
                data['titulo'] = title.get_text(strip=True)
                break
        
        # Precio
        price_selectors = ['.ad-price', '.price', '[class*="price"]', '.precio']
        for selector in price_selectors:
            price = item.select_one(selector)
            if price:
                data['precio_raw'] = price.get_text(strip=True)
                break
        
        # Ubicación
        location_selectors = ['.ad-location', '.location', '[class*="location"]', '.ubicacion']
        for selector in location_selectors:
            location = item.select_one(selector)
            if location:
                data['ubicacion'] = location.get_text(strip=True)
                break
        
        # Descripción breve
        desc_selectors = ['.ad-description', '.description', '.excerpt']
        for selector in desc_selectors:
            desc = item.select_one(selector)
            if desc:
                data['descripcion'] = desc.get_text(strip=True)[:500]
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
            
            # Tipo de inmueble desde título o descripción
            texto_completo = f"{raw_data.get('titulo', '')} {raw_data.get('descripcion', '')}"
            tipo_inmueble = PropertyParser.normalize_property_type(texto_completo)
            
            ubicacion = PropertyParser.normalize_location(
                raw_data.get('ubicacion', ''),
                self.config.get('location_label', 'Venezuela')
            )
            
            # Extraer características del título/descripción
            metros = PropertyParser.extract_area(texto_completo)
            habitaciones = None
            banos = None
            
            # Buscar habitaciones en texto
            hab_match = re.search(r'(\d+)\s*(?:hab|dorm|cuarto)', texto_completo, re.IGNORECASE)
            if hab_match:
                habitaciones = int(hab_match.group(1))
            
            # Buscar baños en texto
            bano_match = re.search(r'(\d+)\s*baño', texto_completo, re.IGNORECASE)
            if bano_match:
                banos = int(bano_match.group(1))
            
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
                descripcion=raw_data.get('descripcion'),
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
        # Buscar enlace de siguiente página
        next_link = soup.select_one('a[rel="next"], .pagination a.next, a:contains("Siguiente")')
        if next_link:
            return True
        
        # Verificar paginación numérica
        pagination = soup.select('.pagination a, .pager a')
        for link in pagination:
            href = link.get('href', '')
            if f'page={current_page + 1}' in href:
                return True
        
        return False



