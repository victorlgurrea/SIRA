"""Orquestación de ingesta USGS + Open-Meteo + AEMET → dashboard_data.json."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import requests

from sira.infrastructure.sources.meteo.aemet_alerts import deduplicar_alertas
from sira.infrastructure.sources.hydrology.chj import descargar_aforos as descargar_aforos_chj
from sira.infrastructure.sources.hydrology.reservoirs import descargar_embalses
from sira.infrastructure.sources.hydrology.segura import descargar_aforos as descargar_aforos_segura
from sira.infrastructure.sources.fire.firms import descargar_incendios
from sira.config.settings import (
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
from sira.infrastructure.http.client import fetch_aemet, fetch_json, write_dashboard
from sira.infrastructure.parsers.fuentes import parse_usgs_feature
from sira.services.historial.snapshots import guardar_snapshots_diarios
from sira.infrastructure.sources.meteo.parse import VACIO_METEO, hourly as _hourly, pack_meteo as _pack_meteo, parse_aemet as _parse_aemet
from sira.infrastructure.sources.meteo.live import meteo_localidad
from sira.infrastructure.sources.meteo.termico import construir_termico_ccaa
from sira.infrastructure.sources.hydrology.ebro import descargar_aforos as descargar_aforos_ebro
from sira.services.ingesta.source_status import estado_fuente, fmt_error_fuente
from sira.domain.seismic.sismos import distancia_km, radio_tsunami_km, riesgo_tsunami, score_sismo
from sira.services.overlays.sismo import clear_test_overlay

log = logging.getLogger(__name__)
VACIO_OCE = {"serie_horaria": [], "resumen": {}}


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


def descargar_sismos() -> list[dict]:
    fin, inicio = date.today(), date.today() - timedelta(days=ZONA["dias_atras"])
    params = {
        "format": "geojson", "starttime": inicio.isoformat(), "endtime": fin.isoformat(),
        "minlatitude": MAPA["lat_min"], "maxlatitude": MAPA["lat_max"],
        "minlongitude": MAPA["lon_min"], "maxlongitude": MAPA["lon_max"],
        "minmagnitude": ZONA["magnitud_min"], "orderby": "time",
    }
    features = fetch_json(USGS_URL, params).get("features", [])

    sismos = []
    for f in features:
        row = parse_usgs_feature(f)
        if not row:
            continue
        lat, lon = row["lat"], row["lon"]
        mag, prof = row["magnitud"], row["profundidad"]
        en_mar = row["en_mar"]
        sub = row["es_submarino"]
        dist = _dist_km(lat, lon)
        ts_flag = riesgo_tsunami(mag, prof, en_mar, row.get("_tsunami_raw"))
        sismos.append({
            "id": row["id"],
            "magnitud": mag,
            "lugar": row["lugar"],
            "timestamp": row["timestamp"],
            "lat": lat,
            "lon": lon,
            "profundidad": prof,
            "dist_valencia_km": dist,
            "en_mar": en_mar,
            "es_submarino": sub,
            "region": _region(lat, lon),
            "usgs_tsunami": row["usgs_tsunami"],
            "alerta_tsunami": ts_flag,
            "radio_tsunami_km": radio_tsunami_km(mag, prof, en_mar=True) if ts_flag else 0.0,
            **score_sismo(mag, prof, dist, sub),
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


def _descargar_alertas_cap() -> list[dict]:
    from sira.infrastructure.sources.meteo.aemet_alerts import fetch_vigentes_alerts

    return fetch_vigentes_alerts(AEMET_API_KEY or None)


def ejecutar_ingesta():
    clear_test_overlay()
    fuentes_estado: dict[str, dict] = {}

    sismos, fuentes_estado["usgs"] = estado_fuente("USGS", descargar_sismos, default=[])
    incendios, fuentes_estado["firms"] = estado_fuente("FIRMS", descargar_incendios, default=[])
    embalses, fuentes_estado["embals_es"] = estado_fuente("embals.es", descargar_embalses, default=[])

    alertas_cap: list[dict] = []
    try:
        alertas_cap = _descargar_alertas_cap()
        fuentes_estado["aemet_cap"] = {
            "ok": True,
            "registros": len(alertas_cap),
            "error": None if alertas_cap else "Sin avisos CAP vigentes",
        }
    except Exception as exc:  # noqa: BLE001
        fuentes_estado["aemet_cap"] = {"ok": False, "registros": 0, "error": fmt_error_fuente(exc)}

    aforos_chj, fuentes_estado["saih_chj"] = estado_fuente(
        "SAIH CHJ", descargar_aforos_chj, alertas_cap, default=[],
    )
    aforos_che, fuentes_estado["saih_che"] = estado_fuente(
        "SAIH Ebro", descargar_aforos_ebro, alertas_cap, default=[],
    )
    aforos_chs, fuentes_estado["saih_chs"] = estado_fuente(
        "SAIH Segura", descargar_aforos_segura, alertas_cap, default=[],
    )
    for af in aforos_chj:
        af.setdefault("cuenca", "CHJ")
    for af in aforos_che:
        af.setdefault("cuenca", "CHE")
    for af in aforos_chs:
        af.setdefault("cuenca", "CHS")
    aforos = aforos_chj + aforos_che + aforos_chs
    termico_ccaa, fuentes_estado["termico_ccaa"] = estado_fuente(
        "Térmico CCAA",
        construir_termico_ccaa,
        lambda mid, nombre=None: meteo_localidad(mid, nombre, prefer_aemet=False),
        default={"generado_en": None, "provincias": [], "ccaa": []},
    )
    oceanografia, fuentes_estado["open_meteo_marine"] = estado_fuente(
        "Open-Meteo marine", descargar_oceanografia, default={},
    )

    meteo_ok = False
    meteo_error = None
    meteo: dict = VACIO_METEO
    try:
        meteo = descargar_meteo()
        meteo_ok = bool(meteo.get("serie_horaria"))
        fuente = str(meteo.get("fuente") or "")
        clave = "aemet_meteo" if fuente == "AEMET" else "open_meteo_weather"
        fuentes_estado[clave] = {
            "ok": meteo_ok,
            "registros": len(meteo.get("serie_horaria") or []),
            "error": None if meteo_ok else "Sin serie horaria",
        }
        if fuente == "AEMET":
            fuentes_estado["open_meteo_weather"] = {"ok": True, "registros": 0, "error": None, "omitido": True}
        else:
            fuentes_estado["aemet_meteo"] = {
                "ok": True,
                "registros": 0,
                "error": "Fallback Open-Meteo",
                "omitido": True,
            }
    except Exception as exc:  # noqa: BLE001
        meteo_error = str(exc)
        fuentes_estado["aemet_meteo"] = {"ok": False, "registros": 0, "error": meteo_error}
        fuentes_estado["open_meteo_weather"] = {"ok": False, "registros": 0, "error": meteo_error}

    por_region: dict[str, int] = {}
    for s in sismos:
        por_region[s["region"]] = por_region.get(s["region"], 0) + 1

    payload = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "sismos": sismos,
        "incendios": incendios,
        "embalses": embalses,
        "aforos": aforos,
        "termico_ccaa": termico_ccaa,
        "oceanografia": oceanografia,
        "meteorologia": meteo,
        "meteo_alertas_cap": deduplicar_alertas(alertas_cap),
        "fuentes_estado": fuentes_estado,
        "estadisticas": {
            "n_sismos": len(sismos),
            "n_incendios": len(incendios),
            "n_embalses": len(embalses),
            "n_embalses_vigilancia": sum(
                1 for e in embalses if e.get("nivel_riesgo") in ("vigilancia", "alerta", "critico")
            ),
            "n_aforos": len(aforos),
            "n_aforos_alerta": sum(
                1 for a in aforos if a.get("nivel_riesgo") in ("vigilancia", "alerta", "critico")
            ),
            "n_termico_provincias": len(termico_ccaa.get("provincias") or []),
            "mag_max": max((s["magnitud"] for s in sismos), default=0),
            "score_max": max((s["score_total"] for s in sismos), default=0),
            "n_alto_critico": sum(1 for s in sismos if s["nivel_alerta"] in ("ALTO", "CRÍTICO")),
            "por_region": por_region,
        },
    }
    path = write_dashboard(payload)
    try:
        guardar_snapshots_diarios(
            sismos,
            alertas_cap,
            embalses=embalses,
            aforos=aforos,
            incendios=incendios,
            termico_ccaa=termico_ccaa,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Historial municipal: %s", exc)
    log.info("Guardado: %s", path)
    return path
