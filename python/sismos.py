"""Distancias y percepción de sismos desde un punto de observación."""
from __future__ import annotations

import math


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return round(111.2 * math.hypot(lat1 - lat2, (lon1 - lon2) * math.cos(math.radians(lat1))), 1)


def distancia_perceptible_km(magnitud: float, profundidad_km: float) -> float:
    """Radio estimado donde el sismo es perceptible (MMI ≥ II).

    Referencia empírica USGS / QuakeFYI: M4 ~100 km, M5 ~200 km, M6 ~400 km
    (eventos superficiales). Los sismos profundos se perciben algo más lejos.
    """
    if magnitud < 2.5:
        return 0.0
    r = 10 ** (0.55 * magnitud + 0.15)
    if profundidad_km > 70:
        r *= 1.0 + min(profundidad_km, 350) / 400
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
