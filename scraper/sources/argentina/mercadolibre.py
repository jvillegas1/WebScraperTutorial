"""Scraper MercadoLibre Argentina - Inmuebles (HTTP, subdominio inmuebles.*)."""

from typing import Dict, List, Optional

import structlog
from bs4 import BeautifulSoup

from ._base import ArgentinaPortalScraper
from ..mercadolibre_listings import (
    is_mercadolibre_blocked,
    parse_mercadolibre_listing_page,
)
from ...regions import get_region_config

logger = structlog.get_logger(__name__)


class MercadoLibreArScraper(ArgentinaPortalScraper):
    """MercadoLibre AR: requests + inmuebles.mercadolibre.com.ar (no Playwright)."""

    name = "mercadolibre"
    base_url = get_region_config("argentina")["portal_urls"]["mercadolibre"]
    listing_prefix = "MLA"

    def _get_soup(self, url: str) -> Optional[BeautifulSoup]:
        soup = super()._get_soup(url)
        if soup is None:
            return None
        if is_mercadolibre_blocked(str(soup)):
            logger.warning(
                "mercadolibre_blocked",
                url=url,
                region=self.region,
            )
            return None
        return soup

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
        base = f"{self.base_url}/{op}/"
        if page > 1:
            offset = (page - 1) * 48 + 1
            base = f"{base.rstrip('/')}_Desde_{offset}"
        return base

    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict]:
        listings = parse_mercadolibre_listing_page(soup, self.listing_prefix)
        if listings:
            return listings
        return ArgentinaPortalScraper._parse_listing_page(self, soup)

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        if soup.select_one('a.andes-pagination__link[title="Siguiente"]'):
            return True
        if soup.select_one('li.andes-pagination__button--next a'):
            return True
        if soup.select_one(f'a[href*="_Desde_{current_page * 48 + 1}"]'):
            return True
        return ArgentinaPortalScraper._has_next_page(self, soup, current_page)
