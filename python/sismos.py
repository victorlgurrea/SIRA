"""Distancias y percepción de sismos desde un punto de observación."""
from __future__ import annotations

import math

from config import SISMO_PERCEPCION


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return round(111.2 * math.hypot(lat1 - lat2, (lon1 - lon2) * math.cos(math.radians(lat1))), 1)


def distancia_perceptible_km(magnitud: float, profundidad_km: float) -> float:
    """Radio estimado (km) donde el sismo es perceptible (MMI ≥ II).

    Parámetros en .env (SISMO_PERCEPTIBLE_*). Referencia USGS / QuakeFYI con
    valores por defecto: M4 ~225 km, M5 ~400 km, M6 ~700 km (superficiales).
    """
    p = SISMO_PERCEPCION
    if magnitud < p["mag_min"]:
        return 0.0
    r = p["factor"] * (10 ** (p["exp_mag"] * magnitud + p["exp_base"]))
    if profundidad_km > p["prof_km"]:
        r *= 1.0 + min(profundidad_km, 350) / 400
    if p["max_km"] > 0:
        r = min(r, p["max_km"])
    return round(r, 1)


def es_perceptible(magnitud: float, profundidad_km: float, distancia_km: float) -> bool:
    return distancia_km <= distancia_perceptible_km(magnitud, profundidad_km)


def filtrar_perceptibles(sismos: list, lat: float, lon: float) -> list[dict]:
    out: list[dict] = []
    for s in sismos:
        d = distancia_km(lat, lon, float(s["lat"]), float(s["lon"]))
        if es_perceptible(float(s["magnitud"]), float(s.get("profundidad") or 0), d):
            out.append({**s, "dist_local_km": d})
    return out
