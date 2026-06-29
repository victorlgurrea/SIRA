"""Incendios activos en España (NASA FIRMS VIIRS) con radio proporcional al área afectada."""
from __future__ import annotations

import csv
import io
import logging
import math
from datetime import datetime, timezone
from statistics import mean

from config import (
    FIRMS_BASE_URL,
    FIRMS_MAP_KEY,
    INCENDIO_CLUSTER_KM,
    INCENDIO_DIAS,
    INCENDIO_RADIO_LOCAL_KM,
    INCENDIO_RADIO_MAX_KM,
    INCENDIO_RADIO_MIN_KM,
    MAPA,
)
from core import fetch_text
from sismos import circle_perimeter, distancia_km

log = logging.getLogger(__name__)

_FIRMS_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def radio_desde_area_km2(area_km2: float) -> float:
    """Radio equivalente del foco a partir del área afectada estimada."""
    area = max(float(area_km2), 0.01)
    return _clamp(math.sqrt(area / math.pi), INCENDIO_RADIO_MIN_KM, INCENDIO_RADIO_MAX_KM)


def _parse_frp(raw: str | None) -> float:
    try:
        return max(0.0, float(raw or 0))
    except (TypeError, ValueError):
        return 0.0


def _parse_scan_track(raw: str | None, default: float = 1.0) -> float:
    try:
        v = float(raw or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _deteccion_desde_fila(row: dict) -> dict | None:
    try:
        lat = float(row.get("latitude", ""))
        lon = float(row.get("longitude", ""))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    scan = _parse_scan_track(row.get("scan"), 1.0)
    track = _parse_scan_track(row.get("track"), 1.0)
    frp = _parse_frp(row.get("frp"))
    acq_date = str(row.get("acq_date") or "").strip()
    acq_time = str(row.get("acq_time") or "").strip().zfill(4)
    ts = f"{acq_date}T{acq_time[:2]}:{acq_time[2:4]}:00" if acq_date and acq_time else ""
    return {
        "lat": lat,
        "lon": lon,
        "scan_km": scan,
        "track_km": track,
        "area_km2": scan * track,
        "frp_mw": frp,
        "satelite": str(row.get("satellite") or row.get("instrument") or "VIIRS"),
        "timestamp": ts,
        "confianza": str(row.get("confidence") or ""),
    }


def _agrupar_focos(puntos: list[dict], sep_km: float) -> list[list[dict]]:
    if not puntos:
        return []
    usado = [False] * len(puntos)
    grupos: list[list[dict]] = []
    for i, p in enumerate(puntos):
        if usado[i]:
            continue
        grupo = [p]
        usado[i] = True
        cambio = True
        while cambio:
            cambio = False
            for j, q in enumerate(puntos):
                if usado[j]:
                    continue
                for g in grupo:
                    if distancia_km(q["lat"], q["lon"], g["lat"], g["lon"]) <= sep_km:
                        grupo.append(q)
                        usado[j] = True
                        cambio = True
                        break
        grupos.append(grupo)
    return grupos


def _foco_desde_grupo(grupo: list[dict], idx: int) -> dict:
    lats = [p["lat"] for p in grupo]
    lons = [p["lon"] for p in grupo]
    lat = mean(lats)
    lon = mean(lons)
    area_pix = sum(p["area_km2"] for p in grupo)
    frp_total = sum(p["frp_mw"] for p in grupo)
    spread_km = 0.0
    if len(grupo) > 1:
        spread_km = max(distancia_km(lat, lon, p["lat"], p["lon"]) for p in grupo)
    area_est = max(area_pix, math.pi * spread_km**2)
    if frp_total > 0:
        area_frp = frp_total * 0.15
        area_est = max(area_est, area_frp)
    radio = radio_desde_area_km2(area_est)
    ts_vals = [p["timestamp"] for p in grupo if p.get("timestamp")]
    ultima = max(ts_vals) if ts_vals else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    sat = max({p["satelite"] for p in grupo}, key=lambda s: sum(1 for p in grupo if p["satelite"] == s))
    return {
        "id": f"firms-{idx:04d}-{lat:.3f}-{lon:.3f}",
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "radio_km": round(radio, 1),
        "area_km2": round(area_est, 2),
        "frp_mw": round(frp_total, 1),
        "n_detecciones": len(grupo),
        "satelite": sat,
        "ultima_deteccion": ultima,
        "fuente": "NASA FIRMS",
        "lugar": "Foco activo",
    }


def _descargar_fuente(source: str, bbox: str, dias: int) -> list[dict]:
    url = f"{FIRMS_BASE_URL.rstrip('/')}/area/csv/{FIRMS_MAP_KEY}/{source}/{bbox}/{dias}"
    try:
        text = fetch_text(url)
    except Exception as exc:  # noqa: BLE001
        log.warning("FIRMS %s: %s", source, exc)
        return []
    if not text.strip() or text.lstrip().startswith("Invalid"):
        return []
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict] = []
    for row in reader:
        det = _deteccion_desde_fila(row)
        if det:
            out.append(det)
    return out


def descargar_incendios() -> list[dict]:
    """Agrupa detecciones VIIRS en focos con radio proporcional al área estimada."""
    if not FIRMS_MAP_KEY:
        log.warning("FIRMS_MAP_KEY no configurada; incendios omitidos")
        return []
    bbox = f"{MAPA['lon_min']},{MAPA['lat_min']},{MAPA['lon_max']},{MAPA['lat_max']}"
    dias = max(1, min(INCENDIO_DIAS, 10))
    puntos: list[dict] = []
    for source in _FIRMS_SOURCES:
        puntos.extend(_descargar_fuente(source, bbox, dias))
    if not puntos:
        return []
    grupos = _agrupar_focos(puntos, INCENDIO_CLUSTER_KM)
    focos = [_foco_desde_grupo(g, i) for i, g in enumerate(grupos)]
    focos.sort(key=lambda x: (-x["frp_mw"], -x["area_km2"]))
    log.info("Incendios: %d focos (%d detecciones FIRMS)", len(focos), len(puntos))
    return focos


def enriquecer_local(incendio: dict, lat_obs: float, lon_obs: float) -> dict:
    """Distancia y si la zona afectada llega a la localidad del usuario."""
    d = distancia_km(lat_obs, lon_obs, float(incendio["lat"]), float(incendio["lon"]))
    radio = float(incendio.get("radio_km") or INCENDIO_RADIO_MIN_KM)
    afecta = d <= (radio + INCENDIO_RADIO_LOCAL_KM * 0.25)
    cerca = d <= INCENDIO_RADIO_LOCAL_KM
    return {
        **incendio,
        "dist_local_km": d,
        "afecta_local": afecta or cerca,
        "cerca_local": cerca,
    }


def filtrar_locales(incendios: list[dict], lat_obs: float, lon_obs: float) -> list[dict]:
    return [i for i in (enriquecer_local(x, lat_obs, lon_obs) for x in incendios) if i["afecta_local"]]


def poligono_foco(lat: float, lon: float, radio_km: float) -> tuple[list[float], list[float]]:
    """Anillo del foco (solo contorno; relleno vía circle_disk en dashboard)."""
    return circle_perimeter(lat, lon, radio_km)
