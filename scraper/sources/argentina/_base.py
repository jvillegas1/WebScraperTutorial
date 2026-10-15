"""Scraper base para portales inmobiliarios de Argentina."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper
from ...parsers.property_parser import Property, PropertyParser
from ._helpers import extract_json_ld_listings, extract_listings_from_cards

logger = structlog.get_logger(__name__)


class ArgentinaPortalScraper(BaseScraper):
    """Base para scrapers argentinos usando HTTP (requests).

    Playwright headless suele recibir 403 o timeout en portales AR;
    requests con headers de navegador real funciona de forma fiable.
    """

    region = "argentina"
    item_selectors: List[str] = [
        'article',
        'li[class*="posting"]',
        'div[class*="card"]',
        'div[class*="listing"]',
        'div[class*="property"]',
    ]
    id_url_patterns: Optional[List[str]] = None

    def _get_headers(self) -> Dict[str, str]:
        headers = super()._get_headers()
        headers.update({
            "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })
        return headers

    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        listings = extract_json_ld_listings(soup, self.base_url)
        if listings:
            return listings
        return extract_listings_from_cards(soup, self.item_selectors, self.base_url)

    def _parse_property_detail(self, raw_data: Dict[str, Any]) -> Optional[Property]:
        try:
            precio, moneda = PropertyParser.normalize_price(raw_data.get('precio_raw', ''))
            if precio is None or precio <= 0:
                return None

            titulo = raw_data.get('titulo', '')
            default_currency = self.config.get('default_currency', 'USD')

            ubicacion = PropertyParser.normalize_location(
                raw_data.get('ubicacion', ''),
                self.config.get('location_label', 'Argentina'),
            )

            return Property(
                id_externo=raw_data['id_externo'],
                source=self.name,
                region=self.region,
                titulo=PropertyParser.clean_text(titulo),
                precio=precio,
                moneda=moneda or default_currency,
                ubicacion=ubicacion,
                tipo_inmueble=PropertyParser.normalize_property_type(titulo),
                url=raw_data['url'],
                fecha_scraping=datetime.now(),
                metros_cuadrados=PropertyParser.extract_area(titulo),
                habitaciones=PropertyParser.extract_number(
                    re.search(r'(\d+)\s*(?:amb|dorm|hab)', titulo, re.I).group(1)
                    if re.search(r'(\d+)\s*(?:amb|dorm|hab)', titulo, re.I) else ''
                ),
            )
        except Exception as e:
            logger.error("property_normalization_error", scraper=self.name, error=str(e))
            return None

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        next_selectors = [
            'a[rel="next"]',
            'a[class*="next"]',
            'a[aria-label*="Siguiente"]',
            'a[title="Siguiente"]',
            f'a[href*="page={current_page + 1}"]',
            f'a[href*="pagina={current_page + 1}"]',
        ]
        for selector in next_selectors:
            if soup.select_one(selector):
                return True
        return False

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        """Fallback nacional cuando no hay localidad activa."""
        op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
        url = f"{self.base_url}/inmuebles/{op}"
        if page > 1:
            url = f"{url}?pagina={page}"
        return url
