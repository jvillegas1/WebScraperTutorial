"""URLs directas de listados Zonaprop (por tipo y barrio/partido)."""

from typing import List


def _target(
    path: str,
    *,
    estado_provincia: str,
    localidad: str,
    sub_localidad: str,
    operacion: str = "venta",
) -> dict:
    slug = path.replace(".html", "")
    return {
        "id": f"ar_zp_{slug.replace('-', '_')}",
        "region": "argentina",
        "tipo": "zonaprop_listing",
        "operacion": operacion,
        "estado_provincia": estado_provincia,
        "localidad": localidad,
        "sub_localidad": sub_localidad,
        "zonaprop_path": path if path.endswith(".html") else f"{path}.html",
        "slug": {"zonaprop": slug, "default": slug},
    }


CABA = "Ciudad Autónoma de Buenos Aires"
GBA = "Gran Buenos Aires"
BA = "Buenos Aires"

# Rutas solicitadas (sin duplicados)
ZONAPROP_EXTRA_PATHS: List[str] = [
    "departamentos-venta-caseros-tres-de-febrero.html",
    "casas-venta-ciudad-jardin-lomas-del-palomar.html",
    "ph-venta-caseros-tres-de-febrero.html",
    "casas-venta-caseros-tres-de-febrero.html",
    "casas-venta-flores.html",
    "departamentos-venta-flores.html",
    "ph-venta-flores.html",
    "casas-venta-almagro.html",
    "departamentos-venta-almagro.html",
    "ph-venta-almagro.html",
    "casas-venta-parque-chacabuco.html",
    "departamentos-venta-parque-chacabuco.html",
    "ph-venta-parque-chacabuco.html",
    "casas-venta-la-paternal.html",
    "departamentos-venta-la-paternal.html",
    "ph-venta-la-paternal.html",
    "casas-venta-agronomia.html",
    "departamentos-venta-agronomia.html",
    "ph-venta-agronomia.html",
    "casas-venta-boedo.html",
    "departamentos-venta-boedo.html",
    "ph-venta-boedo.html",
    "casas-venta-san-cristobal.html",
    "departamentos-venta-san-cristobal.html",
    "ph-venta-san-cristobal.html",
]

_PATH_LOCALITY = {
    "caseros-tres-de-febrero": (BA, GBA, "Caseros"),
    "ciudad-jardin-lomas-del-palomar": (BA, GBA, "Ciudad Jardín Lomas del Palomar"),
    "flores": (CABA, "CABA", "Flores"),
    "almagro": (CABA, "CABA", "Almagro"),
    "parque-chacabuco": (CABA, "CABA", "Parque Chacabuco"),
    "la-paternal": (CABA, "CABA", "La Paternal"),
    "agronomia": (CABA, "CABA", "Agronomía"),
    "boedo": (CABA, "CABA", "Boedo"),
    "san-cristobal": (CABA, "CABA", "San Cristóbal"),
}


def _locality_for_path(path: str) -> tuple:
    slug = path.replace(".html", "")
    for suffix, meta in _PATH_LOCALITY.items():
        if slug.endswith(suffix):
            return meta
    return ("Argentina", "Argentina", "")


def get_zonaprop_extra_targets() -> List[dict]:
    """Convierte rutas Zonaprop en objetivos de scraping geográficos."""
    targets = []
    seen = set()
    for path in ZONAPROP_EXTRA_PATHS:
        if path in seen:
            continue
        seen.add(path)
        estado, loc, sub = _locality_for_path(path)
        targets.append(
            _target(path, estado_provincia=estado, localidad=loc, sub_localidad=sub)
        )
    return targets
