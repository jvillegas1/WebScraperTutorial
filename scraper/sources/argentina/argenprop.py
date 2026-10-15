"""Scraper Argenprop."""

from ._base import ArgentinaPortalScraper
from ...regions import get_region_config


class ArgenpropScraper(ArgentinaPortalScraper):
    name = "argenprop"
    base_url = get_region_config("argentina")["portal_urls"]["argenprop"]
    item_selectors = [
        'div.listing__item',
        'article.listing-card',
        'div[class*="listing-card"]',
        'div.card-container',
    ]

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
        url = f"{self.base_url}/inmuebles/{op}"
        if page > 1:
            url = f"{url}?pagina={page}"
        return url
