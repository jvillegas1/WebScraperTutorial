"""
Módulo de scrapers por región.
Venezuela: portales .ve | Argentina: mercado dinámico con 10 portales.
"""

from .base_scraper import BaseScraper
from .mercadolibre import MercadoLibreScraper
from .tuinmueble import TuInmuebleScraper
from .infocasas import InfoCasasScraper
from .olx import OLXScraper
from .rentahouse import RentaHouseScraper
from .remax import RemaxScraper
from .argentina import ARGENTINA_SCRAPER_REGISTRY

VENEZUELA_SCRAPER_REGISTRY = {
    "mercadolibre": MercadoLibreScraper,
    "tuinmueble": TuInmuebleScraper,
    "infocasas": InfoCasasScraper,
    "olx": OLXScraper,
    "rentahouse": RentaHouseScraper,
    "remax": RemaxScraper,
}

REGION_SCRAPER_REGISTRY = {
    "venezuela": VENEZUELA_SCRAPER_REGISTRY,
    "argentina": ARGENTINA_SCRAPER_REGISTRY,
}

# Compatibilidad legacy
SCRAPER_REGISTRY = VENEZUELA_SCRAPER_REGISTRY


def get_scraper_registry(region: str) -> dict:
    return REGION_SCRAPER_REGISTRY.get(region, {})


def get_scraper_class(region: str, source: str):
    registry = get_scraper_registry(region)
    return registry.get(source)


def list_sources(region: str) -> list:
    return list(get_scraper_registry(region).keys())


__all__ = [
    "BaseScraper",
    "MercadoLibreScraper",
    "TuInmuebleScraper",
    "InfoCasasScraper",
    "OLXScraper",
    "RentaHouseScraper",
    "RemaxScraper",
    "SCRAPER_REGISTRY",
    "VENEZUELA_SCRAPER_REGISTRY",
    "ARGENTINA_SCRAPER_REGISTRY",
    "REGION_SCRAPER_REGISTRY",
    "get_scraper_registry",
    "get_scraper_class",
    "list_sources",
]
