"""Utilidades compartidas para scrapers de Argentina."""

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ...parsers.property_parser import PropertyParser


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("_", "-")


def extract_id_from_url(url: str, patterns: Optional[List[str]] = None) -> Optional[str]:
    if not url:
        return None
    default_patterns = [
        r'/(\d{5,})',
        r'MLA-(\d+)',
        r'id[=/](\d+)',
        r'-(\d+)\.html',
        r'/p/(\d+)',
    ]
    for pattern in (patterns or default_patterns):
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_listings_from_cards(
    soup: BeautifulSoup,
    item_selectors: List[str],
    base_url: str,
) -> List[Dict[str, Any]]:
    """Extrae listados genéricos desde tarjetas HTML."""
    listings = []
    seen_urls = set()

    items: List[Tag] = []
    for selector in item_selectors:
        items = soup.select(selector)
        if items:
            break

    if not items:
        for link in soup.select('a[href]'):
            href = link.get('href', '')
            if not href or href.startswith('#'):
                continue
            if any(k in href.lower() for k in ('inmueble', 'propiedad', 'listing', 'venta', 'departamento', 'casa')):
                parent = link.find_parent(['article', 'div', 'li'])
                if parent and parent not in items:
                    items.append(parent)

    for item in items:
        link = item.select_one('a[href]') or item.find('a', href=True)
        if not link:
            continue

        href = link.get('href', '')
        if href.startswith('/'):
            href = urljoin(base_url, href)
        if href in seen_urls:
            continue
        seen_urls.add(href)

        title_el = (
            item.select_one('h2, h3, h4, .title, [class*="title"], [class*="Title"]')
            or link
        )
        price_el = item.select_one(
            '[class*="price"], [class*="Price"], [class*="precio"], span.amount, .price-tag'
        )
        location_el = item.select_one(
            '[class*="location"], [class*="Location"], [class*="ubicacion"], [class*="address"]'
        )

        titulo = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
        precio_raw = price_el.get_text(strip=True) if price_el else item.get_text(" ", strip=True)[:120]
        ubicacion = location_el.get_text(strip=True) if location_el else ""

        id_externo = extract_id_from_url(href) or PropertyParser.generate_id('ar', href[-40:])
        if not titulo or len(titulo) < 5:
            continue

        listings.append({
            'id_externo': id_externo,
            'url': href,
            'titulo': titulo,
            'precio_raw': precio_raw,
            'ubicacion': ubicacion,
        })

    return listings


def _parse_js_balanced(text: str, start: int, open_ch: str, close_ch: str):
    """Parsea JSON embebido en JS contando delimitadores."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                chunk = re.sub(r"\bundefined\b", "null", chunk)
                return json.loads(chunk)
    raise json.JSONDecodeError("Unbalanced JSON fragment", text, start)


def _parse_js_object(text: str, start: int) -> dict:
    return _parse_js_balanced(text, start, "{", "}")


def _extract_json_array(text: str, key: str) -> Optional[list]:
    marker = f'"{key}"'
    idx = text.find(marker)
    if idx == -1:
        return None
    arr_start = text.find("[", idx)
    if arr_start == -1:
        return None
    try:
        return _parse_js_balanced(text, arr_start, "[", "]")
    except (json.JSONDecodeError, ValueError):
        return None


def _zonaprop_price_raw(prop: dict) -> str:
    ops = prop.get("priceOperationTypes") or prop.get("price_operation_types") or []
    for op_type in ops:
        for price in op_type.get("prices") or []:
            for fmt_key in ("formattedAmount", "formatted_amount", "label"):
                fmt = price.get(fmt_key)
                if fmt:
                    return str(fmt).strip()
            amount = price.get("amount")
            if amount is not None and amount != "":
                currency = price.get("currency") or "USD"
                return f"{currency} {amount}"
    for key in (
        "formattedPrice",
        "price",
        "priceLabel",
        "priceAndCurrency",
        "askingPrice",
    ):
        val = prop.get(key)
        if val:
            return str(val).strip()
    return ""


def _postings_to_listings(postings: list, base_url: str) -> List[Dict[str, Any]]:
    listings: List[Dict[str, Any]] = []
    seen = set()
    for prop in postings:
        if not isinstance(prop, dict):
            continue
        rel_url = (
            prop.get("url")
            or prop.get("link")
            or prop.get("permalink")
            or prop.get("postingUrl")
            or ""
        )
        if not rel_url and prop.get("postingId"):
            rel_url = f"/propiedades/clasificado/venta-{prop['postingId']}.html"
        if not rel_url:
            continue
        if rel_url.startswith("/"):
            href = urljoin(base_url.rstrip("/") + "/", rel_url.lstrip("/"))
        elif rel_url.startswith("http"):
            href = rel_url
        else:
            href = urljoin(base_url.rstrip("/") + "/", rel_url)

        if href in seen:
            continue
        seen.add(href)

        posting_id = (
            prop.get("postingId")
            or prop.get("posting_id")
            or extract_id_from_url(href)
        )
        titulo = (
            prop.get("title")
            or prop.get("generatedTitle")
            or prop.get("generated_title")
            or prop.get("postingTitle")
            or prop.get("posting_title")
            or ""
        )
        loc = prop.get("postingLocation") or prop.get("posting_location") or {}
        address = loc.get("address") or {}
        if isinstance(address, dict):
            addr_name = address.get("name") or ""
        else:
            addr_name = str(address) if address else ""
        ubicacion = addr_name
        if loc.get("location"):
            ubicacion = f"{addr_name}, {loc.get('location')}".strip(", ")

        if not titulo:
            titulo = addr_name or "Inmueble en Zonaprop"

        precio_raw = _zonaprop_price_raw(prop)
        if not precio_raw:
            continue

        listings.append({
            "id_externo": str(posting_id or PropertyParser.generate_id("zp", href[-40:])),
            "url": href,
            "titulo": titulo,
            "precio_raw": precio_raw,
            "ubicacion": ubicacion,
        })
    return listings


def extract_zonaprop_dom_listings(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Tarjetas renderizadas (Playwright) con data-qa de Zonaprop."""
    listings: List[Dict[str, Any]] = []
    seen = set()
    cards = soup.select('div[data-qa="posting PROPERTY"]')
    for card in cards:
        link = card.select_one('h2[data-qa="POSTING_CARD_DESCRIPTION"] a') or card.select_one("a[href]")
        if not link or not link.get("href"):
            continue
        href = link["href"].split("?")[0]
        if href.startswith("/"):
            href = urljoin(base_url.rstrip("/") + "/", href.lstrip("/"))
        if href in seen:
            continue
        seen.add(href)

        posting_id = extract_id_from_url(href)
        price_el = card.select_one('[data-qa="POSTING_CARD_PRICE"]')
        loc_el = card.select_one('[data-qa="POSTING_CARD_LOCATION"]')
        addr_el = card.select_one("h4.postingLocations-module__location-address")
        titulo = link.get_text(strip=True) or "Inmueble en Zonaprop"
        precio_raw = price_el.get_text(strip=True) if price_el else ""
        ubicacion = ""
        if addr_el:
            ubicacion = addr_el.get_text(strip=True)
        if loc_el:
            loc_text = loc_el.get_text(strip=True)
            ubicacion = f"{ubicacion}, {loc_text}".strip(", ") if ubicacion else loc_text

        if not precio_raw:
            continue

        listings.append({
            "id_externo": str(posting_id or PropertyParser.generate_id("zp", href[-40:])),
            "url": href,
            "titulo": titulo,
            "precio_raw": precio_raw,
            "ubicacion": ubicacion,
        })
    return listings


def extract_zonaprop_listings(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Listados desde PRELOADED_STATE o listPostings embebido en HTML."""
    html = str(soup)

    postings = _extract_json_array(html, "listPostings")
    if postings:
        converted = _postings_to_listings(postings, base_url)
        if converted:
            return converted

    script = soup.find("script", id="preloadedData")
    script_text = ""
    if script:
        script_text = script.string or script.get_text() or ""

    if script_text:
        prefixes = (
            "window.__PRELOADED_STATE__ = ",
            "window.PRELOADED_STATE = ",
        )
        for prefix in prefixes:
            idx = script_text.find(prefix)
            if idx == -1:
                continue
            try:
                data = _parse_js_object(script_text, idx + len(prefix))
                postings = (data.get("listStore") or {}).get("listPostings") or []
                converted = _postings_to_listings(postings, base_url)
                if converted:
                    return converted
            except (json.JSONDecodeError, ValueError):
                continue

    for tag in soup.find_all("script"):
        content = tag.string or tag.get_text() or ""
        if "listPostings" not in content:
            continue
        postings = _extract_json_array(content, "listPostings")
        if postings:
            converted = _postings_to_listings(postings, base_url)
            if converted:
                return converted

    dom = extract_zonaprop_dom_listings(soup, base_url)
    if dom:
        return dom

    return []


def extract_json_ld_listings(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Extrae listados desde JSON-LD embebido."""
    listings = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or '')
        except (json.JSONDecodeError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get('@type', '')
            if item_type not in ('Product', 'Offer', 'RealEstateListing', 'Apartment', 'House'):
                if item.get('@type') == 'ItemList':
                    for sub in item.get('itemListElement', []):
                        sub_item = sub.get('item', sub) if isinstance(sub, dict) else {}
                        if isinstance(sub_item, dict):
                            parsed = _parse_json_ld_item(sub_item, base_url)
                            if parsed:
                                listings.append(parsed)
                continue
            parsed = _parse_json_ld_item(item, base_url)
            if parsed:
                listings.append(parsed)

    return listings


def _parse_json_ld_item(item: dict, base_url: str) -> Optional[Dict[str, Any]]:
    url = item.get('url') or item.get('@id') or ''
    if url.startswith('/'):
        url = urljoin(base_url, url)
    if not url:
        return None

    offers = item.get('offers', {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price = offers.get('price') or item.get('price')
    currency = offers.get('priceCurrency') or item.get('priceCurrency') or 'USD'
    titulo = item.get('name') or item.get('title') or ''
    ubicacion = ''
    address = item.get('address', {})
    if isinstance(address, dict):
        parts = [address.get('addressLocality'), address.get('addressRegion')]
        ubicacion = ', '.join(p for p in parts if p)

    if not titulo and not price:
        return None

    precio_raw = f"{currency} {price}" if price else ''
    return {
        'id_externo': extract_id_from_url(url) or PropertyParser.generate_id('jsonld', url[-30:]),
        'url': url,
        'titulo': titulo or 'Inmueble',
        'precio_raw': precio_raw,
        'ubicacion': ubicacion,
    }
