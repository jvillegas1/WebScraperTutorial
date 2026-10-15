"""
Configuración por región (tier): Venezuela y Argentina.
Cada región define portales, moneda, alcance geográfico y frecuencia de scraping.
"""

REGIONS = {
    "venezuela": {
        "label": "Venezuela",
        "flag": "🇻🇪",
        "scope": "national",
        "location_label": "Venezuela",
        "default_currency": "USD",
        "scraping_interval_hours": 6,
        "opportunity_check_interval_hours": 1,
        "active_sources": {
            "mercadolibre": True,
            "tuinmueble": True,
            "infocasas": True,
            "olx": True,
            "rentahouse": True,
            "remax": True,
        },
        "scraping": {
            "city": "",
            "operation": "venta",
            "operations": ["venta", "alquiler"],
            "scope": "national",
            "location_label": "Venezuela",
            "default_currency": "USD",
            "delay_between_requests": 3,
            "delay_jitter": 2,
            "max_retries": 3,
            "retry_backoff_factor": 2,
            "timeout": 30,
            "max_pages_per_source": 50,
            "max_pages_per_location": 3,
            "location_ids": None,
        },
        "opportunity_rules": {
            "relative_threshold": 0.15,
            "price_drop_threshold": 0.05,
            "absolute_thresholds": {
                "casa": 50000,
                "apartamento": 35000,
                "terreno": 20000,
                "local": 30000,
                "oficina": 25000,
                "townhouse": 45000,
                "penthouse": 60000,
                "default": 40000,
            },
        },
        "portal_urls": {
            "mercadolibre": "https://listado.mercadolibre.com.ve",
            "tuinmueble": "https://www.tuinmueble.com",
            "infocasas": "https://www.infocasas.com.ve",
            "olx": "https://www.olx.com.ve",
            "rentahouse": "https://rentahouse.com.ve",
            "remax": "https://www.remax.com.ve",
        },
    },
    "argentina": {
        "label": "Argentina",
        "flag": "🇦🇷",
        "scope": "national",
        "location_label": "Argentina",
        "default_currency": "USD",
        "scraping_interval_hours": 3,
        "opportunity_check_interval_hours": 0.5,
        "active_sources": {
            "mercadolibre": True,
            "zonaprop": True,
            "argenprop": True,
            "properati": True,
            "toctoc": False,
            "buscainmueble": True,
            "lamudi": False,
            "clarin": True,
            "remax": True,
            "century21": True,
        },
        "scraping": {
            "city": "",
            "operation": "venta",
            "operations": ["venta", "alquiler"],
            "scope": "national",
            "location_label": "Argentina",
            "default_currency": "USD",
            "delay_between_requests": 2,
            "delay_jitter": 1,
            "max_retries": 3,
            "retry_backoff_factor": 2,
            "timeout": 60,
            "playwright_wait_until": "domcontentloaded",
            "playwright_render_wait_ms": 1500,
            "max_pages_per_source": 80,
            "max_pages_per_location": 3,
            "location_ids": None,
            "include_zonaprop_extra": True,
            "zonaprop_scrape_scope": "extra_only",
            "zonaprop_headless": False,
            "zonaprop_browser_channel": "msedge",
        },
        "opportunity_rules": {
            "relative_threshold": 0.12,
            "price_drop_threshold": 0.03,
            "absolute_thresholds": {
                "casa": 120000,
                "apartamento": 80000,
                "terreno": 40000,
                "local": 70000,
                "oficina": 60000,
                "townhouse": 100000,
                "penthouse": 150000,
                "default": 90000,
            },
        },
        "portal_urls": {
            "mercadolibre": "https://listado.mercadolibre.com.ar",
            "zonaprop": "https://www.zonaprop.com.ar",
            "argenprop": "https://www.argenprop.com",
            "properati": "https://www.properati.com.ar",
            "toctoc": "https://www.toctoc.com.ar",
            "buscainmueble": "https://www.buscainmueble.com",
            "lamudi": "https://www.lamudi.com.ar",
            "clarin": "https://clasificados.clarin.com",
            "remax": "https://www.remax.com.ar",
            "century21": "https://century21.com.ar",
        },
    },
}


def get_region_config(region: str) -> dict:
    """Obtiene la configuración de una región."""
    if region not in REGIONS:
        raise ValueError(f"Región no soportada: {region}. Disponibles: {list(REGIONS.keys())}")
    return REGIONS[region]


def get_active_sources(region: str) -> dict:
    """Portales activos para una región."""
    return get_region_config(region)["active_sources"]


def list_regions() -> list:
    return list(REGIONS.keys())


def get_scraping_operations(scraping_config: dict) -> list:
    """Operaciones a scrapear: venta, alquiler o ambas."""
    operations = scraping_config.get("operations")
    from .parsers.property_parser import PropertyParser
    if operations:
        return [PropertyParser.normalize_operation(op) for op in operations]
    op = scraping_config.get("operation", "venta")
    return [PropertyParser.normalize_operation(op)]
