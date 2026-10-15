"""Scrapers de portales inmobiliarios de Argentina."""

from .mercadolibre import MercadoLibreArScraper
from .zonaprop import ZonapropScraper
from .argenprop import ArgenpropScraper
from .properati import ProperatiScraper
from .toctoc import ToctocScraper
from .buscainmueble import BuscaInmuebleScraper
from .lamudi import LamudiScraper
from .clarin import ClarinScraper
from .remax import RemaxArScraper
from .century21 import Century21Scraper

ARGENTINA_SCRAPER_REGISTRY = {
    "mercadolibre": MercadoLibreArScraper,
    "zonaprop": ZonapropScraper,
    "argenprop": ArgenpropScraper,
    "properati": ProperatiScraper,
    "toctoc": ToctocScraper,
    "buscainmueble": BuscaInmuebleScraper,
    "lamudi": LamudiScraper,
    "clarin": ClarinScraper,
    "remax": RemaxArScraper,
    "century21": Century21Scraper,
}

__all__ = list(ARGENTINA_SCRAPER_REGISTRY.keys()) + ["ARGENTINA_SCRAPER_REGISTRY"]
