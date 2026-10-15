"""Scraper Lamudi Argentina."""

from ._base import ArgentinaPortalScraper
from ...regions import get_region_config


class LamudiScraper(ArgentinaPortalScraper):
    name = "lamudi"
    base_url = get_region_config("argentina")["portal_urls"]["lamudi"]
    item_selectors = [
        'div.listing-item',
        'article.property-card',
        'div[class*="ListingCard"]',
        'li.search-result',
    ]

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        rent_path = "for-rent" if operation.lower() in ("alquiler", "rent", "renta") else "for-sale"
        url = f"{self.base_url}/{rent_path}/"
        if page > 1:
            url = f"{url}?page={page}"
        return url
