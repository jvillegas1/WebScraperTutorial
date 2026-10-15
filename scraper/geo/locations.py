"""
Catálogo geográfico para scraping y filtros del dashboard.

Venezuela: 24 entidades federales (23 estados + Distrito Capital).
Argentina: 24 jurisdicciones (23 provincias + CABA), barrios de CABA y partidos del GBA.
"""

from __future__ import annotations

from typing import Dict, List, Optional


def _slug(text: str) -> str:
    return (
        text.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
    )


def _ve_estado(name: str, ml_slug: Optional[str] = None) -> dict:
    s = ml_slug or _slug(name)
    return {
        "id": f"ve_{s}",
        "region": "venezuela",
        "tipo": "estado",
        "estado_provincia": name,
        "localidad": "",
        "sub_localidad": "",
        "slug": {
            "mercadolibre": s,
            "corotos": s,
            "infocasas": s,
            "tuinmueble": s,
            "olx": s,
            "default": s,
        },
    }


VENEZUELA_ESTADOS: List[dict] = [
    _ve_estado("Amazonas"),
    _ve_estado("Anzoátegui", "anzoategui"),
    _ve_estado("Apure"),
    _ve_estado("Aragua"),
    _ve_estado("Barinas"),
    _ve_estado("Bolívar", "bolivar"),
    _ve_estado("Carabobo"),
    _ve_estado("Cojedes"),
    _ve_estado("Delta Amacuro", "delta-amacuro"),
    _ve_estado("Distrito Capital", "distrito-capital"),
    _ve_estado("Falcón", "falcon"),
    _ve_estado("Guárico", "guarico"),
    _ve_estado("La Guaira", "la-guaira"),
    _ve_estado("Lara"),
    _ve_estado("Mérida", "merida"),
    _ve_estado("Miranda"),
    _ve_estado("Monagas"),
    _ve_estado("Nueva Esparta", "nueva-esparta"),
    _ve_estado("Portuguesa"),
    _ve_estado("Sucre"),
    _ve_estado("Táchira", "tachira"),
    _ve_estado("Trujillo"),
    _ve_estado("Yaracuy"),
    _ve_estado("Zulia"),
]


def _ar_provincia(name: str, ml_slug: Optional[str] = None) -> dict:
    s = ml_slug or _slug(name)
    return {
        "id": f"ar_{s}",
        "region": "argentina",
        "tipo": "provincia",
        "estado_provincia": name,
        "localidad": name,
        "sub_localidad": "",
        "slug": {
            "mercadolibre": s,
            "zonaprop": s,
            "argenprop": s,
            "properati": s,
            "default": s,
        },
    }


ARGENTINA_PROVINCIAS: List[dict] = [
    _ar_provincia("Buenos Aires", "buenos-aires"),
    _ar_provincia("Catamarca"),
    _ar_provincia("Chaco"),
    _ar_provincia("Chubut"),
    _ar_provincia("Córdoba", "cordoba"),
    _ar_provincia("Corrientes"),
    _ar_provincia("Entre Ríos", "entre-rios"),
    _ar_provincia("Formosa"),
    _ar_provincia("Jujuy"),
    _ar_provincia("La Pampa", "la-pampa"),
    _ar_provincia("La Rioja", "la-rioja"),
    _ar_provincia("Mendoza"),
    _ar_provincia("Misiones"),
    _ar_provincia("Neuquén", "neuquen"),
    _ar_provincia("Río Negro", "rio-negro"),
    _ar_provincia("Salta"),
    _ar_provincia("San Juan", "san-juan"),
    _ar_provincia("San Luis", "san-luis"),
    _ar_provincia("Santa Cruz", "santa-cruz"),
    _ar_provincia("Santa Fe", "santa-fe"),
    _ar_provincia("Santiago del Estero", "santiago-del-estero"),
    _ar_provincia("Tierra del Fuego", "tierra-del-fuego"),
    _ar_provincia("Tucumán", "tucuman"),
    {
        "id": "ar_caba",
        "region": "argentina",
        "tipo": "provincia",
        "estado_provincia": "Ciudad Autónoma de Buenos Aires",
        "localidad": "CABA",
        "sub_localidad": "",
        "slug": {
            "mercadolibre": "capital-federal",
            "zonaprop": "capital-federal",
            "argenprop": "capital-federal",
            "properati": "capital-federal",
            "default": "capital-federal",
        },
    },
]


CABA_BARRIOS: List[dict] = [
    {
        "id": f"ar_caba_{_slug(b)}",
        "region": "argentina",
        "tipo": "barrio",
        "estado_provincia": "Ciudad Autónoma de Buenos Aires",
        "localidad": "CABA",
        "sub_localidad": b,
        "parent_division": "Ciudad Autónoma de Buenos Aires",
        "slug": {
            "mercadolibre": f"capital-federal/{_slug(b)}",
            "zonaprop": f"capital-federal-{_slug(b)}",
            "argenprop": f"capital-federal/{_slug(b)}",
            "properati": f"capital-federal-{_slug(b)}",
            "default": f"capital-federal-{_slug(b)}",
        },
    }
    for b in [
        "Agronomía", "Almagro", "Balvanera", "Barracas", "Belgrano", "Boedo",
        "Caballito", "Chacarita", "Colegiales", "Constitución", "Flores",
        "Floresta", "La Boca", "La Paternal", "Liniers", "Mataderos",
        "Montserrat", "Núñez", "Palermo", "Parque Patricios", "Puerto Madero",
        "Recoleta", "Retiro", "Saavedra", "San Cristóbal", "San Nicolás",
        "San Telmo", "Villa Crespo", "Villa Devoto", "Villa Lugano", "Villa Luro",
        "Villa Ortúzar", "Villa Pueyrredón", "Villa Urquiza", "Villa del Parque",
    ]
]


GBA_PARTIDOS: List[dict] = [
    {
        "id": f"ar_gba_{_slug(p)}",
        "region": "argentina",
        "tipo": "partido",
        "estado_provincia": "Buenos Aires",
        "localidad": "Gran Buenos Aires",
        "sub_localidad": p,
        "parent_division": "Buenos Aires",
        "slug": {
            "mercadolibre": f"buenos-aires/{_slug(p)}",
            "zonaprop": f"gba-{_slug(p)}",
            "argenprop": f"buenos-aires/{_slug(p)}",
            "properati": f"gba-{_slug(p)}",
            "default": f"gba-{_slug(p)}",
        },
    }
    for p in [
        "Avellaneda", "Lanús", "Quilmes", "Berazategui", "Florencio Varela",
        "Lomas de Zamora", "Almirante Brown", "Esteban Echeverría", "Ezeiza",
        "Hurlingham", "Ituzaingó", "José C. Paz", "La Matanza", "Malvinas Argentinas",
        "Merlo", "Moreno", "Morón", "San Fernando", "San Isidro", "San Miguel",
        "Tigre", "Tres de Febrero", "Vicente López", "Presidente Perón",
    ]
]


def get_all_locations(region: str) -> List[dict]:
    if region == "venezuela":
        return list(VENEZUELA_ESTADOS)
    if region == "argentina":
        locs = list(ARGENTINA_PROVINCIAS)
        locs.extend(CABA_BARRIOS)
        locs.extend(GBA_PARTIDOS)
        return locs
    return []


def get_location_by_id(location_id: str) -> Optional[dict]:
    for loc in get_all_locations("venezuela") + get_all_locations("argentina"):
        if loc["id"] == location_id:
            return loc
    return None


def get_scrape_targets(region: str, location_ids: Optional[List[str]] = None) -> List[dict]:
    """Objetivos de scraping: todos o un subconjunto por id."""
    all_locs = get_all_locations(region)
    if not location_ids:
        return all_locs
    id_set = set(location_ids)
    return [loc for loc in all_locs if loc["id"] in id_set]


def list_divisions(region: str) -> List[str]:
    """Estados (VE) o provincias (AR) para filtros de primer nivel."""
    if region == "venezuela":
        return sorted({loc["estado_provincia"] for loc in VENEZUELA_ESTADOS})
    divisions = sorted({loc["estado_provincia"] for loc in ARGENTINA_PROVINCIAS})
    return divisions


def list_sub_localities(region: str, division: str) -> List[str]:
    """Barrios (CABA) o partidos (GBA) bajo una división."""
    if not division or division == "Todos":
        return []
    if region == "argentina":
        if division == "Ciudad Autónoma de Buenos Aires":
            return sorted({loc["sub_localidad"] for loc in CABA_BARRIOS})
        if division == "Buenos Aires":
            return sorted({loc["sub_localidad"] for loc in GBA_PARTIDOS})
    return []


def get_filter_options(region: str) -> dict:
    return {
        "divisions": ["Todos"] + list_divisions(region),
        "sub_localities_caba": sorted({loc["sub_localidad"] for loc in CABA_BARRIOS}),
        "sub_localities_gba": sorted({loc["sub_localidad"] for loc in GBA_PARTIDOS}),
    }


def location_label(loc: dict) -> str:
    parts = [loc.get("estado_provincia", "")]
    if loc.get("localidad") and loc["localidad"] != loc.get("estado_provincia"):
        parts.append(loc["localidad"])
    if loc.get("sub_localidad"):
        parts.append(loc["sub_localidad"])
    return ", ".join(p for p in parts if p)
