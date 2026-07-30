"""Puntos en mar (Mediterráneo occidental) sin invadir tierra."""
from __future__ import annotations

from functools import lru_cache

from sira.infrastructure.geo.bordes_clip import anillos_tierra, punto_en_tierra

# Cajas aproximadas de tierra fuera del contorno IGN (Francia, N. África, etc.)
_LAND_BOXES: tuple[tuple[float, float, float, float], ...] = (
    (35.50, 36.35, -6.05, -1.85),
    (36.35, 37.25, -6.05, -0.15),
    (37.25, 37.85, -6.05, 0.35),
    (42.55, 43.55, -0.35, 2.00),
    (42.60, 43.55, 2.00, 4.20),
    (42.70, 43.55, 4.20, 6.20),
    (42.85, 43.55, 6.20, 7.95),
    (41.65, 42.45, 7.20, 7.95),
    (40.05, 41.20, 5.35, 7.95),
    (38.55, 40.15, 7.85, 8.05),
)


def _en_corredor_mar_andalucia(lat: float, lon: float) -> bool:
    """
    Corredor marítimo Estrecho/Alborán pegado a Andalucía.

    Evita que las cajas aproximadas de N. África tapen mar real en
    la salida mediterránea del Estrecho de Gibraltar.
    """
    return 36.00 <= lat <= 36.32 and -6.05 <= lon <= -1.70


def _en_mar_mediterraneo_west(lat: float, lon: float) -> bool:
    """
    Envolvente aproximada del Mediterráneo occidental / mar de Alborán.

    Evita colar Cantábrico y Atlántico solo por estar dentro del bbox general.
    """
    if _en_corredor_mar_andalucia(lat, lon):
        return True
    if lat < 35.45 or lat > 43.55 or lon < -6.05 or lon > 8.05:
        return False
    if lat <= 36.90:
        return lon >= -4.80
    if lat <= 38.60:
        return lon >= -3.10
    if lat <= 40.20:
        return lon >= -1.10
    if lat <= 42.35:
        return lon >= 0.10
    return lon >= 1.80


def _en_caja_land(lat: float, lon: float) -> bool:
    if _en_corredor_mar_andalucia(lat, lon):
        return False
    for lat_min, lat_max, lon_min, lon_max in _LAND_BOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


@lru_cache(maxsize=1)
def _anillos_ign() -> list[list[list[float]]]:
    return anillos_tierra()


def punto_en_mar_mediterraneo(lat: float, lon: float) -> bool:
    """True si el punto cae en mar (no tierra) dentro del bbox SST habitual."""
    if not _en_mar_mediterraneo_west(lat, lon):
        return False
    if punto_en_tierra(lon, lat, _anillos_ign()):
        return False
    if _en_caja_land(lat, lon):
        return False
    return True


def fraccion_mar_celda(lat: float, lon: float, half: float) -> float:
    """Proporción de muestras en mar dentro de la celda (centro + esquinas)."""
    muestras = [(lat, lon)]
    for dlat, dlon in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        muestras.append((lat + dlat * half, lon + dlon * half))
    mar = sum(1 for la, lo in muestras if punto_en_mar_mediterraneo(la, lo))
    return mar / len(muestras)


def celda_solo_mar(lat: float, lon: float, half: float) -> bool:
    """True si centro y esquinas de la celda están en mar (no invade tierra)."""
    return fraccion_mar_celda(lat, lon, half) >= 1.0
