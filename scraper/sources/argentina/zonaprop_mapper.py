"""Mapeo de URLs .html de Zonaprop a parámetros de búsqueda."""

import re
from typing import Optional, Tuple

OPERATION_TYPE = {
    "venta": "1",
    "alquiler": "2",
    "alquiler-temporario": "3",
}

REAL_ESTATE_TYPE = {
    "departamentos": "2",
    "casas": "1",
    "ph": "3",
    "inmuebles": "2",
    "terrenos": "4",
    "locales-comerciales": "5",
    "oficinas": "6",
}

# Slug de URL -> texto para autocompletado de ubicación en Zonaprop
LOCATION_QUERY = {
    "almagro": "Almagro, Capital Federal",
    "flores": "Flores, Capital Federal",
    "parque-chacabuco": "Parque Chacabuco, Capital Federal",
    "la-paternal": "La Paternal, Capital Federal",
    "agronomia": "Agronomía, Capital Federal",
    "boedo": "Boedo, Capital Federal",
    "san-cristobal": "San Cristóbal, Capital Federal",
    "caseros-tres-de-febrero": "Caseros, GBA Oeste",
    "ciudad-jardin-lomas-del-palomar": "Ciudad Jardín Lomas del Palomar, GBA Oeste",
}


def parse_listing_path(path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    departamentos-venta-almagro.html ->
    (departamentos, venta, almagro)
    """
    slug = path.replace(".html", "")
    slug = re.sub(r"-pagina-\d+$", "", slug)
    for op in ("alquiler-temporario", "alquiler", "venta"):
        token = f"-{op}-"
        if token in slug:
            left, location_slug = slug.split(token, 1)
            return left, op, location_slug or None
    return None, None, None


def build_search_parameters(
    path: str,
    *,
    location_id: Optional[str] = None,
) -> Optional[str]:
    type_slug, operation, location_slug = parse_listing_path(path)
    if not operation:
        return None
    op_id = OPERATION_TYPE.get(operation)
    if not op_id:
        return None
    type_id = REAL_ESTATE_TYPE.get(type_slug or "inmuebles", "2")
    parts = [
        f"operation_type:{op_id}",
        f"real_estate_type:{type_id}",
        "exclude_postings_contacted:false",
    ]
    if location_id:
        parts.append(f"location:{location_id}")
    return ";".join(parts) + ";"


def location_query_for_slug(location_slug: str) -> str:
    if location_slug in LOCATION_QUERY:
        return LOCATION_QUERY[location_slug]
    return location_slug.replace("-", " ").title()
