"""Calidad del agua costera para la localidad seleccionada (consulta ligera)."""
from __future__ import annotations

import logging
import math
import time
from typing import Any

from sira.config.settings import OPEN_METEO_MARINE_URL
from sira.infrastructure.geo.mar_costa_atlantica import punto_en_mar_costa_atlantica
from sira.infrastructure.geo.mar_mediterraneo import punto_en_mar_mediterraneo
from sira.infrastructure.http.client import fetch_json

log = logging.getLogger(__name__)

# ~55–60 km: cubre Murcia capital → costa; Madrid (~300 km) no entra.
_COSTA_MAX_DEG = 0.55
_SST_RADIO_KM = 55.0
_CACHE_TTL_SEC = 45 * 60.0
_NOAA_CHL_URL = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chla1day.json"

_cache: dict[str, tuple[float, dict]] = {}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _es_mar(lat: float, lon: float) -> bool:
    return punto_en_mar_mediterraneo(lat, lon) or punto_en_mar_costa_atlantica(lat, lon)


def punto_marino_cercano(lat: float, lon: float) -> tuple[float, float] | None:
    """Devuelve un punto de mar cercano o None si la localidad no es costera."""
    la0, lo0 = float(lat), float(lon)
    if _es_mar(la0, lo0):
        return round(la0, 4), round(lo0, 4)

    dirs = (
        (0.0, -1.0), (0.0, 1.0), (-1.0, 0.0), (1.0, 0.0),
        (-0.7, -0.7), (-0.7, 0.7), (0.7, -0.7), (0.7, 0.7),
    )
    step = 0.04
    dist = step
    while dist <= _COSTA_MAX_DEG + 1e-9:
        for dlat, dlon in dirs:
            la = la0 + dlat * dist
            lo = lo0 + dlon * dist
            if _es_mar(la, lo):
                return round(la, 4), round(lo, 4)
        dist += step
    return None


def es_zona_costera(lat: float, lon: float) -> bool:
    return punto_marino_cercano(lat, lon) is not None


def _sst_desde_grids(dashboard: dict, lat: float, lon: float) -> tuple[float | None, int]:
    vals: list[float] = []
    for key in ("sst_med_grid", "sst_cant_grid", "sst_atl_grid"):
        grid = dashboard.get(key)
        if not isinstance(grid, dict):
            continue
        for c in grid.get("celdas") or []:
            if c.get("sst_c") is None:
                continue
            try:
                cla, clo, sst = float(c["lat"]), float(c["lon"]), float(c["sst_c"])
            except (TypeError, ValueError, KeyError):
                continue
            if _haversine_km(lat, lon, cla, clo) <= _SST_RADIO_KM:
                vals.append(sst)
    if not vals:
        return None, 0
    return round(sum(vals) / len(vals), 1), len(vals)


def _sst_open_meteo(lat: float, lon: float) -> float | None:
    try:
        data = fetch_json(OPEN_METEO_MARINE_URL, {
            "latitude": lat,
            "longitude": lon,
            "hourly": "sea_surface_temperature",
            "forecast_days": 1,
            "timezone": "UTC",
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("Open-Meteo marine punto: %s", exc)
        return None
    item = data[0] if isinstance(data, list) and data else data
    if not isinstance(item, dict):
        return None
    temps = (item.get("hourly") or {}).get("sea_surface_temperature") or []
    for t in reversed(temps):
        if t is None:
            continue
        try:
            return round(float(t), 1)
        except (TypeError, ValueError):
            continue
    return None


def _clorofila_noaa(lat: float, lon: float) -> tuple[float | None, str | None]:
    """Clorofila-a (mg/m³) vía ERDDAP NOAA (1 píxel, cacheable)."""
    import requests
    from urllib.parse import urlparse

    from sira.config.settings import ALLOWED_HOSTS

    la = round(lat * 25) / 25
    lo = round(lon * 25) / 25
    url = f"{_NOAA_CHL_URL}?chlorophyll[(last)][({la}):({la})][({lo}):({lo})]"
    host = urlparse(url).hostname
    if host not in ALLOWED_HOSTS:
        return None, None
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("NOAA CHL punto: %s", exc)
        return None, None
    table = data.get("table") if isinstance(data, dict) else None
    if not isinstance(table, dict):
        return None, None
    rows = table.get("rows") or []
    if not rows:
        return None, None
    row = rows[0]
    try:
        fecha = str(row[0])[:10] if row[0] else None
        chl = float(row[3])
        if not math.isfinite(chl) or chl < 0:
            return None, fecha
        return round(chl, 3), fecha
    except (TypeError, ValueError, IndexError):
        return None, None


def _nivel_clorofila(chl: float | None) -> str:
    if chl is None:
        return "—"
    if chl < 0.5:
        return "Baja"
    if chl < 2.0:
        return "Moderada"
    return "Elevada"


def _turbidez_texto(chl: float | None) -> str:
    """Proxy óptico ligero (sin producto turbidez dedicado en la consulta puntual)."""
    if chl is None:
        return "—"
    if chl < 0.8:
        return "Agua clara"
    if chl < 2.5:
        return "Ligeramente turbia"
    return "Turbia"


def _apto_bano(chl: float | None) -> dict[str, str]:
    """Indicativo (no sustituye Náyade / Sanidad)."""
    if chl is None:
        return {
            "estado": "Sin dato",
            "detalle": "Consulta el censo oficial Náyade / Sanidad para el veredicto legal.",
        }
    if chl >= 2.5:
        return {
            "estado": "Precaución",
            "detalle": "Indicativo por clorofila elevada; no es el veredicto oficial de baño.",
        }
    if chl >= 1.2:
        return {
            "estado": "Aceptable*",
            "detalle": "Indicativo satélite; confirma en Náyade / playas de tu municipio.",
        }
    return {
        "estado": "Favorable*",
        "detalle": "Indicativo satélite (agua típicamente clara); confirma en Náyade.",
    }


def _viento_desde_meteo(meteo: dict | None) -> dict[str, Any]:
    res = (meteo or {}).get("resumen") if isinstance(meteo, dict) else {}
    if not isinstance(res, dict):
        res = {}
    vel = res.get("viento_vel")
    unidad = str(res.get("viento_unidad") or "m/s")
    vel_ms = None
    if vel is not None:
        try:
            vel_ms = float(vel)
            if unidad.lower().startswith("km"):
                vel_ms = vel_ms / 3.6
        except (TypeError, ValueError):
            vel_ms = None
    dir_txt = res.get("viento_dir_texto")
    if not dir_txt and res.get("viento_dir_grados") is not None:
        g = float(res["viento_dir_grados"]) % 360
        puntos = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
        dir_txt = f"{g:.0f}° ({puntos[int((g + 22.5) / 45) % 8]})"
    return {"vel_ms": round(vel_ms, 1) if vel_ms is not None else None, "dir": dir_txt}


def calidad_agua_local(
    lat: float,
    lon: float,
    *,
    dashboard: dict | None = None,
    meteo: dict | None = None,
    localidad: str | None = None,
) -> dict | None:
    """Datos ligeros de calidad costera para la UI; None si no hay costa cercana."""
    mar = punto_marino_cercano(lat, lon)
    if mar is None:
        return None

    mlat, mlon = mar
    key = f"{mlat:.2f}:{mlon:.2f}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < _CACHE_TTL_SEC:
        out = dict(hit[1])
        out["localidad"] = localidad or out.get("localidad")
        out["viento"] = _viento_desde_meteo(meteo)
        return out

    dash = dashboard if isinstance(dashboard, dict) else {}
    sst, n_sst = _sst_desde_grids(dash, mlat, mlon)
    fuente_sst = f"CMEMS rejilla local ({n_sst} celdas)" if sst is not None else None
    if sst is None:
        sst = _sst_open_meteo(mlat, mlon)
        if sst is not None:
            fuente_sst = "Open-Meteo marine"

    chl, chl_fecha = _clorofila_noaa(mlat, mlon)
    bano = _apto_bano(chl)
    out = {
        "ok": True,
        "localidad": localidad,
        "punto_mar": {"lat": mlat, "lon": mlon},
        "sst_media_c": sst,
        "sst_fuente": fuente_sst,
        "viento": _viento_desde_meteo(meteo),
        "clorofila_mg_m3": chl,
        "clorofila_nivel": _nivel_clorofila(chl),
        "clorofila_fecha": chl_fecha,
        "turbidez": _turbidez_texto(chl),
        "bano_estado": bano["estado"],
        "bano_detalle": bano["detalle"],
        "aviso": "Clorofila/turbidez/baño son indicativos satélite; el apto oficial es Náyade/Sanidad.",
    }
    _cache[key] = (now, dict(out))
    return out
