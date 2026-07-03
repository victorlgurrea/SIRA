"""Incendios activos en España (NASA FIRMS VIIRS) con radio proporcional al área afectada."""
from __future__ import annotations

import csv
import io
import logging
import math
from datetime import datetime, timezone
from functools import lru_cache
from statistics import mean

from config import (
    FIRMS_BASE_URL,
    FIRMS_MAP_KEY,
    INCENDIO_CLUSTER_KM,
    INCENDIO_DIAS,
    INCENDIO_RADIO_LOCAL_KM,
    INCENDIO_RADIO_MAX_KM,
    INCENDIO_RADIO_MIN_KM,
)
from core import fetch_text
from fuentes import parse_firms_row
from sismos import circle_perimeter, distancia_km

log = logging.getLogger(__name__)

_FIRMS_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT")


@lru_cache(maxsize=1)
def _anillos_espana() -> list[list[list[float]]]:
    from geo_bordes_clip import anillos_tierra

    return anillos_tierra()


def _en_espana_aprox(lat: float, lon: float) -> bool:
    """Fallback por cajas: península, Baleares y Canarias."""
    if 27.4 <= lat <= 29.6 and -18.6 <= lon <= -13.0:
        return True
    if 38.4 <= lat <= 40.2 and 0.9 <= lon <= 4.6:
        return True
    if lat < 35.8 or lat > 43.9 or lon < -9.55 or lon > 4.55:
        return False
    if lon < -8.85:
        return False
    if lon < -7.15 and lat < 42.4:
        return False
    if lon < -6.95 and lat < 41.7:
        return False
    return True


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def radio_desde_area_km2(area_km2: float) -> float:
    """Radio equivalente del foco a partir del área afectada estimada."""
    area = max(float(area_km2), 0.01)
    return _clamp(math.sqrt(area / math.pi), INCENDIO_RADIO_MIN_KM, INCENDIO_RADIO_MAX_KM)


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
        "id": f"firms-{lat:.4f}-{lon:.4f}",
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
        det = parse_firms_row(row)
        if det:
            out.append(det)
    return out


def en_espana(lat: float, lon: float) -> bool:
    """Solo territorio español (incluye islas, excluye países vecinos)."""
    try:
        from geo_bordes_clip import punto_en_tierra

        return punto_en_tierra(float(lon), float(lat), _anillos_espana())
    except Exception:  # noqa: BLE001
        # Si falla la geometría local, mantenemos un filtro aproximado de respaldo.
        return _en_espana_aprox(lat, lon)


def _bbox_espana() -> str:
    return "-9.4,35.9,4.4,43.85"


def descargar_incendios() -> list[dict]:
    """Agrupa detecciones VIIRS en focos con radio proporcional al área estimada."""
    if not FIRMS_MAP_KEY:
        log.warning("FIRMS_MAP_KEY no configurada; incendios omitidos")
        return []
    bbox = _bbox_espana()
    dias = max(1, min(INCENDIO_DIAS, 5))
    puntos: list[dict] = []
    for source in _FIRMS_SOURCES:
        puntos.extend(_descargar_fuente(source, bbox, dias))
    puntos = [p for p in puntos if en_espana(p["lat"], p["lon"])]
    if not puntos:
        return []
    grupos = _agrupar_focos(puntos, INCENDIO_CLUSTER_KM)
    focos = [_foco_desde_grupo(g, i) for i, g in enumerate(grupos)]
    focos = [f for f in focos if en_espana(f["lat"], f["lon"])]
    focos.sort(key=lambda x: (-x["frp_mw"], -x["area_km2"]))
    log.info("Incendios España: %d focos (%d detecciones FIRMS)", len(focos), len(puntos))
    return focos


def enriquecer_local(incendio: dict, lat_obs: float, lon_obs: float) -> dict:
    """Distancia y si la zona afectada llega a la localidad del usuario."""
    d = distancia_km(lat_obs, lon_obs, float(incendio["lat"]), float(incendio["lon"]))
    radio = float(incendio.get("radio_km") or INCENDIO_RADIO_MIN_KM)
    margen = INCENDIO_RADIO_LOCAL_KM * 0.25
    afecta = d <= (radio + margen)
    cerca = d <= INCENDIO_RADIO_LOCAL_KM
    return {
        **incendio,
        "dist_local_km": d,
        "afecta_local": afecta,
        "cerca_local": cerca,
    }


def filtrar_locales(incendios: list[dict], lat_obs: float, lon_obs: float) -> list[dict]:
    return [i for i in (enriquecer_local(x, lat_obs, lon_obs) for x in incendios) if i["afecta_local"]]


def alerta_incendio_local(incendio: dict, lat: float, lon: float) -> dict | None:
    """Foco que afecta la localidad del usuario (mismo criterio que el mapa)."""
    info = enriquecer_local(incendio, lat, lon)
    if not info.get("afecta_local"):
        return None
    return info


def poligono_foco(lat: float, lon: float, radio_km: float) -> tuple[list[float], list[float]]:
    """Anillo del foco (solo contorno; relleno vía circle_disk en dashboard)."""
    return circle_perimeter(lat, lon, radio_km)
