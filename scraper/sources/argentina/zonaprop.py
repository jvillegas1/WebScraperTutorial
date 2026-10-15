"""Scraper Zonaprop - API móvil + captura de red Playwright."""

import re
from typing import Any, Dict, List, Optional

import structlog
from bs4 import BeautifulSoup

from ..base_scraper import PlaywrightBaseScraper
from ._base import ArgentinaPortalScraper
from ._helpers import (
    _postings_to_listings,
    extract_listings_from_cards,
    extract_zonaprop_listings,
)
from ...regions import get_region_config
from .zonaprop_api import (
    extract_search_parameters_from_html,
    fetch_postings_page,
    parse_api_postings_payload,
    resolve_location_id,
    search_parameters_from_api_url,
)
from .zonaprop_extra import get_zonaprop_extra_targets
from .zonaprop_mapper import build_search_parameters, location_query_for_slug, parse_listing_path

logger = structlog.get_logger(__name__)


class ZonapropScraper(PlaywrightBaseScraper, ArgentinaPortalScraper):
    """Captura listados desde XHR v3/postings (requiere sesión de navegador)."""

    name = "zonaprop"
    base_url = get_region_config("argentina")["portal_urls"]["zonaprop"]
    item_selectors = ['div[data-qa="posting PROPERTY"]', 'div[class*="postingCard"]']

    def __init__(self, config=None):
        super().__init__(config)
        self._page_listings_cache: Optional[List[Dict[str, Any]]] = None
        self._api_auth_headers: Dict[str, str] = {}
        self._search_parameters: Optional[str] = None
        self._network_postings: List[dict] = []

    async def _init_browser(self):
        headless = self.config.get("zonaprop_headless", False)
        channel = self.config.get("zonaprop_browser_channel")
        if channel:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            launch_kwargs = {
                "headless": headless,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            try:
                self._browser = await self._playwright.chromium.launch(
                    channel=channel,
                    **launch_kwargs,
                )
            except Exception as e:
                logger.warning("zonaprop_channel_fallback", channel=channel, error=str(e))
                self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._context = await self._browser.new_context(
                locale="es-AR",
                timezone_id="America/Argentina/Buenos_Aires",
                user_agent=self._get_headers()["User-Agent"],
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
            )
            self._page = await self._context.new_page()
            await self._page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            logger.info("playwright_browser_initialized", scraper=self.name, channel=channel)
        else:
            await PlaywrightBaseScraper._init_browser(self)

        try:
            await self._page.goto(
                f"{self.base_url.rstrip('/')}/",
                wait_until="domcontentloaded",
                timeout=self.config.get("timeout", 60) * 1000,
            )
            await self._page.wait_for_timeout(1500)
            await self._sync_cookies_to_session()
        except Exception as e:
            logger.warning("zonaprop_warmup_failed", error=str(e))

    async def _sync_cookies_to_session(self):
        if not self._context:
            return
        cookies = await self._context.cookies()
        for cookie in cookies:
            self.session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path") or "/",
            )

    def _listings_path_for_current_location(self, url: str) -> Optional[str]:
        loc = self.config.get("current_location") or {}
        zp = loc.get("zonaprop_path")
        if zp:
            return zp if zp.endswith(".html") else f"{zp}.html"
        if "/zonaprop.com.ar/" in url:
            return url.split(".ar/")[-1].split("?")[0]
        return None

    def _resolve_search_parameters(self, page_url: str, html: str) -> Optional[str]:
        if self._search_parameters:
            return self._search_parameters
        sp = extract_search_parameters_from_html(html)
        if sp:
            return sp
        path = self._listings_path_for_current_location(page_url)
        if not path:
            return None
        _, _, location_slug = parse_listing_path(path)
        location_id = None
        if location_slug:
            query = location_query_for_slug(location_slug)
            location_id = resolve_location_id(
                self.session,
                query,
                headers={**self._get_headers(), **self._api_auth_headers},
                timeout=self.config.get("timeout", 30),
            )
        return build_search_parameters(path, location_id=location_id)

    def _listings_from_sources(
        self,
        *,
        html: str,
        page_url: str,
        page_num: int,
    ) -> tuple[List[Dict[str, Any]], str]:
        if self._network_postings:
            converted = _postings_to_listings(self._network_postings, self.base_url)
            if converted:
                return converted, "network"

        soup = BeautifulSoup(html, "lxml")
        converted = extract_zonaprop_listings(soup, self.base_url)
        if converted:
            return converted, "html_embedded"

        converted = extract_listings_from_cards(soup, self.item_selectors, self.base_url)
        if converted:
            return converted, "html_dom"

        search_params = self._resolve_search_parameters(page_url, html)
        if search_params:
            self._search_parameters = search_params
            api_items = fetch_postings_page(
                self.session,
                search_params,
                offset=max(0, (page_num - 1) * 30),
                headers={**self._get_headers(), **self._api_auth_headers},
                timeout=self.config.get("timeout", 30),
            )
            converted = _postings_to_listings(api_items, self.base_url)
            if converted:
                return converted, "api"

        title = soup.title.get_text(strip=True) if soup.title else ""
        logger.warning(
            "zonaprop_empty_page",
            url=page_url,
            title=title[:120],
            html_len=len(html),
            has_list_postings="listPostings" in html,
            has_captcha="captcha" in html.lower(),
        )
        return [], "none"

    async def _get_page_content(self, url: str) -> Optional[str]:
        if self._page is None:
            await self._init_browser()

        if self._request_count > 0:
            self._delay()
        self._request_count += 1

        self._network_postings = []

        async def on_response(response):
            req_url = response.url
            if "v3/postings" not in req_url or response.status != 200:
                return
            try:
                sp = search_parameters_from_api_url(req_url)
                if sp:
                    self._search_parameters = sp
                req_headers = response.request.headers
                for key in ("authorization", "x-api-key", "x-client-id", "x-uuid"):
                    val = req_headers.get(key)
                    if val:
                        self._api_auth_headers[key] = val
                body = await response.json()
                items = parse_api_postings_payload(body)
                if items:
                    self._network_postings.extend(items)
                    logger.info(
                        "zonaprop_network_capture",
                        count=len(items),
                        total=len(self._network_postings),
                    )
            except Exception as e:
                logger.debug("zonaprop_network_parse_error", error=str(e))

        self._page.on("response", on_response)
        timeout_ms = self.config.get("timeout", 90) * 1000
        wait_until = self.config.get("playwright_wait_until", "domcontentloaded")

        try:
            await self._page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            for sel in (
                "#onetrust-accept-btn-handler",
                'button:has-text("Aceptar")',
                'button:has-text("Aceptar todas")',
            ):
                try:
                    await self._page.locator(sel).first.click(timeout=2500)
                    break
                except Exception:
                    pass

            try:
                await self._page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            for _ in range(4):
                await self._page.mouse.wheel(0, 2000)
                await self._page.wait_for_timeout(700)

            await self._page.wait_for_timeout(self.config.get("playwright_render_wait_ms", 2500))
            await self._sync_cookies_to_session()
            content = await self._page.content()
            return content
        except Exception as e:
            logger.error("playwright_error", url=url, error=str(e), scraper=self.name)
            return None
        finally:
            try:
                self._page.remove_listener("response", on_response)
            except Exception:
                pass

    async def _get_soup_async(self, url: str) -> Optional[BeautifulSoup]:
        page_num = 1
        m = re.search(r"-pagina-(\d+)\.html", url)
        if m:
            page_num = int(m.group(1))
        elif "page=" in url:
            m2 = re.search(r"page=(\d+)", url)
            if m2:
                page_num = int(m2.group(1))

        if page_num == 1:
            self._search_parameters = None
            self._network_postings = []

        if page_num > 1 and self._search_parameters:
            api_items = fetch_postings_page(
                self.session,
                self._search_parameters,
                offset=(page_num - 1) * 30,
                headers={**self._get_headers(), **self._api_auth_headers},
                timeout=self.config.get("timeout", 30),
            )
            listings = _postings_to_listings(api_items, self.base_url)
            self._page_listings_cache = listings
            logger.info(
                "zonaprop_page_extract",
                source="api_pagination",
                listing_count=len(listings),
                url=url,
            )
            return BeautifulSoup("<html></html>", "lxml")

        content = await self._get_page_content(url)
        if content is None:
            self._page_listings_cache = []
            return None

        listings, source = self._listings_from_sources(
            html=content,
            page_url=url,
            page_num=page_num,
        )
        self._page_listings_cache = listings
        logger.info(
            "zonaprop_page_extract",
            source=source,
            raw_count=len(self._network_postings),
            listing_count=len(listings),
            url=url,
        )
        return BeautifulSoup(content, "lxml")

    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        if self._page_listings_cache is not None:
            cached = self._page_listings_cache
            self._page_listings_cache = None
            return cached
        return extract_zonaprop_listings(soup, self.base_url)

    def _get_headers(self) -> Dict[str, str]:
        headers = super()._get_headers()
        headers["Referer"] = f"{self.base_url.rstrip('/')}/"
        headers["Origin"] = f"{self.base_url.rstrip('/')}"
        headers.update(self._api_auth_headers)
        return headers

    def _resolve_scrape_targets(self) -> List[dict]:
        scope = self.config.get("zonaprop_scrape_scope", "extra_only")
        if scope == "extra_only":
            return get_zonaprop_extra_targets()

        targets = super()._resolve_scrape_targets()
        if not self.config.get("include_zonaprop_extra", True):
            return targets
        seen = {t["id"] for t in targets}
        for extra in get_zonaprop_extra_targets():
            if extra["id"] not in seen:
                targets.append(extra)
                seen.add(extra["id"])
        return targets

    def _resolve_search_url(self, city: str, operation: str, page: int = 1) -> str:
        loc = self.config.get("current_location") or {}
        zp_path = loc.get("zonaprop_path")
        if zp_path:
            path = zp_path if zp_path.endswith(".html") else f"{zp_path}.html"
            if page > 1:
                base = path[:-5]
                base = re.sub(r"-pagina-\d+$", "", base)
                path = f"{base}-pagina-{page}.html"
            return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        return super()._resolve_search_url(city, operation, page)

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        if self._search_parameters:
            return current_page < self._pages_limit()
        if soup.select_one('a[rel="next"]'):
            return True
        nxt = current_page + 1
        if soup.select(f'a[href*="-pagina-{nxt}"]'):
            return True
        return False

    async def _close_browser(self):
        await PlaywrightBaseScraper._close_browser(self)

    def scrape(self, city: str = "", operation: str = "venta"):
        """Reinicia auth entre operaciones."""
        self._search_parameters = None
        self._api_auth_headers = {}
        yield from super().scrape(city=city, operation=operation)
