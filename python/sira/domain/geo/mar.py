"""Clasificación epicentro mar/tierra (reglas puras, sin I/O)."""
from __future__ import annotations

import re

_RE_USGS_CERCA_CIUDAD = re.compile(
    r"\d+(?:\.\d+)?\s*km\s+[NSEW]{1,3}\s+of\s+",
    re.IGNORECASE,
)

_MAR_EN_LUGAR = (
    " sea", "seaa", "ocean", "océano", "oceano", " mediterranean", " atlantic",
    "golfo", "gulf", " strait", "estrecho", " channel", "canal ", " mar ",
    "tyrrhenian", "balearic", "alboran", "alborán", "ionian", "ionio",
)

_ZONAS_MARITIMAS: tuple[tuple[float, float, float, float], ...] = (
    (35.45, 36.85, -7.8, -4.8),
    (35.45, 37.2, -4.8, -2.0),
    (36.0, 39.5, -2.0, 0.85),
    (38.2, 41.8, 0.85, 3.2),
    (39.5, 43.2, -1.2, 4.5),
    (36.0, 40.5, -12.0, -9.4),
    (35.5, 37.0, -9.4, -6.8),
    (27.0, 29.8, -18.8, -13.2),
)


def usgs_tsunami_flag(usgs_tsunami: int | bool | None) -> bool:
    try:
        return int(usgs_tsunami or 0) == 1
    except (TypeError, ValueError):
        return bool(usgs_tsunami)


def usgs_lugar_indica_mar(lugar: str | None) -> bool:
    txt = f" {(lugar or '').lower()} "
    return any(k in txt for k in _MAR_EN_LUGAR)


def usgs_lugar_indica_tierra(lugar: str | None) -> bool:
    """Patrón USGS «X km DIR of Ciudad» implica epicentro en tierra firme."""
    if not lugar:
        return False
    return bool(_RE_USGS_CERCA_CIUDAD.search(lugar))


def _en_tierra_iberica(lat: float, lon: float) -> bool:
    if 38.2 <= lat <= 40.8 and 0.05 <= lon <= 3.0:
        return False
    # Interior Murcia (Librilla / Alhama): no marcar como mar por la caja Alborán.
    if 37.55 <= lat <= 38.35 and -2.05 <= lon <= -1.05:
        return True
    if 36.8 <= lat <= 38.2 and -2.0 <= lon <= 1.5:
        return False
    if 27.45 <= lat <= 29.65 and -18.55 <= lon <= -12.95:
        return True
    if 38.62 <= lat <= 40.12 and 1.05 <= lon <= 4.42:
        return True
    if 35.85 <= lat <= 35.95 and -5.45 <= lon <= -5.25:
        return True
    if 35.22 <= lat <= 35.35 and -3.05 <= lon <= -2.85:
        return True
    if 36.05 <= lat <= 43.85 and -9.55 <= lon <= 3.35:
        if lon >= 0.2 and lat < 37.0:
            return False
        if lat < 36.25 and lon < -2.5:
            return False
        if lon < -9.35 and lat > 41.5:
            return False
        return True
    return False


def _en_zona_maritima(lat: float, lon: float) -> bool:
    return any(
        lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
        for lat_min, lat_max, lon_min, lon_max in _ZONAS_MARITIMAS
    )


def epicentro_en_mar(
    lat: float,
    lon: float,
    *,
    lugar: str | None = None,
    profundidad_km: float = 0,
    usgs_tsunami: int | bool | None = None,
) -> bool:
    """Epicentro en el mar (no tierra firme ibérica)."""
    if usgs_lugar_indica_mar(lugar):
        return True
    if _en_tierra_iberica(lat, lon):
        return False
    if usgs_tsunami_flag(usgs_tsunami):
        return True
    if usgs_lugar_indica_tierra(lugar):
        return False
    if profundidad_km > 300:
        return False
    if _en_zona_maritima(lat, lon):
        return True
    return False
