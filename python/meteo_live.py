"""Meteorología en tiempo real para un municipio/localidad."""
from __future__ import annotations

import logging

import requests

from config import AEMET_API_KEY, FORECAST_DAYS, OPEN_METEO_WEATHER_URL, ZONA
from core import fetch_aemet, fetch_json
from geo_es import coords_municipio, municipio_por_id
from meteo_parse import (
    VACIO_METEO,
    actual_aemet_from_item,
    hourly as _hourly,
    num as _num,
    parse_aemet as _parse_aemet,
    resumen_lluvia as _resumen_lluvia,
)

log = logging.getLogger(__name__)

_AEMET_DIR_GRADOS = {
    "N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SO": 225, "O": 270, "NO": 315,
}


def _wmo_tiempo(code: int | None) -> tuple[str, str]:
    if code is None:
        return "🌡️", "—"
    c = int(code)
    if c == 0:
        return "☀️", "Despejado"
    if c in (1, 2):
        return "🌤️", "Poco nuboso"
    if c == 3:
        return "☁️", "Nuboso"
    if c in (45, 48):
        return "🌫️", "Niebla"
    if c in (51, 53, 55, 56, 57):
        return "🌦️", "Llovizna"
    if c in (61, 63, 65, 66, 67, 80, 81, 82):
        return "🌧️", "Lluvia"
    if c in (71, 73, 75, 77, 85, 86):
        return "🌨️", "Nieve"
    if c in (95, 96, 99):
        return "⛈️", "Tormenta"
    return "☁️", "Nuboso"


def _aemet_tiempo(codigo: str | None, descripcion: str = "") -> tuple[str, str]:
    desc = (descripcion or "").lower()
    if "tormenta" in desc:
        return "⛈️", descripcion or "Tormenta"
    if "lluvia" in desc or "chubasco" in desc:
        return "🌧️", descripcion or "Lluvia"
    if "nieve" in desc:
        return "🌨️", descripcion or "Nieve"
    if "niebla" in desc or "bruma" in desc:
        return "🌫️", descripcion or "Niebla"
    c = str(codigo or "").strip()
    if c in ("11",):
        return "☀️", descripcion or "Despejado"
    if c in ("12", "17"):
        return "🌤️", descripcion or "Poco nuboso"
    if c in ("13", "23", "43"):
        return "🌥️", descripcion or "Intervalos nubosos"
    if c in ("14", "24", "44"):
        return "☁️", descripcion or "Nuboso"
    if c in ("15", "25", "45"):
        return "☁️", descripcion or "Muy nuboso"
    if c in ("16",):
        return "☁️", descripcion or "Cubierto"
    return "🌡️", descripcion or "—"


def _aemet_dir_grados(letra: str | None) -> float | None:
    if not letra:
        return None
    return _AEMET_DIR_GRADOS.get(str(letra).strip().upper())


def _actual_openmeteo(data: dict) -> dict:
    cur = data.get("current") or {}
    code = cur.get("weather_code")
    icon, texto = _wmo_tiempo(code)
    temp = cur.get("temperature_2m")
    vel = cur.get("wind_speed_10m")
    return {
        "tiempo_icon": icon,
        "tiempo_texto": texto,
        "temp_c": round(float(temp), 1) if temp is not None else None,
        "viento_vel": round(float(vel), 1) if vel is not None else None,
        "viento_unidad": "m/s",
        "viento_dir_grados": cur.get("wind_direction_10m"),
    }


def _actual_aemet(item: dict) -> dict:
    return actual_aemet_from_item(item)


def _pack_local(fuente: str, municipio: str, serie: list[dict], actual: dict) -> dict:
    resumen = {**_resumen_lluvia(serie), **actual}
    return {
        "fuente": fuente,
        "municipio": municipio,
        "serie_horaria": serie[:48],
        "resumen": resumen,
    }


def meteo_localidad(municipio_id: str | None, localidad: str | None = None) -> dict:
    if not municipio_id:
        return VACIO_METEO

    muni = municipio_por_id(municipio_id)
    nombre = localidad or (muni["nombre"] if muni else ZONA["ciudad_ref"])
    codigo = str(municipio_id).zfill(5)

    if AEMET_API_KEY:
        try:
            data = fetch_aemet(f"prediccion/especifica/municipio/horaria/{codigo}", AEMET_API_KEY)
            item = (data[0] if isinstance(data, list) else data) or {}
            serie = _parse_aemet(data)
            if serie:
                return _pack_local("AEMET", item.get("nombre", nombre), serie, _actual_aemet(item))
        except (requests.RequestException, ValueError, OSError) as exc:
            log.warning("AEMET %s: %s", codigo, exc)

    try:
        lat, lon = coords_municipio(municipio_id)
        data = fetch_json(OPEN_METEO_WEATHER_URL, {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,wind_speed_10m,wind_direction_10m",
            "hourly": "precipitation,precipitation_probability",
            "wind_speed_unit": "ms",
            "timezone": "Europe/Madrid",
            "forecast_days": FORECAST_DAYS,
        })
        serie = _hourly(data, {"precip_mm": "precipitation", "prob_precip_pct": "precipitation_probability"})
        for row in serie:
            row["precip_mm"] = row["precip_mm"] or 0.0
        return _pack_local("Open-Meteo", nombre, serie, _actual_openmeteo(data))
    except (requests.RequestException, ValueError, OSError) as exc:
        log.warning("Open-Meteo %s: %s", codigo, exc)
        return VACIO_METEO
