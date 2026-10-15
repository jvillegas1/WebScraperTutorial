"""Cliente HTTP para la API de listados de Zonaprop (bsre.zonaprop.com.ar)."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests
import structlog

logger = structlog.get_logger(__name__)

API_BASE = "https://bsre.zonaprop.com.ar/v3/postings"

LOCATION_SUGGEST_URLS = (
    "https://bsre.zonaprop.com.ar/v1/locations/suggest",
    "https://bsre.zonaprop.com.ar/v1/geo/suggest",
    "https://www.zonaprop.com.ar/api/geo/suggest",
)


def _default_api_headers() -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.zonaprop.com.ar/",
        "Origin": "https://www.zonaprop.com.ar",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }


def extract_search_parameters_from_html(html: str) -> Optional[str]:
    if not html:
        return None
    patterns = (
        r'"searchParameters"\s*:\s*"((?:\\.|[^"\\])*)"',
        r"searchParameters\\\":\\\"([^\\\"]+)\\\"",
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            raw = match.group(1)
            return raw.encode("utf-8").decode("unicode_escape")
    return None


def search_parameters_from_api_url(url: str) -> Optional[str]:
    try:
        qs = parse_qs(urlparse(url).query)
        params = qs.get("search.parameters") or qs.get("search.parameters[]")
        if params:
            return unquote(params[0])
    except Exception:
        pass
    return None


def _collect_posting_lists(data: Any, depth: int = 0) -> List[dict]:
    if depth > 6 or data is None:
        return []
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and (
            "postingId" in data[0]
            or "posting_id" in data[0]
            or "priceOperationTypes" in data[0]
            or "price_operation_types" in data[0]
        ):
            return [x for x in data if isinstance(x, dict)]
        return []
    if isinstance(data, dict):
        for key in (
            "listPostings",
            "list_postings",
            "postings",
            "items",
            "results",
            "content",
        ):
            if key in data:
                found = _collect_posting_lists(data[key], depth + 1)
                if found:
                    return found
        for value in data.values():
            found = _collect_posting_lists(value, depth + 1)
            if found:
                return found
    return []


def parse_api_postings_payload(data: Any) -> List[dict]:
    return _collect_posting_lists(data)


def resolve_location_id(
    session: requests.Session,
    query: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> Optional[str]:
    if not query:
        return None
    req_headers = _default_api_headers()
    if headers:
        req_headers.update(headers)

    for base_url in LOCATION_SUGGEST_URLS:
        for params in ({"query": query}, {"term": query}, {"keyword": query}):
            try:
                resp = session.get(base_url, params=params, headers=req_headers, timeout=timeout)
                if resp.status_code >= 400:
                    continue
                data = resp.json()
            except (requests.RequestException, ValueError):
                continue

            candidates = data if isinstance(data, list) else data.get("items") or data.get("suggestions") or []
            if not isinstance(candidates, list):
                continue
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                loc_id = (
                    item.get("locationId")
                    or item.get("location_id")
                    or item.get("id")
                    or item.get("value")
                )
                label = (item.get("label") or item.get("name") or "").lower()
                if loc_id and query.lower().split(",")[0] in label:
                    return str(loc_id)
            if candidates and isinstance(candidates[0], dict):
                loc_id = (
                    candidates[0].get("locationId")
                    or candidates[0].get("location_id")
                    or candidates[0].get("id")
                )
                if loc_id:
                    return str(loc_id)
    return None


def fetch_postings_page(
    session: requests.Session,
    search_parameters: str,
    *,
    offset: int = 0,
    limit: int = 30,
    sort_by: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> List[dict]:
    if not search_parameters:
        return []

    params: Dict[str, Any] = {
        "search.name": "listing",
        "paging.limit": limit,
        "paging.offset": offset,
        "search.parameters": search_parameters,
    }
    if sort_by:
        params["sortByName"] = sort_by

    req_headers = _default_api_headers()
    if headers:
        req_headers.update(headers)

    try:
        resp = session.get(API_BASE, params=params, headers=req_headers, timeout=timeout)
        if resp.status_code == 401:
            logger.warning("zonaprop_api_unauthorized", offset=offset)
            return []
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("zonaprop_api_error", error=str(e), offset=offset)
        return []

    items = parse_api_postings_payload(data)
    logger.debug("zonaprop_api_page", offset=offset, count=len(items))
    return items
