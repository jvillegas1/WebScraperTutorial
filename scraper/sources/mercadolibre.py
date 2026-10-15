"""
Scraper para MercadoLibre Venezuela - Inmuebles.
Portal con contenido dinámico, usa Playwright para mejor compatibilidad.
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


class MercadoLibreScraper(PlaywrightBaseScraper):
    """Scraper para MercadoLibre Venezuela - Inmuebles."""
    
    name = "mercadolibre"
    region = "venezuela"
    # URL actualizada - MercadoLibre ahora usa listado.mercadolibre.com.ve
    base_url = "https://listado.mercadolibre.com.ve"
    
    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """
        Construye URL de búsqueda para MercadoLibre.
        
        Formatos válidos:
        - https://listado.mercadolibre.com.ve/inmuebles/casas/venta/zulia/maracaibo/
        - https://listado.mercadolibre.com.ve/inmuebles/venta/zulia/
        - https://listado.mercadolibre.com.ve/inmuebles/casas-en-venta-maracaibo
        """
        city_slug = city.lower().replace(" ", "-") if city else ""
        
        operation_map = {
            "venta": "venta",
            "alquiler": "alquiler",
            "rent": "alquiler",
            "sale": "venta",
        }
        op = operation_map.get(operation.lower(), "venta")
        
        scope = self.config.get("scope", "national")
        if scope == "national" or not city_slug:
            base = f"{self.base_url}/inmuebles/{op}/"
        else:
            base = f"{self.base_url}/inmuebles/{op}/zulia/{city_slug}"
        
        if page > 1:
            # MercadoLibre usa _Desde_X donde X es (page-1)*48 + 1
            offset = (page - 1) * 48 + 1
            base = f"{base}_Desde_{offset}"
        
        return base
    
    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrae listados de una página de resultados de MercadoLibre."""
        listings = []
        
        # Selectores actualizados de MercadoLibre (2024-2025)
        item_selectors = [
            'div.ui-search-result__content-wrapper',
            'div.ui-search-result__wrapper',
            'li.ui-search-layout__item',
            'div.poly-card__content',
            'article.poly-card',
            'div[class*="ui-search-result"]',
        ]
        
        items = []
        for selector in item_selectors:
            items = soup.select(selector)
            if items:
                logger.debug("selector_found", selector=selector, count=len(items))
                break
        
        if not items:
            # Intentar buscar cualquier enlace a inmuebles
            all_links = soup.select('a[href*="/MLV-"]')
            logger.debug("fallback_links_found", count=len(all_links))
            for link in all_links:
                parent = link.find_parent(['div', 'li', 'article'])
                if parent and parent not in items:
                    items.append(parent)
        
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
        
        # URL del anuncio - buscar enlaces con ID de MercadoLibre Venezuela (MLV)
        link_selectors = [
            'a[href*="/MLV-"]',
            'a.ui-search-link',
            'a.ui-search-result__link',
            'a.poly-component__title',
            'a[class*="item__link"]',
        ]
        
        link = None
        for selector in link_selectors:
            link = item.select_one(selector)
            if link and link.get('href'):
                break
        
        if link and link.get('href'):
            href = link['href']
            # Limpiar parámetros de tracking
            if '?' in href:
                href = href.split('?')[0]
            if '#' in href:
                href = href.split('#')[0]
            data['url'] = href
            
            # Extraer ID de la URL (MLV-XXXXXXX)
            id_match = re.search(r'MLV-?(\d+)', href)
            if id_match:
                data['id_externo'] = f"MLV-{id_match.group(1)}"
        
        if not data.get('url') or not data.get('id_externo'):
            return None
        
        # Título - múltiples selectores
        title_selectors = [
            'h2.ui-search-item__title',
            'h2.poly-component__title',
            'h2[class*="title"]',
            'a.poly-component__title',
            'h2',
            'h3',
            '.ui-search-item__group__element--title',
        ]
        
        for selector in title_selectors:
            title = item.select_one(selector)
            if title:
                data['titulo'] = title.get_text(strip=True)
                break
        
        # Precio - múltiples selectores
        price_selectors = [
            '.andes-money-amount__fraction',
            '.ui-search-price__second-line .andes-money-amount__fraction',
            'span[class*="price"] .andes-money-amount__fraction',
            '.poly-price__current .andes-money-amount__fraction',
            '[class*="money-amount__fraction"]',
        ]
        
        for selector in price_selectors:
            price_elem = item.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Buscar símbolo de moneda
                symbol_elem = item.select_one('.andes-money-amount__currency-symbol')
                symbol = symbol_elem.get_text(strip=True) if symbol_elem else "$"
                data['precio_raw'] = f"{symbol} {price_text}"
                break
        
        # Ubicación
        location_selectors = [
            '.ui-search-item__group__element--location',
            '.ui-search-item__location',
            '.poly-component__location',
            '[class*="location"]',
            '.ui-search-item__group--location',
        ]
        
        for selector in location_selectors:
            location = item.select_one(selector)
            if location:
                data['ubicacion'] = location.get_text(strip=True)
                break
        
        # Atributos (metros, habitaciones, baños)
        attr_selectors = [
            '.ui-search-card-attributes__attribute',
            '.ui-search-item__attributes-list li',
            '.poly-attributes-list__item',
            '[class*="attributes"]',
        ]
        
        for selector in attr_selectors:
            attrs = item.select(selector)
            for attr in attrs:
                attr_text = attr.get_text(strip=True).lower()
                if 'm²' in attr_text or 'mts' in attr_text or 'm2' in attr_text:
                    data['metros_raw'] = attr.get_text(strip=True)
                elif 'hab' in attr_text or 'dorm' in attr_text or 'cuarto' in attr_text:
                    data['habitaciones_raw'] = attr.get_text(strip=True)
                elif 'baño' in attr_text:
                    data['banos_raw'] = attr.get_text(strip=True)
        
        # Imagen
        img_selectors = [
            'img.ui-search-result-image__element',
            'img.poly-component__picture',
            'img[class*="image"]',
            'img',
        ]
        
        for selector in img_selectors:
            img = item.select_one(selector)
            if img:
                src = img.get('data-src') or img.get('src') or img.get('data-srcset')
                if src and 'http' in src:
                    data['imagen'] = src.split()[0]  # Tomar primera URL si hay srcset
                    break
        
        return data if data.get('id_externo') else None
    
    def _parse_property_detail(self, raw_data: Dict[str, Any]) -> Optional[Property]:
        """Normaliza los datos crudos a un objeto Property."""
        try:
            # Precio
            precio, moneda = PropertyParser.normalize_price(raw_data.get('precio_raw', ''))
            if precio is None or precio <= 0:
                logger.debug("invalid_price", raw=raw_data.get('precio_raw'))
                return None
            
            # Tipo de inmueble desde el título
            titulo = raw_data.get('titulo', '')
            tipo_inmueble = PropertyParser.normalize_property_type(titulo)
            
            # Ubicación
            ubicacion = PropertyParser.normalize_location(
                raw_data.get('ubicacion', ''),
                self.config.get('location_label', 'Venezuela')
            )
            
            # Metros cuadrados
            metros = PropertyParser.extract_area(raw_data.get('metros_raw', '') or titulo)
            
            # Habitaciones
            habitaciones = PropertyParser.extract_number(raw_data.get('habitaciones_raw', ''))
            if not habitaciones:
                # Intentar extraer del título
                hab_match = re.search(r'(\d+)\s*(?:hab|dorm|cuarto)', titulo, re.IGNORECASE)
                if hab_match:
                    habitaciones = int(hab_match.group(1))
            
            # Baños
            banos = PropertyParser.extract_number(raw_data.get('banos_raw', ''))
            if not banos:
                bano_match = re.search(r'(\d+)\s*baño', titulo, re.IGNORECASE)
                if bano_match:
                    banos = int(bano_match.group(1))
            
            # Imágenes
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
            logger.error("property_normalization_error", error=str(e), raw_data=raw_data)
            return None
    
    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """Verifica si hay más páginas en MercadoLibre."""
        # Buscar botón de siguiente página
        next_selectors = [
            'a.andes-pagination__link[title="Siguiente"]',
            'li.andes-pagination__button--next a',
            'a[title="Siguiente"]',
            f'a[href*="_Desde_{(current_page) * 48 + 1}"]',
        ]
        
        for selector in next_selectors:
            next_btn = soup.select_one(selector)
            if next_btn:
                return True
        
        # Verificar paginación numérica
        pagination = soup.select_one('.andes-pagination')
        if pagination:
            current = pagination.select_one('.andes-pagination__button--current')
            all_pages = pagination.select('.andes-pagination__button')
            if current and all_pages:
                try:
                    last_page_text = all_pages[-1].get_text(strip=True)
                    if last_page_text.isdigit():
                        return current_page < int(last_page_text)
                except (ValueError, IndexError):
                    pass
        
        return False
    