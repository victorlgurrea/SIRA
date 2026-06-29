"""Mapeo y parseo según el formato real de cada fuente externa.

Referencias:
- USGS FDSN / GeoJSON: https://earthquake.usgs.gov/fdsnws/event/1/
- NASA FIRMS area CSV: https://firms.modaps.eosdis.nasa.gov/api/area/
- AEMET Meteoalerta CAP 1.2: opendata.aemet.es/avisos_cap/
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# --- USGS GeoJSON (Feature.properties + geometry.coordinates) ----------------

USGS_COORDS = ("lon", "lat", "profundidad_km")  # geometry.coordinates[0..2]
USGS_PROPS = (
    "mag", "place", "time", "updated", "tsunami", "alert", "status",
    "magType", "type", "sig", "felt", "cdi", "mmi",
)
# properties.tsunami: entero 0|1. USGS lo marca en eventos grandes en región oceánica;
# NO confirma que haya ola. Autoridad tsunami: NOAA/PTWC.
# properties.place: ciudad GeoNames cercana ("12 km NE of Valencia, Spain"), no indica mar/tierra.
# properties.time: epoch en milisegundos UTC.


_RE_USGS_CERCA_CIUDAD = re.compile(
    r"\d+(?:\.\d+)?\s*km\s+[NSEW]{1,3}\s+of\s+",
    re.IGNORECASE,
)

_MAR_EN_LUGAR = (
    " sea", "seaa", "ocean", "océano", "oceano", " mediterranean", " atlantic",
    "golfo", "gulf", " strait", "estrecho", " channel", "canal ", " mar ",
    "tyrrhenian", "balearic", "alboran", "alborán", "ionian", "ionio",
)

# Rectángulos predominantemente marinos en el bbox del mapa (después de excluir tierra ibérica).
_ZONAS_MARITIMAS: tuple[tuple[float, float, float, float], ...] = (
    (35.45, 36.85, -7.8, -4.8),   # Alborán / Estrecho
    (35.45, 37.2, -4.8, -2.0),    # Mar frente a Melilla/Almería
    (36.0, 39.5, -2.0, 0.85),     # Mediterráneo frente a Levante/Valencia
    (38.2, 41.8, 0.85, 3.2),      # Mar entre península y Baleares
    (39.5, 43.2, -1.2, 4.5),      # Mediterráneo norte / Golfo de León
    (36.0, 40.5, -12.0, -9.4),    # Atlántico frente a Galicia/Portugal
    (35.5, 37.0, -9.4, -6.8),     # Atlántico sur (Cádiz/Huelva)
    (27.0, 29.8, -18.8, -13.2),   # Atlántico canario
)

# --- NASA FIRMS CSV (VIIRS *_NRT) --------------------------------------------

FIRMS_CSV_COLUMNS = (
    "latitude", "longitude", "bright_ti4", "scan", "track",
    "acq_date", "acq_time", "satellite", "instrument", "confidence",
    "version", "bright_ti5", "frp", "daynight", "type",
)
# scan × track ≈ área del píxel (km²). confidence: 'h'|'n'|'l' o numérico (MODIS).
# acq_time: HHMM en UTC. Máx. day_range API FIRMS: 5.

# --- AEMET CAP 1.2 (Meteoalerta) ---------------------------------------------

AEMET_EVENT_CODES = (
    "AEMET-Meteoalerta nivel",
    "AEMET-Meteoalerta fenomeno",
    "AEMET-Meteoalerta parametro",
    "AEMET-Meteoalerta probabilidad",
)
AEMET_AREA_CODE = "AEMET-Meteoalerta zona"
# fenomeno: código de 2 letras (CO=oleaje costero, RI=rissaga, …).
# parametro: "CO;Oleaje;3 m" (tipo;descripción;magnitud).
# zona: código Meteoalerta; costeras suelen terminar en C.


def usgs_tsunami_flag(usgs_tsunami: int | bool | None) -> bool:
    try:
        return int(usgs_tsunami or 0) == 1
    except (TypeError, ValueError):
        return bool(usgs_tsunami)


def usgs_lugar_indica_mar(lugar: str | None) -> bool:
    txt = f" {(lugar or '').lower()} "
    return any(k in txt for k in _MAR_EN_LUGAR)


def usgs_lugar_indica_tierra(lugar: str | None) -> bool:
    """USGS cita la ciudad GeoNames más cercana; el patrón 'X km DIR of Ciudad' implica epicentro en tierra firme."""
    if not lugar:
        return False
    return bool(_RE_USGS_CERCA_CIUDAD.search(lugar))


def _en_tierra_iberica(lat: float, lon: float) -> bool:
    """Superficie firme aproximada: península, Baleares, Canarias, Ceuta y Melilla."""
    # Agua mediterránea al E de la costa (excluir del polígono peninsular amplio)
    if 38.2 <= lat <= 40.8 and 0.05 <= lon <= 3.0:
        return False
    if 36.8 <= lat <= 38.2 and -2.0 <= lon <= 1.5:
        return False
    if 27.45 <= lat <= 29.65 and -18.55 <= lon <= -12.95:
        return True
    if 38.62 <= lat <= 40.12 and 1.05 <= lon <= 4.42:
        return True
    if 35.85 <= lat <= 35.95 and -5.45 <= lon <= -5.25:
        return True
    if 35.22 <= lat <= 35.35 and -3.05 <= lon <= -2.85:
        return True
    if 36.05 <= lat <= 43.85 and -9.55 <= lon <= 3.35:
        if lon >= 0.2 and lat < 37.0:
            return False
        if lat < 36.25 and lon < -2.5:
            return False
        if lon < -9.35 and lat > 41.5:
            return False
        return True
    return False


def _en_zona_maritima(lat: float, lon: float) -> bool:
    return any(lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
               for lat_min, lat_max, lon_min, lon_max in _ZONAS_MARITIMAS)


def epicentro_en_mar(
    lat: float,
    lon: float,
    *,
    lugar: str | None = None,
    profundidad_km: float = 0,
    usgs_tsunami: int | bool | None = None,
) -> bool:
    """Epicentro en el mar (no tierra firme ibérica).

    Orden según señales de la API USGS y geografía local:
    1. place con nombre de mar/océano → True.
    2. Tierra ibérica por coordenadas → False (tierra manda sobre USGS tsunami).
    3. properties.tsunami=1 → True.
    4. place con patrón «X km … of Ciudad» → False.
    5. Coordenadas en faja marítima → True.
    6. Por defecto → False.
    """
    if usgs_lugar_indica_mar(lugar):
        return True
    if _en_tierra_iberica(lat, lon):
        return False
    if usgs_tsunami_flag(usgs_tsunami):
        return True
    if usgs_lugar_indica_tierra(lugar):
        return False
    if profundidad_km > 300:
        return False
    if _en_zona_maritima(lat, lon):
        return True
    return False


def parse_usgs_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    """GeoJSON Feature USGS → dict normalizado para SIRA."""
    props = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) < 3 or props.get("mag") is None:
        return None

    lon, lat, prof = float(coords[0]), float(coords[1]), float(coords[2] or 0)
    mag = float(props["mag"])
    lugar = str(props.get("place") or "")[:200]
    usgs_ts = props.get("tsunami")
    en_mar = epicentro_en_mar(lat, lon, lugar=lugar, profundidad_km=prof, usgs_tsunami=usgs_ts)

    return {
        "id": feature.get("id"),
        "magnitud": mag,
        "lugar": lugar,
        "timestamp": datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc).isoformat(),
        "lat": lat,
        "lon": lon,
        "profundidad": prof,
        "usgs_tsunami": 1 if usgs_tsunami_flag(usgs_ts) else 0,
        "en_mar": en_mar,
        "es_submarino": prof < 200,
        "usgs_alert": props.get("alert"),
        "usgs_status": props.get("status"),
        "mag_type": props.get("magType"),
        "_tsunami_raw": usgs_ts,
    }


def parse_firms_row(row: dict[str, str]) -> dict[str, Any] | None:
    """Fila CSV FIRMS VIIRS → detección normalizada."""
    try:
        lat = float(row.get("latitude", ""))
        lon = float(row.get("longitude", ""))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    def _f(key: str, default: float = 0.0) -> float:
        try:
            v = float(row.get(key) or default)
            return v if v > 0 else default
        except (TypeError, ValueError):
            return default

    scan = _f("scan", 1.0)
    track = _f("track", 1.0)
    acq_date = str(row.get("acq_date") or "").strip()
    acq_time = str(row.get("acq_time") or "").strip().zfill(4)
    ts = f"{acq_date}T{acq_time[:2]}:{acq_time[2:4]}:00" if acq_date and acq_time else ""

    return {
        "lat": lat,
        "lon": lon,
        "scan_km": scan,
        "track_km": track,
        "area_km2": scan * track,
        "frp_mw": max(0.0, _f("frp", 0.0)),
        "satelite": str(row.get("satellite") or row.get("instrument") or "VIIRS"),
        "timestamp": ts,
        "confianza": str(row.get("confidence") or ""),
        "daynight": str(row.get("daynight") or ""),
        "tipo": str(row.get("type") or ""),
    }
