"""Scraper Century 21 Argentina."""

from ._base import ArgentinaPortalScraper
from ...regions import get_region_config


class Century21Scraper(ArgentinaPortalScraper):
    name = "century21"
    base_url = get_region_config("argentina")["portal_urls"]["century21"]
    item_selectors = [
        'div.property-card',
        'article.listing',
        'div[class*="listing-card"]',
        'div.search-result-item',
    ]

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        url = self.base_url.rstrip('/')
        if page > 1:
            url = f"{url}?page={page}"
        return url
