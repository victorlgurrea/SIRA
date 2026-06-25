"""Configuración desde .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data" / "processed"
DATA_FILE = DATA_DIR / "dashboard_data.json"
ALERTAS_STATE_FILE = DATA_DIR / "alertas_estado.json"
PUSH_SUBSCRIPTIONS_FILE = DATA_DIR / "push_subscriptions.json"
PUSH_STATE_FILE = DATA_DIR / "push_estado.json"
TEST_SISMO_OVERLAY_FILE = DATA_DIR / "test_sismo_overlay.json"
TEST_METEO_ALERTS_FILE = DATA_DIR / "test_meteo_alerts.json"


def _f(key: str, default: str) -> float:
    return float(os.getenv(key, default))


def _i(key: str, default: str) -> int:
    return int(os.getenv(key, default))


def _pem_env(key: str) -> str:
    raw = os.getenv(key, "").strip()
    if not raw:
        return ""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    return raw.replace("\\n", "\n")


ZONA = {
    "nombre": os.getenv("ZONA_NOMBRE", "Mediterráneo Occidental - Costa Valenciana"),
    "lat_ref": _f("LAT_REF", "39.47"),
    "lon_ref": _f("LON_REF", "-0.38"),
    "ciudad_ref": os.getenv("CIUDAD_REF", "Valencia"),
    "magnitud_min": _f("MAGNITUD_MIN", "3.0"),
    "dias_atras": _i("DIAS_ATRAS", "30"),
    "umbral_score_alerta": _i("UMBRAL_SCORE_ALERTA", "55"),
    "anomalia_sst_umbral": _f("ANOMALIA_SST_UMBRAL", "0.8"),
}

# Radio de percepción sísmica (km) desde la localidad · MMI ≥ II
# radio ≈ FACTOR × 10^(EXP_MAG × M + EXP_BASE); profundos amplían el radio
SISMO_PERCEPCION = {
    "mag_min": _f("SISMO_PERCEPTIBLE_MAG_MIN", "2.5"),
    "factor": _f("SISMO_PERCEPTIBLE_FACTOR", "1.0"),
    "exp_mag": _f("SISMO_PERCEPTIBLE_EXP_MAG", "0.55"),
    "exp_base": _f("SISMO_PERCEPTIBLE_EXP_BASE", "0.15"),
    "prof_km": _f("SISMO_PERCEPTIBLE_PROF_KM", "70"),
    "max_km": _f("SISMO_PERCEPTIBLE_MAX_KM", "0"),
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

# Puntos de referencia marinos por costa (Open-Meteo marine)
MARES = {
    "MEDITERRÁNEO": {
        "nombre": "Mar Mediterráneo",
        "lat": _f("MAR_MED_LAT", "39.20"),
        "lon": _f("MAR_MED_LON", "0.20"),
        "punto": os.getenv("MAR_MED_PUNTO", "Valencia"),
    },
    "CANTÁBRICO": {
        "nombre": "Mar Cantábrico",
        "lat": _f("MAR_CANT_LAT", "43.46"),
        "lon": _f("MAR_CANT_LON", "-3.81"),
        "punto": os.getenv("MAR_CANT_PUNTO", "Santander"),
    },
    "ATLÁNTICO": {
        "nombre": "Mar Atlántico",
        "lat": _f("MAR_ATL_LAT", "42.90"),
        "lon": _f("MAR_ATL_LON", "-9.35"),
        "punto": os.getenv("MAR_ATL_PUNTO", "Costa atlántica — Galicia"),
    },
}

USGS_URL = os.getenv("USGS_URL", "https://earthquake.usgs.gov/fdsnws/event/1/query")
OPEN_METEO_MARINE_URL = os.getenv("OPEN_METEO_MARINE_URL", "https://marine-api.open-meteo.com/v1/marine")
OPEN_METEO_WEATHER_URL = os.getenv("OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")
AEMET_API_KEY = os.getenv("AEMET_API_KEY", "")
AEMET_MUNICIPIO = os.getenv("AEMET_MUNICIPIO", "46250")
AEMET_PUSH_MIN_LEVEL = os.getenv("AEMET_PUSH_MIN_LEVEL", "naranja").strip().lower()
AEMET_ALERT_PHENOMENA = tuple(
    p.strip().upper()
    for p in os.getenv("AEMET_ALERT_PHENOMENA", "AT,VI,TO,PR,CO").split(",")
    if p.strip()
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = _i("API_PORT", "8000")
API_KEY = os.getenv("API_KEY", "")
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = _i("DASHBOARD_PORT", "8050")
SCHEDULER_MIN = _i("SCHEDULER_INTERVALO_MIN", "30")
DASHBOARD_REFRESH_MIN = _i("DASHBOARD_REFRESH_MIN", "5")
if os.getenv("DASHBOARD_REFRESH_MS"):
    DASHBOARD_REFRESH_MS = _i("DASHBOARD_REFRESH_MS", "300000")
else:
    DASHBOARD_REFRESH_MS = DASHBOARD_REFRESH_MIN * 60_000
FORECAST_DAYS = _i("OPEN_METEO_FORECAST_DAYS", "7")
RIESGO_METEO_HORAS = _i("RIESGO_METEO_HORAS", "48")
HTTP_TIMEOUT = _i("HTTP_TIMEOUT", "30")
RATE_LIMIT_SEC = _i("RATE_LIMIT_SEC", "60")
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() in ("1", "true", "yes")
ALLOW_DATA_REFRESH = os.getenv("ALLOW_DATA_REFRESH", "false").lower() in ("1", "true", "yes")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:8050,http://localhost:8050").split(",") if o.strip()]
CRON_SECRET = os.getenv("CRON_SECRET", "")
INGESTA_INTERVAL_MIN = _i("INGESTA_INTERVAL_MIN", "60")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = _pem_env("VAPID_PRIVATE_KEY")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@sira.local")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = _i("SMTP_PORT", "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

ALLOWED_HOSTS = frozenset({
    "earthquake.usgs.gov", "marine-api.open-meteo.com", "api.open-meteo.com",
    "geocoding-api.open-meteo.com", "datasets-server.huggingface.co",
    "raw.githubusercontent.com", "huggingface.co",
    "opendata.aemet.es", "api.telegram.org",
}) | {h.strip() for h in os.getenv("ALLOWED_HTTP_HOSTS", "").split(",") if h.strip()}
