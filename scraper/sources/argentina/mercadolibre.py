"""Scraper MercadoLibre Argentina - Inmuebles."""

import re
from typing import Dict, List

import structlog
from bs4 import BeautifulSoup

from ..base_scraper import PlaywrightBaseScraper
from ._base import ArgentinaPortalScraper
from ...regions import get_region_config

logger = structlog.get_logger(__name__)


class MercadoLibreArScraper(PlaywrightBaseScraper, ArgentinaPortalScraper):
    """MercadoLibre requiere Playwright; el resto de portales AR usan HTTP."""

    name = "mercadolibre"
    base_url = get_region_config("argentina")["portal_urls"]["mercadolibre"]
    item_selectors = [
        'div.ui-search-result__content-wrapper',
        'li.ui-search-layout__item',
        'article.poly-card',
        'div[class*="ui-search-result"]',
    ]

    async def _init_browser(self):
        await PlaywrightBaseScraper._init_browser(self)
        try:
            await self._page.goto(
                'https://www.mercadolibre.com.ar/',
                wait_until='domcontentloaded',
                timeout=self.config.get('timeout', 60) * 1000,
            )
            await self._page.wait_for_timeout(1500)
        except Exception as e:
            logger.warning("mercadolibre_warmup_failed", error=str(e))

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
        base = f"{self.base_url}/inmuebles/{op}/"
        if page > 1:
            offset = (page - 1) * 48 + 1
            base = f"{base.rstrip('/')}_Desde_{offset}"
        return base

    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict]:
        listings = []
        items = []
        for selector in self.item_selectors:
            items = soup.select(selector)
            if items:
                break

        if not items:
            for link in soup.select('a[href*="/MLA-"]'):
                parent = link.find_parent(['div', 'li', 'article'])
                if parent and parent not in items:
                    items.append(parent)

        for item in items:
            link = item.select_one('a[href*="/MLA-"]') or item.select_one('a[href]')
            if not link or not link.get('href'):
                continue
            href = link['href'].split('?')[0]
            id_match = re.search(r'MLA-(\d+)', href)
            if not id_match:
                continue

            title_el = item.select_one('h2, .poly-component__title, .ui-search-item__title') or link
            price_el = item.select_one('.andes-money-amount, [class*="price"]')
            loc_el = item.select_one('.ui-search-item__location, [class*="location"]')

            listings.append({
                'id_externo': id_match.group(1),
                'url': href,
                'titulo': title_el.get_text(strip=True),
                'precio_raw': price_el.get_text(strip=True) if price_el else '',
                'ubicacion': loc_el.get_text(strip=True) if loc_el else '',
            })

        return listings

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        if soup.select_one('a.andes-pagination__link[title="Siguiente"]'):
            return True
        if soup.select_one('li.andes-pagination__button--next a'):
            return True
        return ArgentinaPortalScraper._has_next_page(self, soup, current_page)
