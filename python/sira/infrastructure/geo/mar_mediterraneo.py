"""Puntos en mar (Mediterráneo occidental) sin invadir tierra."""
from __future__ import annotations

from functools import lru_cache

from sira.infrastructure.geo.bordes_clip import anillos_tierra, punto_en_tierra


def _en_corredor_mar_andalucia(lat: float, lon: float) -> bool:
    """Corredor marítimo Estrecho/Alborán pegado a Andalucía."""
    return 36.00 <= lat <= 36.55 and -5.90 <= lon <= -1.60


def _en_tierra_magreb(lat: float, lon: float) -> bool:
    """
    Tierra aproximada de Marruecos/Argelia/Túnez mediterráneos.

    IGN solo cubre España; sin esto CMEMS pinta costa magrebí como mar.
    """
    if lat >= 37.35 or lon < -6.2 or lon > 9.5:
        return False
    if _en_corredor_mar_andalucia(lat, lon):
        return False
    # Costa mediterránea magrebí (aprox. sur del litoral).
    if lon < -4.80:
        return lat < 35.95
    if lon < -2.50:
        return lat < 35.55
    if lon < -1.20:
        return lat < 35.35
    if lon < 0.50:
        return lat < 35.90
    if lon < 2.50:
        return lat < 36.55
    if lon < 4.50:
        return lat < 36.85
    if lon < 6.50:
        return lat < 36.95
    return lat < 37.15


def _en_tierra_francia_med(lat: float, lon: float) -> bool:
    """Tierra aproximada del sur de Francia (Golfo de León / Provenza)."""
    if lon < 1.80 or lon > 8.20:
        return False
    if lat < 42.35:
        return False
    # Costa francesa Med: por encima de esta línea ≈ tierra.
    if lon < 3.20:
        return lat > 42.55
    if lon < 4.80:
        return lat > 43.05
    if lon < 6.20:
        return lat > 43.15
    return lat > 43.20


def _en_tierra_corcega_cerdena(lat: float, lon: float) -> bool:
    """
    Tierra aproximada de Córcega y Cerdeña.

    CMEMS da valor sobre isla; sin máscara la SST tapa el contorno.
    Franjas estrechas para no comerse el mar alrededor.
    """
    # Córcega.
    if 41.36 <= lat <= 43.02 and 8.54 <= lon <= 9.57:
        return True
    # Cerdeña (franjas N→S).
    if 40.90 <= lat <= 41.25 and 8.50 <= lon <= 9.70:
        return True
    if 40.20 <= lat <= 40.90 and 8.25 <= lon <= 9.65:
        return True
    if 39.40 <= lat <= 40.20 and 8.30 <= lon <= 9.70:
        return True
    if 38.86 <= lat <= 39.40 and 8.40 <= lon <= 9.60:
        return True
    return False


def _en_mar_mediterraneo_west(lat: float, lon: float) -> bool:
    """Envolvente aproximada del Mediterráneo occidental / Alborán."""
    if _en_corredor_mar_andalucia(lat, lon):
        return True
    if lat < 35.45 or lat > 43.55 or lon < -6.05 or lon > 10.00:
        return False
    if lat <= 36.90:
        return lon >= -5.90
    if lat <= 38.60:
        return lon >= -3.10
    if lat <= 40.20:
        return lon >= -1.10
    if lat <= 42.35:
        return lon >= 0.10
    return lon >= 1.80


@lru_cache(maxsize=1)
def _anillos_ign() -> list[list[list[float]]]:
    return anillos_tierra()


def punto_en_mar_mediterraneo(lat: float, lon: float) -> bool:
    """True si el punto cae en mar (no tierra) dentro del bbox SST habitual."""
    if not _en_mar_mediterraneo_west(lat, lon):
        return False
    if punto_en_tierra(lon, lat, _anillos_ign()):
        return False
    if _en_tierra_magreb(lat, lon):
        return False
    if _en_tierra_francia_med(lat, lon):
        return False
    if _en_tierra_corcega_cerdena(lat, lon):
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
