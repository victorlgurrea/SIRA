"""Distancias, score y percepción de sismos desde un punto de observación."""
from __future__ import annotations

import math

from config import SISMO_PERCEPCION, TSUNAMI


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


def circle_perimeter(lat: float, lon: float, radius_km: float, points: int = 72) -> tuple[list[float], list[float]]:
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


def circle_disk_polygon(lat: float, lon: float, radius_km: float, points: int = 72) -> tuple[list[float], list[float]]:
    """Anillo invertido para que Plotly geo rellene el disco interior (no el exterior)."""
    lat_r, lon_r = circle_perimeter(lat, lon, radius_km, points)
    return lat_r[::-1], lon_r[::-1]


def es_perceptible(magnitud: float, profundidad_km: float, distancia_km: float) -> bool:
    return distancia_km <= distancia_perceptible_km(magnitud, profundidad_km)


def alerta_tsunami(usgs_tsunami: int | bool | None) -> bool:
    """True si USGS asocia aviso o generación de tsunami (campo properties.tsunami)."""
    try:
        return int(usgs_tsunami or 0) == 1
    except (TypeError, ValueError):
        return bool(usgs_tsunami)


def radio_tsunami_km(magnitud: float, profundidad_km: float, es_submarino: bool) -> float:
    """Radio estimado (km) de zona de aviso/propagación desde el epicentro."""
    p = TSUNAMI
    mag = max(float(magnitud), p["mag_ref"])
    r = p["factor"] * (10 ** (p["exp_mag"] * (mag - p["mag_ref"])))
    if not es_submarino:
        r *= p["factor_terrestre"]
    if profundidad_km > p["prof_km"]:
        r *= max(0.3, 1.0 - min(profundidad_km, 400) / 500)
    if p["max_km"] > 0:
        r = min(r, p["max_km"])
    return round(max(r, p["min_km"]), 1)


def score_sismo(mag: float, prof: float, dist: float, sub: bool) -> dict:
    mag_p = next((p for m, p in [(7, 40), (6.5, 32), (6, 22), (5.5, 14), (5, 8), (4.5, 4)] if mag >= m), 1)
    prof_p = next((p for d, p in [(10, 30), (30, 25), (70, 18), (150, 8)] if prof <= d), 2)
    dist_p = next((p for d, p in [(200, 20), (400, 15), (700, 10), (1000, 5)] if dist <= d), 1)
    total = mag_p + prof_p + dist_p + (10 if sub else 0)
    nivel = next((n for u, n in [(75, "CRÍTICO"), (55, "ALTO"), (35, "MODERADO"), (15, "BAJO")] if total >= u), "MÍNIMO")
    return {"score_total": total, "nivel_alerta": nivel}


def enriquecer_local(sismo: dict, lat: float, lon: float) -> dict:
    """Añade distancia, score y nivel desde el punto de observación."""
    d = distancia_km(lat, lon, float(sismo["lat"]), float(sismo["lon"]))
    mag = float(sismo["magnitud"])
    prof = float(sismo.get("profundidad") or 0)
    sub = bool(sismo.get("es_submarino"))
    local = score_sismo(mag, prof, d, sub)
    radio = distancia_perceptible_km(mag, prof)
    if "alerta_tsunami" in sismo:
        ts_flag = bool(sismo.get("alerta_tsunami"))
    else:
        ts_flag = alerta_tsunami(sismo.get("usgs_tsunami"))
    stored_ts = sismo.get("radio_tsunami_km")
    if ts_flag and stored_ts is not None:
        radio_ts = float(stored_ts)
    elif ts_flag:
        radio_ts = radio_tsunami_km(mag, prof, sub)
    else:
        radio_ts = 0.0
    return {
        **sismo,
        "dist_local_km": d,
        "radio_perceptible_km": radio,
        "alerta_tsunami": ts_flag,
        "radio_tsunami_km": radio_ts,
        "score_local": local["score_total"],
        "nivel_local": local["nivel_alerta"],
        "perceptible_local": d <= radio,
    }


def alerta_local(sismo: dict, lat: float, lon: float) -> dict | None:
    """Perceptible desde el punto de observación; None si no aplica."""
    info = enriquecer_local(sismo, lat, lon)
    if not info["perceptible_local"]:
        return None
    return info


def filtrar_perceptibles(sismos: list, lat: float, lon: float) -> list[dict]:
    out: list[dict] = []
    for s in sismos:
        info = enriquecer_local(s, lat, lon)
        if info["perceptible_local"]:
            out.append(info)
    return out
