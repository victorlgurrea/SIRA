"""Meteorología en tiempo real para un municipio/localidad."""
from __future__ import annotations

import logging

import requests

from config import AEMET_API_KEY, FORECAST_DAYS, OPEN_METEO_WEATHER_URL, ZONA
from core import fetch_aemet, fetch_json
from geo_es import coords_municipio, municipio_por_id
from ingesta import VACIO_METEO, _hourly, _pack_meteo, _parse_aemet

log = logging.getLogger(__name__)


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
                return _pack_meteo("AEMET", item.get("nombre", nombre), serie)
        except (requests.RequestException, ValueError, OSError) as exc:
            log.warning("AEMET %s: %s", codigo, exc)

    try:
        lat, lon = coords_municipio(municipio_id)
        data = fetch_json(OPEN_METEO_WEATHER_URL, {
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation,precipitation_probability",
            "timezone": "Europe/Madrid",
            "forecast_days": FORECAST_DAYS,
        })
        serie = _hourly(data, {"precip_mm": "precipitation", "prob_precip_pct": "precipitation_probability"})
        for row in serie:
            row["precip_mm"] = row["precip_mm"] or 0.0
        return _pack_meteo("Open-Meteo", nombre, serie)
    except (requests.RequestException, ValueError, OSError) as exc:
        log.warning("Open-Meteo %s: %s", codigo, exc)
        return VACIO_METEO
