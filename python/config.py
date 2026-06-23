"""Configuración desde .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_FILE = ROOT / "data" / "processed" / "dashboard_data.json"
ALERTAS_STATE_FILE = ROOT / "data" / "processed" / "alertas_estado.json"


def _f(key: str, default: str) -> float:
    return float(os.getenv(key, default))


def _i(key: str, default: str) -> int:
    return int(os.getenv(key, default))


ZONA = {
    "nombre": os.getenv("ZONA_NOMBRE", "Mediterráneo Occidental - Costa Valenciana"),
    "lat_ref": _f("LAT_REF", "39.47"),
    "lon_ref": _f("LON_REF", "-0.38"),
    "ciudad_ref": os.getenv("CIUDAD_REF", "Valencia"),
    "magnitud_min": _f("MAGNITUD_MIN", "3.0"),
    "dias_atras": _i("DIAS_ATRAS", "365"),
    "umbral_score_alerta": _i("UMBRAL_SCORE_ALERTA", "55"),
    "anomalia_sst_umbral": _f("ANOMALIA_SST_UMBRAL", "0.8"),
}

MAPA = {
    "lat_centro": _f("MAPA_LAT_CENTRO", "40.4168"),
    "lon_centro": _f("MAPA_LON_CENTRO", "-3.7038"),
    "ciudad_centro": os.getenv("MAPA_CIUDAD_CENTRO", "Madrid"),
    "lat_min": _f("MAPA_LAT_MIN", "32.0"),
    "lat_max": _f("MAPA_LAT_MAX", "46.0"),
    "lon_min": _f("MAPA_LON_MIN", "-12.0"),
    "lon_max": _f("MAPA_LON_MAX", "8.0"),
    "projection_scale": _f("MAPA_PROJECTION_SCALE", "1.5"),
}

USGS_URL = os.getenv("USGS_URL", "https://earthquake.usgs.gov/fdsnws/event/1/query")
OPEN_METEO_MARINE_URL = os.getenv("OPEN_METEO_MARINE_URL", "https://marine-api.open-meteo.com/v1/marine")
OPEN_METEO_WEATHER_URL = os.getenv("OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")
AEMET_API_KEY = os.getenv("AEMET_API_KEY", "")
AEMET_MUNICIPIO = os.getenv("AEMET_MUNICIPIO", "46250")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = _i("API_PORT", "8000")
API_KEY = os.getenv("API_KEY", "")
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = _i("DASHBOARD_PORT", "8050")
SCHEDULER_MIN = _i("SCHEDULER_INTERVALO_MIN", "30")
DASHBOARD_REFRESH_MS = _i("DASHBOARD_REFRESH_MS", "300000")
FORECAST_DAYS = _i("OPEN_METEO_FORECAST_DAYS", "7")
HTTP_TIMEOUT = _i("HTTP_TIMEOUT", "30")
RATE_LIMIT_SEC = _i("RATE_LIMIT_SEC", "60")
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "true").lower() in ("1", "true", "yes")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:8050,http://localhost:8050").split(",") if o.strip()]

ALLOWED_HOSTS = frozenset({
    "earthquake.usgs.gov", "marine-api.open-meteo.com", "api.open-meteo.com",
    "opendata.aemet.es", "api.telegram.org",
}) | {h.strip() for h in os.getenv("ALLOWED_HTTP_HOSTS", "").split(",") if h.strip()}
