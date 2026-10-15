"""Construcción de URLs de búsqueda por portal y localidad."""

import re
from typing import Optional
from urllib.parse import urljoin

from .locations import location_label


def _portal_slug(location: dict, portal: str) -> str:
    slugs = location.get("slug") or {}
    return slugs.get(portal) or slugs.get("default") or ""


def build_search_url(
    portal: str,
    region: str,
    location: dict,
    base_url: str,
    operation: str = "venta",
    page: int = 1,
) -> str:
    op = "venta" if operation.lower() in ("venta", "sale") else "alquiler"
    slug = _portal_slug(location, portal)
    base_url = base_url.rstrip("/")

    if region == "venezuela":
        return _build_venezuela_url(portal, base_url, op, slug, page)
    return _build_argentina_url(portal, base_url, op, slug, page, location)


def _paginate(url: str, page: int, portal: str) -> str:
    if page <= 1:
        return url
    if portal == "mercadolibre":
        offset = (page - 1) * 48 + 1
        sep = "&" if "?" in url else ""
        if "_Desde_" in url:
            return url
        return f"{url.rstrip('/')}_Desde_{offset}"
    if portal == "zonaprop" and url.endswith(".html"):
        base = url[:-5]
        base = re.sub(r"-pagina-\d+$", "", base)
        return f"{base}-pagina-{page}.html"
    if "?" in url:
        return f"{url}&page={page}"
    return f"{url}?page={page}"


def _build_venezuela_url(portal: str, base_url: str, op: str, slug: str, page: int) -> str:
    if portal == "mercadolibre":
        url = f"{base_url}/inmuebles/{op}/{slug}/" if slug else f"{base_url}/inmuebles/{op}/"
    elif portal == "corotos":
        url = f"{base_url}/inmuebles/{op}/{slug}" if slug else f"{base_url}/inmuebles/{op}/"
    elif portal == "infocasas":
        url = f"{base_url}/{op}/inmuebles/{slug}" if slug else f"{base_url}/{op}/inmuebles/"
    elif portal == "tuinmueble":
        url = f"{base_url}/{op}/inmuebles/{slug}" if slug else f"{base_url}/{op}/inmuebles/"
    elif portal == "olx":
        url = f"{base_url}/inmuebles/{slug}_g" if slug else f"{base_url}/inmuebles/venta/"
    elif portal == "rentahouse":
        url = f"{base_url}/inmuebles_{op}_{slug}.html" if slug else f"{base_url}/casa_en_{op}.html"
    elif portal == "remax":
        ubi = slug.replace("-", "+") if slug else "Venezuela"
        url = f"{base_url}/inmuebles/casa-o-townhouse/{op}?ubi={ubi}"
    else:
        url = f"{base_url}/inmuebles/{op}/{slug}" if slug else base_url
    return _paginate(url, page, portal)


def _build_argentina_url(
    portal: str, base_url: str, op: str, slug: str, page: int, location: dict
) -> str:
    if portal == "mercadolibre":
        url = f"{base_url}/inmuebles/{op}/{slug}/" if slug else f"{base_url}/inmuebles/{op}/"
    elif portal == "zonaprop":
        if location.get("zonaprop_path"):
            path = location["zonaprop_path"]
            path = path if path.endswith(".html") else f"{path}.html"
            url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        else:
            suffix = slug or "argentina"
            url = f"{base_url}/inmuebles-{op}-{suffix}.html"
    elif portal == "argenprop":
        url = f"{base_url}/inmuebles/{op}/{slug}" if slug else f"{base_url}/inmuebles/{op}"
    elif portal == "properati":
        url = f"{base_url}/s/{op}/{slug}" if slug else f"{base_url}/s/{op}"
    elif portal == "toctoc":
        url = f"{base_url}/{op}/{slug}" if slug else f"{base_url}/{op}"
    elif portal == "buscainmueble":
        url = f"{base_url}/{op}/{slug}/" if slug else f"{base_url}/{op}/"
    elif portal == "lamudi":
        rent_path = "for-rent" if op == "alquiler" else "for-sale"
        url = f"{base_url}/{rent_path}/{slug}/" if slug else f"{base_url}/{rent_path}/"
    elif portal == "clarin":
        path = (
            "/inicio/index#!/5/listado/nivel-estructura/Inmuebles/_Top:Alquiler%20Ofrecido"
            if op == "alquiler"
            else "/inicio/index#!/1/listado/nivel-estructura/Inmuebles"
        )
        url = f"{base_url.rstrip('/')}{path}"
    elif portal == "remax":
        listing_type = "rent" if op == "alquiler" else "buy"
        if slug:
            url = f"{base_url}/listings/{listing_type}?location={slug}"
        else:
            url = f"{base_url}/listings/{listing_type}?"
    elif portal == "century21":
        listing_type = "rent" if op == "alquiler" else "buy"
        url = (
            f"{base_url}/listings/{listing_type}?location={slug}"
            if slug else f"{base_url}/listings/{listing_type}?"
        )
    else:
        url = f"{base_url}/{op}/{slug}" if slug else base_url
    return _paginate(url, page, portal)


def apply_location_to_property(prop, location: dict):
    """Enriquece una Property con datos geográficos del target de scraping."""
    prop.estado_provincia = location.get("estado_provincia", "")
    prop.localidad = location.get("localidad", "") or location.get("estado_provincia", "")
    prop.sub_localidad = location.get("sub_localidad", "")
    if location and not prop.ubicacion:
        prop.ubicacion = location_label(location)
    elif location:
        label = location_label(location)
        if label.lower() not in (prop.ubicacion or "").lower():
            prop.ubicacion = f"{prop.ubicacion}, {label}" if prop.ubicacion else label
