"""Datos geográficos y utilidades de búsqueda por localidad."""

from .locations import (
    VENEZUELA_ESTADOS,
    ARGENTINA_PROVINCIAS,
    CABA_BARRIOS,
    GBA_PARTIDOS,
    get_scrape_targets,
    get_filter_options,
    get_location_by_id,
    list_divisions,
    list_sub_localities,
)
from .url_builders import build_search_url

__all__ = [
    "VENEZUELA_ESTADOS",
    "ARGENTINA_PROVINCIAS",
    "CABA_BARRIOS",
    "GBA_PARTIDOS",
    "get_scrape_targets",
    "get_filter_options",
    "get_location_by_id",
    "list_divisions",
    "list_sub_localities",
    "build_search_url",
]
