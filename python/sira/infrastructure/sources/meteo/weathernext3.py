"""WeatherNext 3 (Google DeepMind) vía BigQuery — acceso restringido (allowlist).

*** MÓDULO DORMIDO hasta que Google conceda el acceso ***

WeatherNext 3 (agosto 2026) es un modelo global de previsión meteorológica de
Google DeepMind/Google Research: 0.05° (~5 km) en estaciones, 0.1° (~10 km) en
superficie, 0.25° (~25 km) en niveles de presión; inicializaciones cada hora;
64 miembros de ensemble. Documentación oficial:
https://developers.google.com/weathernext/guides/models

Hoy (23-sep-2026) solo se puede consultar con una cuenta de Google Cloud
admitida en la allowlist oficial — formulario de acceso, 5-7 días laborables:
https://developers.google.com/weathernext/guides/access-forecast
Hemos solicitado el acceso; este módulo queda preparado para activarse solo
en cuanto llegue, sin más cambios de código (ver `weathernext.py`, que hace
el fallback automático a WeatherNext 2 / Open-Meteo mientras tanto).

Variables disponibles vía BigQuery (tabla `weathernext_3_0_0_0p1deg`,
estadísticas del ensemble ya precalculadas: `_mean`, `_p10`, `_p25`, `_p50`,
`_p75`, `_p90` por variable): temperatura y punto de rocío a 2 m, viento a
10 m/100 m (u/v y velocidad escalar), precipitación horaria (tres fuentes:
modelo, IMERG satélite, radar-satélite experimental — en metros), nubosidad
(total/alta/media/baja, fracción 0-1), radiación solar horaria (J/m²),
presión a nivel del mar (Pa) y temperatura superficial del mar (K).

*** IMPORTANTE: es un modelo puramente atmosférico/oceánico. NO incluye
coordenadas ni datos de sismos, incendios, embalses ni aforos — esos
paneles/cards no se deben intentar rellenar con WeatherNext y la página
`/weathernext` del dashboard no los incluye a propósito. ***

Puesta en marcha en cuanto llegue el acceso (checklist):
1. `pip install google-cloud-bigquery` (ya listado en requirements.txt).
2. En BigQuery → Analytics Hub, suscribirse al listing "WeatherNext 3":
   queda enlazado como `<tu_proyecto>.<tu_dataset>.weathernext_3_0_0_0p1deg`.
3. Crear una service account con roles "BigQuery Data Viewer" + "BigQuery Job
   User" sobre ese proyecto y descargar la clave JSON.
4. Variables de entorno (en Render: grupo sira-secrets):
     GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/clave.json
     WEATHERNEXT3_PROJECT_ID=<tu_proyecto>
     WEATHERNEXT3_DATASET_ID=<tu_dataset>
5. Nada más: `weathernext_localidad()` detecta la configuración y usa
   BigQuery automáticamente, con fallback silencioso a WeatherNext 2 si algo
   falla (p. ej. la cuenta aún no está admitida, o hay un error de red/cuota).

Pendiente de validar contra datos reales en cuanto haya acceso (construido
siguiendo la documentación oficial, sin poder probar todavía contra BigQuery
real): nombres exactos de columnas, unidades, y que `ST_DWITHIN`/`ST_GEOGPOINT`
encajen con el `geography`/`geography_polygon` de la tabla tal cual queda en
vuestro proyecto.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sira.config.settings import (
    WEATHERNEXT3_DATASET_ID,
    WEATHERNEXT3_HORAS_MAX,
    WEATHERNEXT3_PROJECT_ID,
    WEATHERNEXT3_TABLE_0P1DEG,
)

log = logging.getLogger(__name__)

FUENTE_WEATHERNEXT3 = "Google WeatherNext 3 (BigQuery)"

# Radio de búsqueda del punto más cercano en la rejilla 0.1° (~10 km/celda).
_RADIO_CELDA_M = 15_000

_cliente = None
_cliente_error = False


def weathernext3_configurado() -> bool:
    """True si hay proyecto/dataset configurados.

    No garantiza que el acceso ya esté concedido: eso solo se sabe al
    lanzar la primera consulta (permission denied si la allowlist aún no
    incluye la cuenta).
    """
    return bool(WEATHERNEXT3_PROJECT_ID and WEATHERNEXT3_DATASET_ID)


def _get_cliente():
    """Cliente BigQuery perezoso y cacheado (import pesado; opcional)."""
    global _cliente, _cliente_error
    if _cliente is not None:
        return _cliente
    if _cliente_error:
        return None
    try:
        from google.cloud import bigquery
    except ImportError:
        log.warning("google-cloud-bigquery no instalado; WeatherNext 3 no disponible (fallback a WN2)")
        _cliente_error = True
        return None
    try:
        _cliente = bigquery.Client(project=WEATHERNEXT3_PROJECT_ID)
    except Exception:  # noqa: BLE001
        log.exception("No se pudo crear el cliente BigQuery para WeatherNext 3")
        _cliente_error = True
        return None
    return _cliente


def _tabla() -> str:
    return f"`{WEATHERNEXT3_PROJECT_ID}.{WEATHERNEXT3_DATASET_ID}.{WEATHERNEXT3_TABLE_0P1DEG}`"


def _ultimo_init_time(client) -> datetime | None:
    """Último `init_time` disponible en las últimas 48h (filtra por partición;
    ver "Best practices" de la guía de BigQuery: siempre filtrar por init_time).
    """
    sql = f"""
        SELECT MAX(init_time) AS ultimo
        FROM {_tabla()}
        WHERE init_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
    """
    rows = list(client.query(sql).result())
    if not rows or rows[0]["ultimo"] is None:
        return None
    return rows[0]["ultimo"]


def weathernext3_localidad(lat: float, lon: float, *, nombre: str | None = None) -> dict | None:
    """Serie horaria WeatherNext 3 (media del ensemble) para un punto.

    Devuelve None si el módulo no está configurado, falta la librería, o
    BigQuery falla por cualquier motivo (incl. "cuenta aún no admitida en
    la allowlist") — el llamante (`weathernext.py`) debe hacer fallback a
    WeatherNext 2 en ese caso, nunca debe propagar la excepción.
    """
    if not weathernext3_configurado():
        return None
    client = _get_cliente()
    if client is None:
        return None
    try:
        from google.cloud import bigquery

        init_time = _ultimo_init_time(client)
        if init_time is None:
            log.warning("WeatherNext 3: sin init_time reciente en BigQuery")
            return None

        sql = f"""
            SELECT
                f.time AS forecast_time,
                f.temperature_2m_mean AS temp_k,
                f.wind_speed_10m_mean AS viento_ms,
                f.total_precipitation_1hr_mean AS precip_m,
                f.total_cloud_cover_mean AS nubosidad_frac,
                f.mean_sea_level_pressure_mean AS presion_pa,
                f.sea_surface_temperature_mean AS sst_k
            FROM {_tabla()} AS t, t.forecast AS f
            WHERE t.init_time = @init_time
              AND ST_DWITHIN(t.geography, ST_GEOGPOINT(@lon, @lat), @radio)
              AND f.hours <= @horas_max
            ORDER BY f.time ASC
            LIMIT 2000
        """
        job = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("init_time", "TIMESTAMP", init_time),
                    bigquery.ScalarQueryParameter("lat", "FLOAT64", float(lat)),
                    bigquery.ScalarQueryParameter("lon", "FLOAT64", float(lon)),
                    bigquery.ScalarQueryParameter("radio", "FLOAT64", _RADIO_CELDA_M),
                    bigquery.ScalarQueryParameter("horas_max", "INT64", WEATHERNEXT3_HORAS_MAX),
                ]
            ),
        )

        serie: list[dict] = []
        vistos: set[str] = set()
        for row in job.result():
            ts = row["forecast_time"].isoformat()
            if ts in vistos:
                # El radio de búsqueda puede tocar más de una celda de 0.1°;
                # nos quedamos con la primera (la más próxima al init_time ASC).
                continue
            vistos.add(ts)
            temp_k = row["temp_k"]
            presion_pa = row["presion_pa"]
            nub = row["nubosidad_frac"]
            precip_m = row["precip_m"]
            viento = row["viento_ms"]
            sst_k = row["sst_k"]
            serie.append({
                "timestamp": ts,
                "temp_c": round(float(temp_k) - 273.15, 1) if temp_k is not None else None,
                "viento_ms": round(float(viento), 2) if viento is not None else None,
                "precip_mm": round(float(precip_m) * 1000, 2) if precip_m is not None else 0.0,
                "nubosidad_pct": round(float(nub) * 100, 1) if nub is not None else None,
                "presion_hpa": round(float(presion_pa) / 100, 1) if presion_pa is not None else None,
                "sst_c": round(float(sst_k) - 273.15, 2) if sst_k is not None else None,
            })

        if not serie:
            return None
        return {
            "fuente": FUENTE_WEATHERNEXT3,
            "municipio": nombre or "",
            "serie_horaria": serie,
            "resumen": {},
        }
    except Exception:  # noqa: BLE001
        log.warning(
            "WeatherNext 3 BigQuery falló (¿allowlist todavía pendiente?); uso fallback WN2",
            exc_info=True,
        )
        return None
