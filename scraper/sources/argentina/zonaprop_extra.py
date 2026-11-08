"""URLs directas de listados Zonaprop (por tipo y barrio/partido)."""

from typing import List

from ...geo.locations import CABA_BARRIOS, barrio_slug

ZONAPROP_CABA_LISTING_TYPES = ("casas", "departamentos", "ph")


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

# GBA y listados puntuales fuera del catálogo CABA×3
ZONAPROP_GBA_PATHS: List[str] = [
    "departamentos-venta-caseros-tres-de-febrero.html",
    "casas-venta-ciudad-jardin-lomas-del-palomar.html",
    "ph-venta-caseros-tres-de-febrero.html",
    "casas-venta-caseros-tres-de-febrero.html",
]

_PATH_LOCALITY = {
    "caseros-tres-de-febrero": (BA, GBA, "Caseros"),
    "ciudad-jardin-lomas-del-palomar": (BA, GBA, "Ciudad Jardín Lomas del Palomar"),
}


def _locality_for_path(path: str) -> tuple:
    slug = path.replace(".html", "")
    for suffix, meta in _PATH_LOCALITY.items():
        if slug.endswith(suffix):
            return meta
    return ("Argentina", "Argentina", "")


def get_caba_zonaprop_targets(operacion: str = "venta") -> List[dict]:
    """
    Un objetivo por barrio y tipo de publicación (casas / departamentos / ph).
    Coincide con los 3 formatos de URL que usa Zonaprop en CABA.
    """
    targets: List[dict] = []
    seen_ids: set[str] = set()
    for loc in CABA_BARRIOS:
        barrio = loc["sub_localidad"]
        slug = barrio_slug(barrio)
        for tipo in ZONAPROP_CABA_LISTING_TYPES:
            path = f"{tipo}-{operacion}-{slug}.html"
            target = _target(
                path,
                estado_provincia=CABA,
                localidad="CABA",
                sub_localidad=barrio,
                operacion=operacion,
            )
            if target["id"] in seen_ids:
                continue
            seen_ids.add(target["id"])
            targets.append(target)
    return targets


def get_zonaprop_extra_targets() -> List[dict]:
    """CABA: todos los barrios × 3 sitios Zonaprop + rutas GBA manuales."""
    targets: List[dict] = []
    seen: set[str] = set()

    for target in get_caba_zonaprop_targets():
        if target["id"] not in seen:
            targets.append(target)
            seen.add(target["id"])

    for path in ZONAPROP_GBA_PATHS:
        if path in seen:
            continue
        seen.add(path)
        estado, loc, sub = _locality_for_path(path)
        targets.append(
            _target(path, estado_provincia=estado, localidad=loc, sub_localidad=sub)
        )
    return targets


def get_caba_barrio_portal_slugs(barrio: str) -> dict:
    """Slugs por portal (ML / Zonaprop / Argenprop) para un barrio de CABA."""
    s = barrio_slug(barrio)
    return {
        "mercadolibre": f"capital-federal/{s}",
        "zonaprop": f"capital-federal-{s}",
        "argenprop": f"capital-federal/{s}",
    }
