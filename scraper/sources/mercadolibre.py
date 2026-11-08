"""
Scraper para MercadoLibre Venezuela - Inmuebles.
Usa HTTP contra inmuebles.mercadolibre.com.ve (listado.* suele bloquear bots).
"""

import re
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

import structlog
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from .mercadolibre_listings import (
    is_mercadolibre_blocked,
    parse_mercadolibre_listing_page,
)
from ..parsers.property_parser import Property, PropertyParser

logger = structlog.get_logger(__name__)


class MercadoLibreScraper(BaseScraper):
    """Scraper HTTP para MercadoLibre Venezuela."""

    name = "mercadolibre"
    region = "venezuela"
    base_url = "https://inmuebles.mercadolibre.com.ve"
    listing_prefix = "MLV"

    def _get_headers(self) -> Dict[str, str]:
        headers = super()._get_headers()
        headers["Accept-Language"] = "es-VE,es;q=0.9,en;q=0.8"
        return headers

    def _get_soup(self, url: str) -> Optional[BeautifulSoup]:
        soup = super()._get_soup(url)
        if soup is None:
            self._last_fetch_blocked = False
            return None
        if is_mercadolibre_blocked(str(soup)):
            self._last_fetch_blocked = True
            logger.warning(
                "mercadolibre_blocked",
                url=url,
                region=self.region,
                hint="MercadoLibre VE exige tráfico residencial o sesión de navegador",
            )
            return None
        self._last_fetch_blocked = False
        return soup

    def scrape(
        self,
        city: str = "Maracaibo",
        operation: str = "venta",
    ) -> Generator[Property, None, None]:
        """Igual que BaseScraper, pero aborta si varias localidades seguidas están bloqueadas."""
        self._start_time = datetime.now()
        self._request_count = 0
        total_found = 0
        targets = self._resolve_scrape_targets()
        saved_location = self.config.get("current_location")
        empty_blocked_streak = 0
        max_empty_blocked = self.config.get("mercadolibre_max_blocked_locations", 3)

        logger.info(
            "scraping_started",
            scraper=self.name,
            city=city,
            operation=operation,
            locations=len(targets),
        )

        for location in targets:
            loc_op = location.get("operacion")
            if loc_op and PropertyParser.normalize_operation(operation) != loc_op:
                continue
            self.config["current_location"] = location
            found_here = 0
            for prop in self._scrape_single_location(city, operation):
                found_here += 1
                total_found += 1
                empty_blocked_streak = 0
                yield prop

            if found_here == 0 and getattr(self, "_last_fetch_blocked", False):
                empty_blocked_streak += 1
                if empty_blocked_streak >= max_empty_blocked:
                    logger.warning(
                        "mercadolibre_abort_blocked_streak",
                        streak=empty_blocked_streak,
                        region=self.region,
                    )
                    break
            else:
                empty_blocked_streak = 0

        if saved_location is not None:
            self.config["current_location"] = saved_location
        else:
            self.config.pop("current_location", None)

        duration = (datetime.now() - self._start_time).total_seconds()
        logger.info(
            "scraping_completed",
            scraper=self.name,
            city=city,
            operation=operation,
            locations=len(targets),
            total_properties=total_found,
            total_requests=self._request_count,
            duration_seconds=duration,
        )

    def _build_search_url(self, city: str, operation: str, page: int = 1) -> str:
        city_slug = city.lower().replace(" ", "-") if city else ""
        op = PropertyParser.normalize_operation(operation)
        scope = self.config.get("scope", "national")
        if scope == "national" or not city_slug:
            base = f"{self.base_url}/{op}/"
        else:
            base = f"{self.base_url}/{op}/zulia/{city_slug}/"
        if page > 1:
            offset = (page - 1) * 48 + 1
            base = f"{base.rstrip('/')}_Desde_{offset}"
        return base

    def _parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        return parse_mercadolibre_listing_page(soup, self.listing_prefix)

    def _parse_property_detail(self, raw_data: Dict[str, Any]) -> Optional[Property]:
        try:
            precio, moneda = PropertyParser.normalize_price(raw_data.get("precio_raw", ""))
            if precio is None or precio <= 0:
                return None

            titulo = raw_data.get("titulo", "")
            ubicacion = PropertyParser.normalize_location(
                raw_data.get("ubicacion", ""),
                self.config.get("location_label", "Venezuela"),
            )
            habitaciones = PropertyParser.extract_number(raw_data.get("habitaciones_raw", ""))
            if not habitaciones:
                hab_match = re.search(r"(\d+)\s*(?:hab|dorm|cuarto)", titulo, re.I)
                if hab_match:
                    habitaciones = int(hab_match.group(1))

            banos = PropertyParser.extract_number(raw_data.get("banos_raw", ""))
            imagenes = [raw_data["imagen"]] if raw_data.get("imagen") else []

            return Property(
                id_externo=raw_data["id_externo"],
                source=self.name,
                region=self.region,
                titulo=PropertyParser.clean_text(titulo),
                precio=precio,
                moneda=moneda,
                ubicacion=ubicacion,
                tipo_inmueble=PropertyParser.normalize_property_type(titulo),
                url=raw_data["url"],
                fecha_scraping=datetime.now(),
                metros_cuadrados=PropertyParser.extract_area(
                    raw_data.get("metros_raw", "") or titulo
                ),
                habitaciones=habitaciones,
                banos=banos,
                imagenes=imagenes,
            )
        except Exception as e:
            logger.error("property_normalization_error", error=str(e), raw_data=raw_data)
            return None

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        next_selectors = [
            'a.andes-pagination__link[title="Siguiente"]',
            'li.andes-pagination__button--next a',
            'a[title="Siguiente"]',
            f'a[href*="_Desde_{current_page * 48 + 1}"]',
        ]
        for selector in next_selectors:
            if soup.select_one(selector):
                return True
        pagination = soup.select_one(".andes-pagination")
        if pagination:
            current = pagination.select_one(".andes-pagination__button--current")
            all_pages = pagination.select(".andes-pagination__button")
            if current and all_pages:
                last_text = all_pages[-1].get_text(strip=True)
                if last_text.isdigit():
                    return current_page < int(last_text)
        return False
