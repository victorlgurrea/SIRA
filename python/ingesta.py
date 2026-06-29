"""Ingesta USGS + Open-Meteo + AEMET → dashboard_data.json"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import requests

from config import (
    AEMET_API_KEY,
    AEMET_MUNICIPIO,
    FORECAST_DAYS,
    MAPA,
    MARES,
    OPEN_METEO_MARINE_URL,
    OPEN_METEO_WEATHER_URL,
    USGS_URL,
    ZONA,
)
from core import fetch_aemet, fetch_json, write_dashboard
from incendios import descargar_incendios
from sismos import distancia_km, score_sismo
from test_overlay import clear_test_overlay

log = logging.getLogger(__name__)
VACIO_OCE = {"serie_horaria": [], "resumen": {}}
VACIO_METEO = {"fuente": "—", "serie_horaria": [], "resumen": {}}


def _region(lat: float, lon: float) -> str:
    if lat >= 42.5 and lon <= 1.0:
        return "CANTÁBRICO"
    if lon < -5.5:
        return "ATLÁNTICO"
    if lon >= -1.0 or (lat <= 38.0 and lon >= -6.0):
        return "MEDITERRÁNEO"
    return "IBÉRICO"


def _dist_km(lat: float, lon: float) -> float:
    rlat, rlon = ZONA["lat_ref"], ZONA["lon_ref"]
    return distancia_km(lat, lon, rlat, rlon)


def _hourly(data: dict, mapping: dict[str, str]) -> list[dict]:
    h = data.get("hourly", {})
    times = h.get("time", [])
    return [
        {"timestamp": t, **{out: h.get(src, [None] * len(times))[i] for out, src in mapping.items()}}
        for i, t in enumerate(times)
    ]


def _aemet_val(obj) -> str | int | float | None:
    return obj.get("value") if isinstance(obj, dict) else obj


def _num(val, default: float = 0.0) -> float:
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("", "ip", "0"):
        return default
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return default


def _resumen_lluvia(serie: list[dict]) -> dict:
    s24 = serie[:24]
    probs = [x["prob_precip_pct"] for x in s24 if x.get("prob_precip_pct") is not None]
    return {
        "precip_prox_24h_mm": round(sum(x.get("precip_mm", 0) for x in s24), 1),
        "prob_max_pct": max(probs, default=0),
        "prob_actual_pct": s24[0].get("prob_precip_pct") if s24 else None,
    }


def _pack_meteo(fuente: str, municipio: str, serie: list[dict]) -> dict:
    serie = serie[:48]
    return {"fuente": fuente, "municipio": municipio, "serie_horaria": serie, "resumen": _resumen_lluvia(serie)}


def descargar_sismos() -> list[dict]:
    fin, inicio = date.today(), date.today() - timedelta(days=ZONA["dias_atras"])
    params = {
        "format": "geojson", "starttime": inicio.isoformat(), "endtime": fin.isoformat(),
        "minlatitude": MAPA["lat_min"], "maxlatitude": MAPA["lat_max"],
        "minlongitude": MAPA["lon_min"], "maxlongitude": MAPA["lon_max"],
        "minmagnitude": ZONA["magnitud_min"], "orderby": "time",
    }
    try:
        features = fetch_json(USGS_URL, params).get("features", [])
    except (requests.RequestException, ValueError, OSError) as exc:
        log.warning("USGS: %s", exc)
        return []

    sismos = []
    for f in features:
        p, c = f.get("properties", {}), f.get("geometry", {}).get("coordinates", [])
        if len(c) < 3 or p.get("mag") is None:
            continue
        lon, lat, prof = float(c[0]), float(c[1]), float(c[2] or 0)
        sub, dist = prof < 200, _dist_km(lat, lon)
        sismos.append({
            "id": f.get("id"), "magnitud": float(p["mag"]),
            "lugar": str(p.get("place", ""))[:200],
            "timestamp": datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).isoformat(),
            "lat": lat, "lon": lon, "profundidad": prof,
            "dist_valencia_km": dist, "es_submarino": sub, "region": _region(lat, lon),
            **score_sismo(float(p["mag"]), prof, dist, sub),
        })
    log.info("Sismos: %d", len(sismos))
    return sismos


def descargar_oceanografia() -> dict:
    resultado: dict = {}
    for clave, mar in MARES.items():
        try:
            data = fetch_json(OPEN_METEO_MARINE_URL, {
                "latitude": mar["lat"], "longitude": mar["lon"],
                "hourly": "sea_surface_temperature,ocean_current_velocity,ocean_current_direction",
                "timezone": "UTC", "forecast_days": FORECAST_DAYS,
            })
            serie = _hourly(data, {
                "sst_c": "sea_surface_temperature",
                "corriente_vel_ms": "ocean_current_velocity",
                "corriente_dir_grados": "ocean_current_direction",
            })
        except (requests.RequestException, ValueError, OSError) as exc:
            log.warning("Open-Meteo marine %s: %s", clave, exc)
            resultado[clave] = dict(VACIO_OCE)
            continue

        sst_vals = [x["sst_c"] for x in serie if x["sst_c"] is not None]
        media = sum(sst_vals) / len(sst_vals) if sst_vals else 0.0
        ult = serie[-1] if serie else {}
        anom = (ult.get("sst_c") or media) - media
        resultado[clave] = {
            "punto": mar["punto"],
            "serie_horaria": serie,
            "resumen": {
                "sst_media_c": round(media, 2),
                "sst_actual_c": ult.get("sst_c"),
                "anomalia_c": round(anom, 2),
                "alerta_termica": abs(anom) > ZONA["anomalia_sst_umbral"],
                "corriente_vel_ms": ult.get("corriente_vel_ms"),
                "corriente_dir_grados": ult.get("corriente_dir_grados"),
            },
        }
    log.info("Oceanografía: %d zonas", len(resultado))
    return resultado


def _parse_aemet(data: dict | list) -> list[dict]:
    item = (data[0] if isinstance(data, list) else data) or {}
    serie = []
    for dia in item.get("prediccion", {}).get("dia", []):
        fecha = dia.get("fecha", "")
        for h in dia.get("hora", []):
            periodo = str(h.get("periodo", ""))
            ts = f"{fecha}T{periodo.zfill(2)}:00" if periodo.isdigit() else fecha
            prob = _aemet_val(h.get("probPrecipitacion"))
            serie.append({
                "timestamp": ts,
                "precip_mm": _num(_aemet_val(h.get("precipitacion"))),
                "prob_precip_pct": int(prob) if prob is not None and str(prob).strip().isdigit() else None,
            })
    return serie


def descargar_meteo() -> dict:
    if AEMET_API_KEY:
        try:
            data = fetch_aemet(f"prediccion/especifica/municipio/horaria/{AEMET_MUNICIPIO}", AEMET_API_KEY)
            item = (data[0] if isinstance(data, list) else data) or {}
            serie = _parse_aemet(data)
            if serie:
                log.info("Meteo AEMET: %s", AEMET_MUNICIPIO)
                return _pack_meteo("AEMET", item.get("nombre", AEMET_MUNICIPIO), serie)
        except (requests.RequestException, ValueError, OSError) as exc:
            log.warning("AEMET: %s — fallback Open-Meteo", exc)

    try:
        data = fetch_json(OPEN_METEO_WEATHER_URL, {
            "latitude": ZONA["lat_ref"], "longitude": ZONA["lon_ref"],
            "hourly": "precipitation,precipitation_probability",
            "timezone": "Europe/Madrid", "forecast_days": FORECAST_DAYS,
        })
        serie = _hourly(data, {"precip_mm": "precipitation", "prob_precip_pct": "precipitation_probability"})
        for row in serie:
            row["precip_mm"] = row["precip_mm"] or 0.0
        log.info("Meteo Open-Meteo")
        return _pack_meteo("Open-Meteo", ZONA["ciudad_ref"], serie)
    except (requests.RequestException, ValueError, OSError) as exc:
        log.warning("Open-Meteo weather: %s", exc)
        return VACIO_METEO


def ejecutar_ingesta():
    clear_test_overlay()
    sismos = descargar_sismos()
    incendios = descargar_incendios()
    por_region: dict[str, int] = {}
    for s in sismos:
        por_region[s["region"]] = por_region.get(s["region"], 0) + 1

    payload = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "sismos": sismos,
        "incendios": incendios,
        "oceanografia": descargar_oceanografia(),
        "meteorologia": descargar_meteo(),
        "estadisticas": {
            "n_sismos": len(sismos),
            "n_incendios": len(incendios),
            "mag_max": max((s["magnitud"] for s in sismos), default=0),
            "score_max": max((s["score_total"] for s in sismos), default=0),
            "n_alto_critico": sum(1 for s in sismos if s["nivel_alerta"] in ("ALTO", "CRÍTICO")),
            "por_region": por_region,
        },
    }
    path = write_dashboard(payload)
    log.info("Guardado: %s", path)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ejecutar_ingesta()
