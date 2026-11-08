"""Parsing compartido para listados MercadoLibre (MLA / MLV)."""

import re
from typing import Any, Dict, List, Optional

import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger(__name__)

ITEM_SELECTORS = [
    "li.ui-search-layout__item",
    "article.poly-card",
    "div.ui-search-result__content-wrapper",
    "div.ui-search-result__wrapper",
    "div.poly-card__content",
    'div[class*="ui-search-result"]',
]

BLOCK_MARKERS = (
    "negative_traffic",
    "account-verification",
    "ingresa a tu cuenta",
    "registrationtype=negative_traffic",
)


def is_mercadolibre_blocked(html: str) -> bool:
    lower = html.lower()
    return any(marker in lower for marker in BLOCK_MARKERS)


def parse_mercadolibre_listing_page(
    soup: BeautifulSoup,
    listing_prefix: str,
) -> List[Dict[str, Any]]:
    """
    Extrae listados de una página de resultados.

    Args:
        soup: HTML parseado.
        listing_prefix: 'MLA' o 'MLV'.
    """
    listings: List[Dict[str, Any]] = []
    link_pattern = re.compile(rf"/{listing_prefix}-?(\d+)", re.I)

    items: List[Any] = []
    for selector in ITEM_SELECTORS:
        items = soup.select(selector)
        if items:
            logger.debug(
                "mercadolibre_selector_found",
                selector=selector,
                count=len(items),
                prefix=listing_prefix,
            )
            break

    if not items:
        for link in soup.select(f'a[href*="/{listing_prefix}-"]'):
            parent = link.find_parent(["div", "li", "article"])
            if parent and parent not in items:
                items.append(parent)

    seen: set[str] = set()
    for item in items:
        try:
            raw = _extract_listing_from_item(item, link_pattern, listing_prefix)
            if not raw:
                continue
            ext_id = raw["id_externo"]
            if ext_id in seen:
                continue
            seen.add(ext_id)
            listings.append(raw)
        except Exception as e:
            logger.debug("mercadolibre_listing_error", error=str(e))

    return listings


def _extract_listing_from_item(
    item: BeautifulSoup,
    link_pattern: re.Pattern[str],
    listing_prefix: str,
) -> Optional[Dict[str, Any]]:
    link = None
    for selector in (
        f'a[href*="/{listing_prefix}-"]',
        "a.ui-search-link",
        "a.poly-component__title",
        "a[href]",
    ):
        link = item.select_one(selector)
        if link and link.get("href") and link_pattern.search(link["href"]):
            break
        link = None

    if not link or not link.get("href"):
        return None

    href = link["href"].split("?")[0].split("#")[0]
    id_match = link_pattern.search(href)
    if not id_match:
        return None

    data: Dict[str, Any] = {
        "id_externo": f"{listing_prefix}-{id_match.group(1)}",
        "url": href,
    }

    for selector in (
        "h2.poly-component__title",
        "h2.ui-search-item__title",
        "a.poly-component__title",
        "h2",
        "h3",
    ):
        title = item.select_one(selector)
        if title:
            data["titulo"] = title.get_text(strip=True)
            break
    if not data.get("titulo"):
        data["titulo"] = link.get_text(strip=True)

    price_container = item.select_one(".andes-money-amount") or item
    fraction = price_container.select_one(".andes-money-amount__fraction")
    if fraction:
        symbol_el = price_container.select_one(".andes-money-amount__currency-symbol")
        symbol = symbol_el.get_text(strip=True) if symbol_el else "$"
        data["precio_raw"] = f"{symbol} {fraction.get_text(strip=True)}"
    else:
        price_el = item.select_one('[class*="price"]')
        if price_el:
            data["precio_raw"] = price_el.get_text(strip=True)

    for selector in (
        ".ui-search-item__location",
        ".poly-component__location",
        '[class*="location"]',
    ):
        loc = item.select_one(selector)
        if loc:
            data["ubicacion"] = loc.get_text(strip=True)
            break

    for selector in (
        ".ui-search-card-attributes__attribute",
        ".ui-search-item__attributes-list li",
        ".poly-attributes-list__item",
    ):
        for attr in item.select(selector):
            attr_text = attr.get_text(strip=True).lower()
            if "m²" in attr_text or "m2" in attr_text or "mts" in attr_text:
                data["metros_raw"] = attr.get_text(strip=True)
            elif "hab" in attr_text or "dorm" in attr_text:
                data["habitaciones_raw"] = attr.get_text(strip=True)
            elif "baño" in attr_text:
                data["banos_raw"] = attr.get_text(strip=True)

    for selector in (
        "img.ui-search-result-image__element",
        "img.poly-component__picture",
        "img",
    ):
        img = item.select_one(selector)
        if img:
            src = img.get("data-src") or img.get("src")
            if src and src.startswith("http"):
                data["imagen"] = src.split()[0]
                break

    return data
