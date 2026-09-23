"""Previsión WeatherNext (Google DeepMind): WeatherNext 3 si hay acceso, si no
WeatherNext 2 vía Open-Meteo.

WeatherNext 3 (agosto 2026) es el modelo real solicitado, pero solo se puede
consultar con una cuenta de Google Cloud admitida en la allowlist oficial
(formulario, 5-7 días laborables) — ver `weathernext3.py` para el detalle y
el checklist de puesta en marcha. Mientras la allowlist no responda (o
mientras no se configuren las variables de entorno / falte la librería),
este módulo cae automáticamente a **WeatherNext 2**, que sí es de acceso
libre e inmediato a través del endpoint "ensemble" de Open-Meteo con el
modelo `google_weathernext2_ensemble_mean` (media del ensemble).

En cuanto llegue el acceso a WeatherNext 3, `weathernext_localidad()` empieza
a usarlo automáticamente sin más cambios de código (ver `weathernext3.py`).

Este módulo se mantiene deliberadamente fuera de `services/ingesta/orchestrator.py`:
la ingesta principal corre en el plan gratuito de Render con memoria muy
ajustada, así que las llamadas a WeatherNext se hacen bajo demanda (cuando
alguien visita la página del dashboard) con una cache corta en memoria en
lugar de sumarse al ciclo de ingesta cada 3 h.

Nota: es un modelo puramente atmosférico/oceánico (temperatura, precipitación,
viento, nubosidad, presión...). NO da coordenadas de sismos, incendios,
embalses ni aforos — la página `/weathernext` del dashboard no incluye esos
paneles a propósito.
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
from sira.infrastructure.sources.meteo.weathernext3 import (
    weathernext3_configurado,
    weathernext3_localidad,
)

log = logging.getLogger(__name__)

FUENTE_WEATHERNEXT = "Google WeatherNext 2 (Open-Meteo)"

_CACHE_TTL_CCAA_SEC = 900.0  # 15 min
_CACHE_TTL_PUNTO_SEC = 600.0  # 10 min
_cache_ccaa: dict[str, object] = {"ts": 0.0, "data": None}
_cache_punto: dict[str, tuple[float, dict]] = {}


def _weathernext2_localidad(lat: float, lon: float, nombre: str) -> dict:
    """Fallback: serie horaria WeatherNext 2 (media del ensemble) vía Open-Meteo."""
    try:
        data = fetch_json(OPEN_METEO_ENSEMBLE_URL, {
            "latitude": lat,
            "longitude": lon,
            "hourly": (
                "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,"
                "cloud_cover,pressure_msl"
            ),
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
            "nubosidad_pct": "cloud_cover",
            "presion_hpa": "pressure_msl",
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
        log.warning("WeatherNext 2 (Open-Meteo) %s: %s", nombre, exc)
        return VACIO_METEO


def weathernext_localidad(municipio_id: str | None, localidad: str | None = None) -> dict:
    """Serie horaria WeatherNext para un municipio.

    Usa WeatherNext 3 (BigQuery) si está configurado y responde; si no,
    cae a WeatherNext 2 (Open-Meteo), que funciona hoy sin allowlist.
    """
    if not municipio_id:
        return VACIO_METEO
    muni = municipio_por_id(municipio_id)
    nombre = localidad or (muni["nombre"] if muni else str(municipio_id))
    lat, lon = coords_municipio(municipio_id)

    if weathernext3_configurado():
        try:
            r3 = weathernext3_localidad(lat, lon, nombre=nombre)
        except Exception:  # noqa: BLE001
            log.exception("weathernext3_localidad %s: fallo inesperado", municipio_id)
            r3 = None
        if r3:
            return r3

    return _weathernext2_localidad(lat, lon, nombre)


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
