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

En cuanto llegue el acceso a WeatherNext 3, `weathernext_punto()` empieza a
usarlo automáticamente sin más cambios de código (ver `weathernext3.py`).

Este módulo se mantiene deliberadamente fuera de `services/ingesta/orchestrator.py`:
la ingesta principal corre en el plan gratuito de Render con memoria muy
ajustada, así que las llamadas a WeatherNext se hacen bajo demanda (cuando
alguien visita la página del dashboard) con una cache corta en memoria en
lugar de sumarse al ciclo de ingesta cada 3 h.

Nota: es un modelo puramente atmosférico/oceánico (temperatura, precipitación,
viento, nubosidad, presión, temperatura del mar...). NO da coordenadas de
sismos, incendios, embalses ni aforos — la página `/weathernext` del
dashboard no incluye esos paneles a propósito.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from sira.config.settings import (
    MARES,
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
_CACHE_TTL_SST_SEC = 900.0  # 15 min
_cache_ccaa: dict[str, object] = {"ts": 0.0, "data": None}
_cache_punto: dict[str, tuple[float, dict]] = {}
_cache_sst: dict[str, object] = {"ts": 0.0, "data": None}

# El punto de referencia del Cantábrico en `MARES` (Santander, cerca de la
# costa) cae en una celda de tierra/costa de la rejilla del ensemble de
# Open-Meteo para `sea_surface_temperature` (devuelve null aunque el resto de
# variables sí respondan). Para el panel de SST de WeatherNext usamos un punto
# un poco más adentro del Cantábrico, verificado que sí da SST; el resto de
# usos de `MARES` (CMEMS, etiquetas...) no se tocan.
_SST_COORDS_ALT: dict[str, tuple[float, float]] = {
    "CANTÁBRICO": (43.75, -4.0),
}


def _weathernext2_punto(lat: float, lon: float, nombre: str) -> dict:
    """Fallback: serie horaria WeatherNext 2 (media del ensemble) vía Open-Meteo."""
    try:
        data = fetch_json(OPEN_METEO_ENSEMBLE_URL, {
            "latitude": lat,
            "longitude": lon,
            "hourly": (
                "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,"
                "cloud_cover,pressure_msl,sea_surface_temperature"
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
            "sst_c": "sea_surface_temperature",
        })
        for row in serie:
            if row.get("temp_c") is not None:
                row["temp_c"] = round(float(row["temp_c"]), 1)
            if row.get("sst_c") is not None:
                row["sst_c"] = round(float(row["sst_c"]), 2)
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


def weathernext_punto(lat: float, lon: float, nombre: str = "") -> dict:
    """Serie horaria WeatherNext para un punto (lat, lon) cualquiera (tierra o mar).

    Usa WeatherNext 3 (BigQuery) si está configurado y responde; si no, cae a
    WeatherNext 2 (Open-Meteo), que funciona hoy sin allowlist.
    """
    if weathernext3_configurado():
        try:
            r3 = weathernext3_localidad(lat, lon, nombre=nombre)
        except Exception:  # noqa: BLE001
            log.exception("weathernext3_localidad (%s, %s): fallo inesperado", lat, lon)
            r3 = None
        if r3:
            return r3

    return _weathernext2_punto(lat, lon, nombre)


def weathernext_localidad(municipio_id: str | None, localidad: str | None = None) -> dict:
    """Serie horaria WeatherNext para un municipio (INE)."""
    if not municipio_id:
        return VACIO_METEO
    muni = municipio_por_id(municipio_id)
    nombre = localidad or (muni["nombre"] if muni else str(municipio_id))
    lat, lon = coords_municipio(municipio_id)
    return weathernext_punto(lat, lon, nombre)


def construir_weathernext_ccaa(*, now: datetime | None = None, max_workers: int = 6) -> dict:
    """Resumen térmico WeatherNext por provincia/CCAA (para el mapa)."""
    return construir_termico_ccaa(weathernext_localidad, now=now, max_workers=max_workers)


def construir_weathernext_ccaa_cache(*, max_workers: int = 6) -> dict:
    """Igual que `construir_weathernext_ccaa` pero con cache corta en memoria.

    52 llamadas al API no son gratis en tiempo de respuesta (ni, en el caso de
    WeatherNext 3/BigQuery, en coste); se cachean unos minutos para que abrir
    o refrescar la página de WeatherNext no dispare siempre esa ronda completa.
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


def weathernext_sst_cache() -> dict:
    """Temperatura superficial del mar (WeatherNext) en los 3 puntos de
    referencia usados por el resto del dashboard (Mediterráneo, Cantábrico,
    Atlántico — ver `MARES` en settings), con cache corta en memoria.

    Misma forma que `oceanografia` (dict con `serie_horaria`), para poder
    reutilizar `_fig_linea(..., "sst_c", ..., con_semaforo_sst=True)` tal
    cual se hace en el dashboard principal.
    """
    now = time.monotonic()
    if _cache_sst["data"] is not None and (now - float(_cache_sst["ts"])) < _CACHE_TTL_SST_SEC:
        return _cache_sst["data"]  # type: ignore[return-value]
    data = {}
    for clave, mar in MARES.items():
        lat, lon = _SST_COORDS_ALT.get(clave, (mar["lat"], mar["lon"]))
        try:
            data[clave] = weathernext_punto(lat, lon, mar.get("punto", clave))
        except Exception:  # noqa: BLE001
            log.exception("weathernext_sst_cache %s falló", clave)
            data[clave] = VACIO_METEO
    _cache_sst["data"] = data
    _cache_sst["ts"] = now
    return data


def weathernext_resumen_actual(punto: dict | None) -> tuple[dict, list[dict]]:
    """Construye (resumen, proximas_horas) para `ui.components.meteo_ahora()`
    a partir de la serie horaria de WeatherNext.

    WeatherNext no tiene un endpoint de "tiempo actual" como AEMET/Open-Meteo
    forecast: se usa la primera hora de la serie (la más próxima a ahora) y se
    deriva un icono/texto simple a partir de nubosidad y precipitación (no hay
    humedad relativa ni weather_code fiables en el modelo del ensemble).
    """
    serie = (punto or {}).get("serie_horaria") or []
    if not serie:
        return {}, []
    actual = serie[0]
    nub = actual.get("nubosidad_pct")
    precip = actual.get("precip_mm") or 0.0
    if precip and float(precip) >= 0.2:
        icon, texto = "🌧️", "Lluvia"
    elif nub is not None and float(nub) >= 80:
        icon, texto = "☁️", "Muy nuboso"
    elif nub is not None and float(nub) >= 40:
        icon, texto = "⛅", "Nuboso"
    elif nub is not None and float(nub) >= 10:
        icon, texto = "🌤️", "Poco nuboso"
    else:
        icon, texto = "☀️", "Despejado"
    resumen = {
        "tiempo_icon": icon,
        "tiempo_texto": texto,
        "temp_c": actual.get("temp_c"),
        "sensacion_c": None,
        "humedad_pct": None,
        "viento_vel": actual.get("viento_ms"),
        "viento_unidad": "m/s",
        "viento_dir_grados": actual.get("viento_dir_grados"),
    }
    return resumen, serie[:6]
