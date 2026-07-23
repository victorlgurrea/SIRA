"""Geometría y distancias puras (sin I/O)."""
from __future__ import annotations

import math


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return round(111.2 * math.hypot(lat1 - lat2, (lon1 - lon2) * math.cos(math.radians(lat1))), 1)


def circle_perimeter(
    lat: float, lon: float, radius_km: float, points: int = 72,
) -> tuple[list[float], list[float]]:
    """Anillo cerrado del círculo de radio_km (solo contorno)."""
    if radius_km <= 0:
        return [float(lat)], [float(lon)]
    lat_rad = math.radians(lat)
    km_per_deg_lat = 111.2
    km_per_deg_lon = 111.2 * max(0.2, math.cos(lat_rad))
    lats: list[float] = []
    lons: list[float] = []
    for i in range(points + 1):
        ang = 2 * math.pi * i / points
        lats.append(lat + (radius_km * math.sin(ang)) / km_per_deg_lat)
        lons.append(lon + (radius_km * math.cos(ang)) / km_per_deg_lon)
    return lats, lons


def circle_disk_polygon(
    lat: float, lon: float, radius_km: float, points: int = 72,
) -> tuple[list[float], list[float]]:
    """Anillo invertido para que Plotly geo rellene el disco interior."""
    lat_r, lon_r = circle_perimeter(lat, lon, radius_km, points)
    return lat_r[::-1], lon_r[::-1]
