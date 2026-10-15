"""Scraper BuscaInmueble.com.ar."""

from ._base import ArgentinaPortalScraper
from ...regions import get_region_config


class BuscaInmuebleScraper(ArgentinaPortalScraper):
    name = "buscainmueble"
    base_url = get_region_config("argentina")["portal_urls"]["buscainmueble"]
    item_selectors = [
        'div.property-item',
        'article.listing',
        'div[class*="property"]',
        'div.result-item',
    ]

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
        url = f"{self.base_url}/{op}/"
        if page > 1:
            url = f"{url}?page={page}"
        return url
