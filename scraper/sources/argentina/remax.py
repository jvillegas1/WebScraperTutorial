"""Scraper RE/MAX Argentina."""

from ._base import ArgentinaPortalScraper
from ...regions import get_region_config


class RemaxArScraper(ArgentinaPortalScraper):
    name = "remax"
    base_url = get_region_config("argentina")["portal_urls"]["remax"]
    item_selectors = [
        'div.listing-card',
        'article.property-card',
        'div[class*="property-card"]',
        'div.search-result',
    ]

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        listing_type = "rent" if operation.lower() in ("alquiler", "rent", "renta") else "buy"
        url = f"{self.base_url}/listings/{listing_type}?"
        if page > 1:
            url = f"{url}page={page}"
        return url
