"""Previsión WeatherNext (Google DeepMind) vía Open-Meteo.

WeatherNext 3 (agosto 2026) solo se puede consumir hoy con acceso restringido
en Google Cloud (BigQuery/Earth Engine/GCS, allowlist de 5-7 días laborables).
WeatherNext 2 sí es de acceso libre e inmediato a través del endpoint
"ensemble" de Open-Meteo, usando el modelo `google_weathernext2_ensemble_mean`
(media del ensemble; sin necesidad de promediar 64 miembros a mano).

Este módulo se mantiene deliberadamente fuera de `services/ingesta/orchestrator.py`:
la ingesta principal corre en el plan gratuito de Render con memoria muy
ajustada, así que las llamadas a WeatherNext se hacen bajo demanda (cuando
alguien visita la página del dashboard) con una cache corta en memoria en
lugar de sumarse al ciclo de ingesta cada 3 h.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from sira.config.settings import (
    OPEN_METEO_ENSEMBLE_URL,
    WEATHERNEXT_FORECAST_DAYS,
    WEATHERNEXT_MODEL,
)
from sira.infrastructure.geo.es import coords_municipio, municipio_por_id
from sira.infrastructure.http.client import fetch_json
from sira.infrastructure.sources.meteo.parse import VACIO_METEO, hourly as _hourly
from sira.infrastructure.sources.meteo.termico import construir_termico_ccaa

log = logging.getLogger(__name__)

FUENTE_WEATHERNEXT = "Google WeatherNext 2 (Open-Meteo)"

_CACHE_TTL_CCAA_SEC = 900.0  # 15 min
_CACHE_TTL_PUNTO_SEC = 600.0  # 10 min
_cache_ccaa: dict[str, object] = {"ts": 0.0, "data": None}
_cache_punto: dict[str, tuple[float, dict]] = {}


def weathernext_localidad(municipio_id: str | None, localidad: str | None = None) -> dict:
    """Serie horaria WeatherNext 2 (media del ensemble) para un municipio."""
    if not municipio_id:
        return VACIO_METEO
    muni = municipio_por_id(municipio_id)
    nombre = localidad or (muni["nombre"] if muni else str(municipio_id))
    try:
        lat, lon = coords_municipio(municipio_id)
        data = fetch_json(OPEN_METEO_ENSEMBLE_URL, {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m",
            "models": WEATHERNEXT_MODEL,
            "wind_speed_unit": "ms",
            "timezone": "Europe/Madrid",
            "forecast_days": WEATHERNEXT_FORECAST_DAYS,
        })
        serie = _hourly(data, {
            "temp_c": "temperature_2m",
            "precip_mm": "precipitation",
            "viento_ms": "wind_speed_10m",
            "viento_dir_grados": "wind_direction_10m",
        })
        for row in serie:
            if row.get("temp_c") is not None:
                row["temp_c"] = round(float(row["temp_c"]), 1)
            row["precip_mm"] = row.get("precip_mm") or 0.0
        return {
            "fuente": FUENTE_WEATHERNEXT,
            "municipio": nombre,
            "serie_horaria": serie,
            "resumen": {},
        }
    except (requests.RequestException, ValueError, OSError) as exc:
        log.warning("WeatherNext %s: %s", municipio_id, exc)
        return VACIO_METEO


def construir_weathernext_ccaa(*, now: datetime | None = None, max_workers: int = 6) -> dict:
    """Resumen térmico WeatherNext 2 por provincia/CCAA (para el mapa)."""
    return construir_termico_ccaa(weathernext_localidad, now=now, max_workers=max_workers)


def construir_weathernext_ccaa_cache(*, max_workers: int = 6) -> dict:
    """Igual que `construir_weathernext_ccaa` pero con cache corta en memoria.

    52 llamadas al API "ensemble" de Open-Meteo no son gratis en tiempo de
    respuesta; se cachean unos minutos para que abrir/refrescar la página de
    WeatherNext no dispare siempre esa ronda completa.
    """
    now = time.monotonic()
    if _cache_ccaa["data"] is not None and (now - float(_cache_ccaa["ts"])) < _CACHE_TTL_CCAA_SEC:
        return _cache_ccaa["data"]  # type: ignore[return-value]
    data = construir_weathernext_ccaa(max_workers=max_workers)
    _cache_ccaa["data"] = data
    _cache_ccaa["ts"] = now
    return data


def weathernext_localidad_cache(municipio_id: str | None, localidad: str | None = None) -> dict:
    """Igual que `weathernext_localidad` pero con cache corta en memoria."""
    key = str(municipio_id or "")
    now = time.monotonic()
    cached = _cache_punto.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_PUNTO_SEC:
        return cached[1]
    data = weathernext_localidad(municipio_id, localidad)
    _cache_punto[key] = (now, data)
    return data
