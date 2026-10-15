"""Scraper Properati Argentina."""

from ._base import ArgentinaPortalScraper
from ...regions import get_region_config


class ProperatiScraper(ArgentinaPortalScraper):
    name = "properati"
    base_url = get_region_config("argentina")["portal_urls"]["properati"]
    item_selectors = [
        'div.property-card',
        'article[class*="property"]',
        'div[class*="PropertyCard"]',
        'li.search-result',
    ]

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
        url = f"{self.base_url}/s/{op}"
        if page > 1:
            url = f"{url}?page={page}"
        return url
