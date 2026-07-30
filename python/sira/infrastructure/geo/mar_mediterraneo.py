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


def _en_mar_mediterraneo_west(lat: float, lon: float) -> bool:
    """Envolvente aproximada del Mediterráneo occidental / Alborán."""
    if _en_corredor_mar_andalucia(lat, lon):
        return True
    if lat < 35.45 or lat > 43.55 or lon < -6.05 or lon > 9.50:
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


def land_overlay_boxes() -> list[tuple[float, float, float, float]]:
    """
    Rectángulos de tierra a dibujar ENCIMA de la capa SST.

    Formato: (lat_min, lat_max, lon_min, lon_max).
    Cubren Magreb y sur de Francia (fuera del IGN).
    """
    return [
        # Marruecos / Argelia occidental
        (30.00, 35.90, -6.50, -2.50),
        (30.00, 35.40, -2.50, -1.20),
        (30.00, 35.85, -1.20, 0.50),
        # Argelia central / oriental
        (30.00, 36.50, 0.50, 2.50),
        (30.00, 36.80, 2.50, 4.50),
        (30.00, 36.90, 4.50, 6.50),
        (30.00, 37.10, 6.50, 9.50),
        # Sur de Francia
        (42.55, 46.50, 1.80, 3.20),
        (43.05, 46.50, 3.20, 4.80),
        (43.15, 46.50, 4.80, 6.20),
        (43.20, 46.50, 6.20, 8.20),
    ]
