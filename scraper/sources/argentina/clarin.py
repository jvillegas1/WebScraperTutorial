"""Scraper Clarin Clasificados - Inmuebles."""

from ._base import ArgentinaPortalScraper
from ...regions import get_region_config

# Rutas hash del SPA de clasificados.clarin.com
CLARIN_LISTING_PATHS = {
    "venta": "/inicio/index#!/1/listado/nivel-estructura/Inmuebles",
    "alquiler": (
        "/inicio/index#!/5/listado/nivel-estructura/Inmuebles/_Top:Alquiler%20Ofrecido"
    ),
}


class ClarinScraper(ArgentinaPortalScraper):
    name = "clarin"
    base_url = get_region_config("argentina")["portal_urls"]["clarin"]
    item_selectors = [
        'article.ad-item',
        'div.listing-card',
        'div[class*="clasificado"]',
        'li.result-item',
    ]

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
        return f"{self.base_url.rstrip('/')}{CLARIN_LISTING_PATHS[op]}"
