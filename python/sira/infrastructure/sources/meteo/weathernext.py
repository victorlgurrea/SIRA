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
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import requests

from sira.config.settings import (
    MARES,
    OPEN_METEO_ENSEMBLE_URL,
    WEATHERNEXT_FORECAST_DAYS,
    WEATHERNEXT_MODEL,
)
from sira.infrastructure.geo.es import coords_municipio, municipio_por_id
from sira.infrastructure.geo.mar_costa_atlantica import (
    fraccion_mar_celda as _fraccion_mar_atl,
    punto_en_mar_costa_atlantica_mapa,
)
from sira.infrastructure.geo.mar_mediterraneo import (
    fraccion_mar_celda as _fraccion_mar_med,
    punto_en_mar_mediterraneo,
)
from sira.infrastructure.http.client import fetch_json
from sira.infrastructure.sources.meteo.parse import VACIO_METEO, hourly as _hourly
from sira.infrastructure.sources.meteo.termico import (
    construir_termico_ccaa,
    ensamblar_termico_ccaa,
    tareas_provincias,
    _completar_sin_temp,
)
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
_cache_sst_grid: dict[str, object] = {"ts": 0.0, "data": None}

# El punto de referencia del Cantábrico en `MARES` (Santander, cerca de la
# costa) cae en una celda de tierra/costa de la rejilla del ensemble de
# Open-Meteo para `sea_surface_temperature` (devuelve null aunque el resto de
# variables sí respondan). Para el panel de SST de WeatherNext usamos un punto
# un poco más adentro del Cantábrico, verificado que sí da SST; el resto de
# usos de `MARES` (CMEMS, etiquetas...) no se tocan.
_SST_COORDS_ALT: dict[str, tuple[float, float]] = {
    "CANTÁBRICO": (43.75, -4.0),
}

# Nº de coordenadas por llamada HTTP al API "ensemble" de Open-Meteo. Pedir
# muchas localizaciones en UNA llamada (en vez de 1 llamada por localización)
# es lo que evita el 429 "Too Many Requests": al mapa nacional (52 provincias)
# o a la rejilla SST le sale mucho más barato en Nº de *peticiones*, aunque el
# volumen de datos pedido sea el mismo.
_OM_BATCH = 45
_OM_BATCH_PAUSA_SEC = 1.1

# Open-Meteo corta la conexión de forma intermitente bajo la carga de varios
# lotes seguidos (`ConnectionResetError`/"Connection aborted"). Sin reintento
# se perdía el lote ENTERO (hasta 45 puntos de golpe) — un hueco grande en el
# mapa/rejilla en vez de una celda suelta, muy visible sobre todo en el
# Mediterráneo (bbox más grande => más lotes => más probabilidad de que
# alguno falle). Con bboxes más grandes (más lotes seguidos) también aparece
# 429 "Too Many Requests" -- ese necesita una espera mucho más larga que un
# simple corte de conexión, o el reintento vuelve a chocar con el límite.
_OM_REINTENTOS = 3
_OM_REINTENTO_PAUSA_SEC = 1.0
_OM_REINTENTO_PAUSA_429_SEC = 8.0


def _fetch_lote_om(params: dict, *, contexto: str) -> dict | list | None:
    """`fetch_json` con reintentos ante fallos de red transitorios."""
    ultimo_exc: Exception | None = None
    for intento in range(_OM_REINTENTOS):
        if intento:
            es_429 = isinstance(ultimo_exc, requests.HTTPError) and getattr(
                ultimo_exc.response, "status_code", None
            ) == 429
            pausa = _OM_REINTENTO_PAUSA_429_SEC * intento if es_429 else _OM_REINTENTO_PAUSA_SEC * intento
            time.sleep(pausa)
        try:
            return fetch_json(OPEN_METEO_ENSEMBLE_URL, params)
        except (requests.RequestException, ValueError, OSError) as exc:
            ultimo_exc = exc
    log.warning(
        "WeatherNext (Open-Meteo) %s: agotados %d intentos (%s)",
        contexto, _OM_REINTENTOS, ultimo_exc,
    )
    return None


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


def _weathernext2_ccaa_lote(tareas: list[tuple[str, str, str, str | None, str, str]]) -> dict[str, dict]:
    """Serie WN2 de las 52 provincias en pocas llamadas HTTP (batch de
    coordenadas), no 52 llamadas sueltas — eso es lo que disparaba 429 "Too
    Many Requests" en Open-Meteo (52 peticiones casi simultáneas) y dejaba el
    mapa sin datos (todas las provincias en gris "sin dato")."""
    puntos: list[tuple[str, float, float]] = []
    for _pid, _prov_nombre, mid, _ccaa_id, _ccaa, _muni_nombre in tareas:
        lat, lon = coords_municipio(mid)
        puntos.append((mid, lat, lon))

    resultados: dict[str, dict] = {}
    for i in range(0, len(puntos), _OM_BATCH):
        if i:
            time.sleep(_OM_BATCH_PAUSA_SEC)
        lote = puntos[i : i + _OM_BATCH]
        data = _fetch_lote_om(
            {
                "latitude": ",".join(str(p[1]) for p in lote),
                "longitude": ",".join(str(p[2]) for p in lote),
                "hourly": "temperature_2m,precipitation,cloud_cover",
                "models": WEATHERNEXT_MODEL,
                "timezone": "Europe/Madrid",
                "forecast_days": WEATHERNEXT_FORECAST_DAYS,
            },
            contexto=f"lote CCAA {i // _OM_BATCH}",
        )
        if data is None:
            continue
        items = data if isinstance(data, list) else [data]
        for (mid, _lat, _lon), item in zip(lote, items):
            if not isinstance(item, dict):
                continue
            serie = _hourly(item, {
                "temp_c": "temperature_2m",
                "precip_mm": "precipitation",
                "nubosidad_pct": "cloud_cover",
            })
            for row in serie:
                if row.get("temp_c") is not None:
                    row["temp_c"] = round(float(row["temp_c"]), 1)
            resultados[mid] = {"fuente": FUENTE_WEATHERNEXT, "serie_horaria": serie, "resumen": {}}
    return resultados


def construir_weathernext_ccaa(*, now: datetime | None = None, max_workers: int = 6) -> dict:
    """Resumen térmico WeatherNext por provincia/CCAA (para el mapa nacional).

    Si WeatherNext 3 (BigQuery) está configurado se consulta punto a punto
    (52 llamadas en paralelo, sin límite de tasa conocido tipo Open-Meteo);
    si no, se usa WeatherNext 2 en lotes de `_OM_BATCH` coordenadas por
    llamada para no disparar el 429 de Open-Meteo.
    """
    if weathernext3_configurado():
        return construir_termico_ccaa(weathernext_localidad, now=now, max_workers=max_workers)
    tareas = tareas_provincias()
    resultados = _weathernext2_ccaa_lote(tareas)
    return _completar_sin_temp(ensamblar_termico_ccaa(tareas, resultados, now=now), now=now)


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


@dataclass(frozen=True)
class _RegionSstWn:
    nombre: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    paso: float
    fraccion_mar: Callable[[float, float, float], float]
    punto_en_mar: Callable[[float, float], bool]


# Cajas de respaldo si no hay malla CMEMS en la ingesta. Preferimos CMEMS en
# el mapa /weathernext (cobertura Med-Physics hasta Turquía y mosaico IBI
# Portugal→Gibraltar). Estas cajas solo rellenan huecos con Open-Meteo.
_REGIONES_SST_WN: dict[str, _RegionSstWn] = {
    "MEDITERRÁNEO": _RegionSstWn(
        "Mediterráneo", 35.8, 43.0, -5.4, 7.6, 0.4, _fraccion_mar_med, punto_en_mar_mediterraneo,
    ),
    "CANTÁBRICO": _RegionSstWn(
        "Cantábrico", 42.2, 44.6, -10.95, -1.2, 0.35, _fraccion_mar_atl, punto_en_mar_costa_atlantica_mapa,
    ),
    "ATLÁNTICO": _RegionSstWn(
        "Atlántico", 35.9, 42.3, -10.95, -5.0, 0.35, _fraccion_mar_atl, punto_en_mar_costa_atlantica_mapa,
    ),
}


def _malla_puntos_mar(region: _RegionSstWn) -> list[tuple[float, float]]:
    """Puntos de la rejilla que caen ya en mar (se descartan de tierra ANTES
    de gastar llamadas HTTP, no después)."""
    half = max(region.paso * 0.48, 0.06)
    pts: list[tuple[float, float]] = []
    lat = region.lat_min
    while lat <= region.lat_max + 1e-9:
        lon = region.lon_min
        while lon <= region.lon_max + 1e-9:
            lat_r, lon_r = round(lat, 4), round(lon, 4)
            if region.fraccion_mar(lat_r, lon_r, half) >= 0.6:
                pts.append((lat_r, lon_r))
            lon += region.paso
        lat += region.paso
    return pts


def _weathernext_sst_grid_region(region: _RegionSstWn) -> dict:
    """Rejilla SST WeatherNext de una costa: `{celdas, fecha, paso_deg, fuente}`
    (misma forma que las mallas CMEMS de `cmems_sst.py`, para reutilizar
    `add_capa_sst_grid`/`add_leyenda_sst_med` del mapa principal)."""
    puntos = _malla_puntos_mar(region)
    celdas: list[dict] = []
    fecha_ref: str | None = None
    for i in range(0, len(puntos), _OM_BATCH):
        if i:
            time.sleep(_OM_BATCH_PAUSA_SEC)
        lote = puntos[i : i + _OM_BATCH]
        data = _fetch_lote_om(
            {
                "latitude": ",".join(str(p[0]) for p in lote),
                "longitude": ",".join(str(p[1]) for p in lote),
                "hourly": "sea_surface_temperature",
                "models": WEATHERNEXT_MODEL,
                "timezone": "UTC",
                "forecast_days": 1,
            },
            contexto=f"rejilla SST {region.nombre} lote {i // _OM_BATCH}",
        )
        if data is None:
            continue
        items = data if isinstance(data, list) else [data]
        for (lat, lon), item in zip(lote, items):
            if not isinstance(item, dict):
                continue
            hourly = item.get("hourly") or {}
            temps = hourly.get("sea_surface_temperature") or []
            times = hourly.get("time") or []
            sst, ts = None, None
            for t, v in zip(times, temps):
                if v is not None:
                    sst, ts = float(v), str(t)
                    break
            if sst is None:
                continue
            if ts and (fecha_ref is None or ts > fecha_ref):
                fecha_ref = ts
            celdas.append({"lat": lat, "lon": lon, "sst_c": round(sst, 2)})

    fecha = (fecha_ref or datetime.now().strftime("%Y-%m-%dT%H:%M"))[:16]
    return {
        "region": region.nombre,
        "fuente": FUENTE_WEATHERNEXT,
        "fecha": fecha,
        "paso_deg": region.paso,
        "celdas": celdas,
    }


def _construir_sst_grid_todas() -> dict[str, dict]:
    data: dict[str, dict] = {}
    for clave, region in _REGIONES_SST_WN.items():
        try:
            data[clave] = _weathernext_sst_grid_region(region)
        except Exception:  # noqa: BLE001
            log.exception("weathernext_sst_grid_cache %s falló", clave)
            data[clave] = {}
    return data


_cache_sst_grid_lock = threading.Lock()
_cache_sst_grid_refrescando = False


def weathernext_sst_grid_cache() -> dict:
    """Rejillas SST WeatherNext (Mediterráneo/Cantábrico/Atlántico) para
    pintarlas como celdas en el mapa, igual que hace el dashboard principal
    con CMEMS. Cache corta en memoria (mismo TTL que `weathernext_sst_cache`).

    "Stale-while-revalidate": con bboxes grandes (sobre todo el Mediterráneo)
    esto puede tardar ~1 min en frío (varias decenas de lotes a Open-Meteo).
    Si ya hay un dato previo (aunque esté caducado) se devuelve al instante y
    se refresca en un hilo de fondo, para que ningún usuario que visite
    /weathernext se quede esperando ese minuto -- solo la primera vez que el
    proceso arranca (sin nada cacheado aún) se espera de forma síncrona.
    """
    global _cache_sst_grid_refrescando
    now = time.monotonic()
    data = _cache_sst_grid["data"]
    caducado = data is None or (now - float(_cache_sst_grid["ts"])) >= _CACHE_TTL_SST_SEC
    if not caducado:
        return data  # type: ignore[return-value]

    if data is None:
        # Primer arranque: no hay nada que servir, hay que esperar sí o sí.
        nuevo = _construir_sst_grid_todas()
        _cache_sst_grid["data"] = nuevo
        _cache_sst_grid["ts"] = now
        return nuevo

    with _cache_sst_grid_lock:
        ya_en_marcha = _cache_sst_grid_refrescando
        _cache_sst_grid_refrescando = True
    if ya_en_marcha:
        return data  # type: ignore[return-value]

    def _refrescar() -> None:
        global _cache_sst_grid_refrescando
        try:
            nuevo = _construir_sst_grid_todas()
            _cache_sst_grid["data"] = nuevo
            _cache_sst_grid["ts"] = time.monotonic()
        except Exception:  # noqa: BLE001
            log.exception("Refresco en background de weathernext_sst_grid_cache falló")
        finally:
            with _cache_sst_grid_lock:
                _cache_sst_grid_refrescando = False

    threading.Thread(target=_refrescar, daemon=True, name="wn-sst-grid-refresh").start()
    return data  # type: ignore[return-value]


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
