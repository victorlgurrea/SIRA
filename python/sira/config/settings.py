"""Configuración desde .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# settings.py → config/ → sira/ → python/ → raíz del repo
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data" / "processed"
DATA_FILE = DATA_DIR / "dashboard_data.json"
_db_env = Path(os.getenv("DB_PATH", str(DATA_DIR / "sira.db")))
DB_PATH = _db_env if _db_env.is_absolute() else (ROOT / _db_env).resolve()
# Legacy JSON (migración → SQLite en db.py)
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
    "exp_mag": _f("SISMO_PERCEPTIBLE_EXP_MAG", "0.34"),
    "exp_base": _f("SISMO_PERCEPTIBLE_EXP_BASE", "0.30"),
    "prof_km": _f("SISMO_PERCEPTIBLE_PROF_KM", "70"),
    "max_km": _f("SISMO_PERCEPTIBLE_MAX_KM", "450"),
}

# Radio de aviso tsunami (km) · solo sismos con epicentro en el mar
# radio ≈ TSUNAMI_FACTOR × 10^(TSUNAMI_EXP_MAG × (M − TSUNAMI_MAG_REF))
TSUNAMI = {
    "mag_ref": _f("TSUNAMI_MAG_REF", "6.5"),
    "mag_min": _f("TSUNAMI_MAG_MIN", "6.5"),
    "factor": _f("TSUNAMI_FACTOR", "100.0"),
    "exp_mag": _f("TSUNAMI_EXP_MAG", "0.55"),
    "prof_km": _f("TSUNAMI_PROF_KM", "50"),
    "min_km": _f("TSUNAMI_MIN_KM", "80"),
    "max_km": _f("TSUNAMI_MAX_KM", "1200"),
}

TSUNAMI_GOV_FEED_URL = os.getenv(
    "TSUNAMI_GOV_FEED_URL",
    "https://www.tsunami.gov/php/esri.php?a=t&format=json",
)
TSUNAMI_GOV_CACHE_SEC = _i("TSUNAMI_GOV_CACHE_SEC", "300")

# Círculos azules en mapa para avisos costeros AEMET (CO oleaje / RI rissaga)
COSTERO_MAPA = {
    "radio_base": _f("COSTERO_RADIO_BASE_KM", "75"),
    "min_km": _f("COSTERO_RADIO_MIN_KM", "45"),
    "max_km": _f("COSTERO_RADIO_MAX_KM", "160"),
    "oleaje_ref_m": _f("COSTERO_OLEAJE_REF_M", "3.0"),
    "factor_nivel": {
        "amarillo": _f("COSTERO_FACTOR_AMARILLO", "1.0"),
        "naranja": _f("COSTERO_FACTOR_NARANJA", "1.35"),
        "rojo": _f("COSTERO_FACTOR_ROJO", "1.7"),
    },
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

# Cuadrícula SST Mediterráneo (Copernicus Marine CMEMS L4 HR)
# Registro: https://data.marine.copernicus.eu/register
CMEMS_USERNAME = os.getenv("COPERNICUSMARINE_SERVICE_USERNAME", "")
CMEMS_PASSWORD = os.getenv("COPERNICUSMARINE_SERVICE_PASSWORD", "")
CMEMS_SST_DATASET_ID = os.getenv(
    "CMEMS_SST_DATASET_ID",
    "cmems_mod_med_phy-tem_anfc_4.2km-2D_PT1H-m",
)
CMEMS_SST_VARIABLE = os.getenv("CMEMS_SST_VARIABLE", "thetao")
CMEMS_SST_LAT_MIN = _f("CMEMS_SST_LAT_MIN", "30.00")
CMEMS_SST_LAT_MAX = _f("CMEMS_SST_LAT_MAX", "46.50")
CMEMS_SST_LON_MIN = _f("CMEMS_SST_LON_MIN", "-6.50")
CMEMS_SST_LON_MAX = _f("CMEMS_SST_LON_MAX", "20.00")
CMEMS_SST_PASO_DEG = _f("CMEMS_SST_PASO_DEG", "0.12")
CMEMS_SST_MAP_MAX_CELDAS = _i("CMEMS_SST_MAP_MAX_CELDAS", "2600")

USGS_URL = os.getenv("USGS_URL", "https://earthquake.usgs.gov/fdsnws/event/1/query")
# NASA FIRMS — focos activos (clave gratuita: https://firms.modaps.eosdis.nasa.gov/api/map_key)
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")
FIRMS_BASE_URL = os.getenv("FIRMS_BASE_URL", "https://firms.modaps.eosdis.nasa.gov/api")
INCENDIO_DIAS = _i("INCENDIO_DIAS", "3")
INCENDIO_CLUSTER_KM = _f("INCENDIO_CLUSTER_KM", "4.0")
INCENDIO_RADIO_MIN_KM = _f("INCENDIO_RADIO_MIN_KM", "1.5")
INCENDIO_RADIO_MAX_KM = _f("INCENDIO_RADIO_MAX_KM", "35.0")
INCENDIO_RADIO_LOCAL_KM = _f("INCENDIO_RADIO_LOCAL_KM", "75.0")
INCENDIO_MAP_MAX = _i("INCENDIO_MAP_MAX", "18")
COSTERO_MAP_MAX = _i("COSTERO_MAP_MAX", "12")
MAP_CIRCLE_POINTS = _i("MAP_CIRCLE_POINTS", "40")
# Embalses — embals.es (SAIH + MITECO) · https://embals.es/docs/api
EMBALS_API_BASE = os.getenv(
    "EMBALS_API_BASE",
    "https://volcjmdnsxfuekvehwte.supabase.co/functions/v1",
)
EMBALS_API_KEY = os.getenv("EMBALS_API_KEY", "")
EMBALSE_CUENCAS = tuple(
    c.strip().lower()
    for c in os.getenv("EMBALSE_CUENCAS", "jucar,segura,ebro").split(",")
    if c.strip()
)
EMBALSE_UMBRAL_VIGILANCIA = _f("EMBALSE_UMBRAL_VIGILANCIA", "85")
EMBALSE_UMBRAL_ALERTA = _f("EMBALSE_UMBRAL_ALERTA", "95")
EMBALSE_UMBRAL_CRITICO = _f("EMBALSE_UMBRAL_CRITICO", "98")
EMBALSE_RADIO_LOCAL_KM = _f("EMBALSE_RADIO_LOCAL_KM", "120")
EMBALSE_MAP_MAX = _i("EMBALSE_MAP_MAX", "15")
# Aforos — SAIH CHJ (https://saih.chj.es) · red MITECO cuenca Júcar
CHJ_SAIH_BASE = os.getenv("CHJ_SAIH_BASE", "https://saih.chj.es")
CHE_SAIH_BASE = os.getenv("CHE_SAIH_BASE", "https://www.saihebro.com")
CHS_SAIH_BASE = os.getenv("CHS_SAIH_BASE", "https://www.chsegura.es")
AFORO_RADIO_LOCAL_KM = _f("AFORO_RADIO_LOCAL_KM", "100")
AFORO_MAP_MAX = _i("AFORO_MAP_MAX", "20")
AFORO_CAUDAL_VIGILANCIA_M3S = _f("AFORO_CAUDAL_VIGILANCIA_M3S", "1.0")
OPEN_METEO_MARINE_URL = os.getenv("OPEN_METEO_MARINE_URL", "https://marine-api.open-meteo.com/v1/marine")
OPEN_METEO_WEATHER_URL = os.getenv("OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")
AEMET_API_KEY = os.getenv("AEMET_API_KEY", "")
AEMET_MUNICIPIO = os.getenv("AEMET_MUNICIPIO", "46250")
AEMET_PUSH_MIN_LEVEL = os.getenv("AEMET_PUSH_MIN_LEVEL", "amarillo").strip().lower()
# Ventana de predicción Meteoalerta (avisos CAP hasta D+3 / 72 h).
AEMET_CAP_FORECAST_HOURS = _i("AEMET_CAP_FORECAST_HOURS", "72")
AEMET_ALERT_PHENOMENA = tuple(
    p.strip().upper()
    for p in os.getenv(
        "AEMET_ALERT_PHENOMENA",
        "AT,BT,VI,TO,PR,CO,NE,VS,NI,DH,GA,RI,AL",
    ).split(",")
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
# Índice compuesto de impacto grave local (0–100 %)
RIESGO_LOCAL_PESOS = {
    "meteo": _f("RIESGO_LOCAL_PESO_METEO", "0.35"),
    "hidrologia": _f("RIESGO_LOCAL_PESO_HIDRO", "0.25"),
    "sismico": _f("RIESGO_LOCAL_PESO_SISMO", "0.20"),
    "incendio": _f("RIESGO_LOCAL_PESO_INCENDIO", "0.10"),
    "termico": _f("RIESGO_LOCAL_PESO_TERMICO", "0.10"),
}
RIESGO_LOCAL_BONO_CONCURRENCIA = _f("RIESGO_LOCAL_BONO_CONCURRENCIA", "1.15")
RIESGO_LOCAL_CONCURRENCIA_EJES = _i("RIESGO_LOCAL_CONCURRENCIA_EJES", "60")
RIESGO_LOCAL_CONCURRENCIA_MIN = _i("RIESGO_LOCAL_CONCURRENCIA_MIN", "2")
HTTP_TIMEOUT = _i("HTTP_TIMEOUT", "30")
RATE_LIMIT_SEC = _i("RATE_LIMIT_SEC", "60")
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() in ("1", "true", "yes")
ALLOW_DATA_REFRESH = os.getenv("ALLOW_DATA_REFRESH", "false").lower() in ("1", "true", "yes")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:8050,http://localhost:8050").split(",") if o.strip()]
CRON_SECRET = os.getenv("CRON_SECRET", "")
INGESTA_INTERVAL_MIN = _i("INGESTA_INTERVAL_MIN", "60")
HISTORIAL_DIAS_DEFAULT = _i("HISTORIAL_DIAS_DEFAULT", "30")
AFORO_DATOS_MAX_MIN = _i("AFORO_DATOS_MAX_MIN", "25")
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
    "opendata.aemet.es", "www.aemet.es", "aemet.es",
    "api.telegram.org",
    "firms.modaps.eosdis.nasa.gov",
    "volcjmdnsxfuekvehwte.supabase.co",
    "saih.chj.es",
    "www.saihebro.com",
    "saihebro.es",
    "www.saihebro.es",
    "www.chsegura.es",
    "chsegura.es",
    "saihweb.chsegura.es",
    "tsunami.gov",
    "www.tsunami.gov",
}) | {h.strip() for h in os.getenv("ALLOWED_HTTP_HOSTS", "").split(",") if h.strip()}
