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

# Reglas mar/tierra viven en dominio; reexport para parsers legacy.
from sira.domain.geo.mar import (  # noqa: E402
    epicentro_en_mar,
    usgs_lugar_indica_mar,
    usgs_lugar_indica_tierra,
    usgs_tsunami_flag,
)


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
        "profundidad": abs(prof),
        "usgs_tsunami": 1 if usgs_tsunami_flag(usgs_ts) else 0,
        "en_mar": en_mar,
        "es_submarino": abs(prof) < 200,
        "usgs_alert": props.get("alert"),
        "usgs_status": props.get("status"),
        "mag_type": props.get("magType"),
        "fuente": "USGS",
        "_tsunami_raw": usgs_ts,
    }


def parse_emsc_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    """GeoJSON Feature EMSC (seismicportal) → dict normalizado para SIRA."""
    props = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if props.get("mag") is None or len(coords) < 2:
        return None

    lon = float(coords[0])
    lat = float(coords[1])
    prof_raw = coords[2] if len(coords) > 2 else props.get("depth")
    try:
        prof = abs(float(prof_raw or 0))
    except (TypeError, ValueError):
        prof = 0.0
    mag = float(props["mag"])
    region = str(props.get("flynn_region") or props.get("region") or "").strip()
    if region.upper() == "SPAIN" and 37.5 <= lat <= 38.5 and -2.2 <= lon <= -1.0:
        lugar = f"Murcia (cerca Librilla), {lat:.2f}°N {lon:.2f}°E"
    elif region:
        lugar = f"{region.title()}, near {lat:.2f}°N {lon:.2f}°E"
    else:
        lugar = f"EMSC {lat:.2f}°N {lon:.2f}°E"
    lugar = lugar[:200]
    time_raw = props.get("time")
    if isinstance(time_raw, str):
        ts = datetime.fromisoformat(time_raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    elif isinstance(time_raw, (int, float)):
        # epoch ms o s
        sec = float(time_raw) / 1000.0 if float(time_raw) > 1e12 else float(time_raw)
        ts = datetime.fromtimestamp(sec, tz=timezone.utc).isoformat()
    else:
        return None

    en_mar = epicentro_en_mar(lat, lon, lugar=lugar, profundidad_km=prof, usgs_tsunami=0)
    eid = feature.get("id") or props.get("unid") or props.get("source_id")
    return {
        "id": f"emsc-{eid}",
        "magnitud": mag,
        "lugar": lugar,
        "timestamp": ts,
        "lat": lat,
        "lon": lon,
        "profundidad": prof,
        "usgs_tsunami": 0,
        "en_mar": en_mar,
        "es_submarino": prof < 200,
        "usgs_alert": None,
        "usgs_status": props.get("auth") or "EMSC",
        "mag_type": props.get("magtype") or props.get("magType"),
        "fuente": "EMSC",
        "_tsunami_raw": 0,
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
