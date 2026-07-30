"""Orquestación de ingesta USGS + Open-Meteo + AEMET → dashboard_data.json."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import requests

from sira.infrastructure.sources.meteo.aemet_alerts import deduplicar_alertas
from sira.infrastructure.sources.hydrology.reservoirs import descargar_embalses
from sira.infrastructure.sources.hydrology.multi import descargar_aforos_con_estado
from sira.infrastructure.sources.fire.firms import descargar_incendios
from sira.infrastructure.sources.ocean.cmems_sst import descargar_sst_med_cuadricula
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
from sira.services.ingesta.source_status import estado_fuente, fmt_error_fuente
from sira.domain.geo import distancia_km
from sira.domain.seismic.sismos import radio_tsunami_km, riesgo_tsunami, score_sismo
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


def _bloque_oce_vacio(punto: str | None = None) -> dict:
    out = dict(VACIO_OCE)
    if punto:
        out["punto"] = punto
    return out


def _resumen_oce(serie: list[dict]) -> dict:
    sst_vals = [x["sst_c"] for x in serie if x.get("sst_c") is not None]
    media = sum(sst_vals) / len(sst_vals) if sst_vals else 0.0
    ult = serie[-1] if serie else {}
    anom = (ult.get("sst_c") or media) - media
    return {
        "sst_media_c": round(media, 2),
        "sst_actual_c": ult.get("sst_c"),
        "anomalia_c": round(anom, 2),
        "alerta_termica": abs(anom) > ZONA["anomalia_sst_umbral"],
        "corriente_vel_ms": ult.get("corriente_vel_ms"),
        "corriente_dir_grados": ult.get("corriente_dir_grados"),
    }


def _serie_plana_sst(sst_c: float, horas: int = 24) -> list[dict]:
    """Serie degradada (SST constante) cuando Open-Meteo no responde."""
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [
        {
            "timestamp": (base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00"),
            "sst_c": round(float(sst_c), 2),
            "corriente_vel_ms": None,
            "corriente_dir_grados": None,
        }
        for i in range(max(1, horas))
    ]


def _sst_cerca_grid(grid: dict | None, lat: float, lon: float) -> float | None:
    celdas = (grid or {}).get("celdas") if isinstance(grid, dict) else None
    if not isinstance(celdas, list) or not celdas:
        return None
    mejor = None
    mejor_d = 1e9
    for c in celdas:
        if not isinstance(c, dict) or c.get("sst_c") is None:
            continue
        d = (float(c["lat"]) - lat) ** 2 + (float(c["lon"]) - lon) ** 2
        if d < mejor_d:
            mejor_d = d
            mejor = float(c["sst_c"])
    return mejor


def completar_oceanografia_desde_sst_grid(oceanografia: dict, sst_med_grid: dict | None) -> dict:
    """Si Mediterráneo viene vacío, rellena SST desde la malla CMEMS."""
    if not isinstance(oceanografia, dict):
        oceanografia = {}
    mar = MARES.get("MEDITERRÁNEO") or {}
    bloque = oceanografia.get("MEDITERRÁNEO")
    if isinstance(bloque, dict) and bloque.get("serie_horaria"):
        return oceanografia
    sst = _sst_cerca_grid(sst_med_grid, float(mar.get("lat", 39.2)), float(mar.get("lon", 0.2)))
    if sst is None:
        return oceanografia
    serie = _serie_plana_sst(sst, horas=FORECAST_DAYS * 24)
    oceanografia["MEDITERRÁNEO"] = {
        "punto": mar.get("punto", "Valencia"),
        "serie_horaria": serie,
        "resumen": _resumen_oce(serie),
        "fuente_fallback": "CMEMS SST malla",
    }
    log.info("Oceanografía MEDITERRÁNEO: fallback CMEMS SST=%.2f °C", sst)
    return oceanografia


def descargar_oceanografia() -> dict:
    """SST y corrientes por mar (1 petición Open-Meteo batch + reintentos 429)."""
    import time

    claves = list(MARES.keys())
    lats = ",".join(str(MARES[k]["lat"]) for k in claves)
    lons = ",".join(str(MARES[k]["lon"]) for k in claves)
    params = {
        "latitude": lats,
        "longitude": lons,
        "hourly": "sea_surface_temperature,ocean_current_velocity,ocean_current_direction",
        "timezone": "UTC",
        "forecast_days": FORECAST_DAYS,
    }

    data = None
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            data = fetch_json(OPEN_METEO_MARINE_URL, params)
            break
        except (requests.RequestException, ValueError, OSError) as exc:
            last_exc = exc
            msg = str(exc).lower()
            # Cupo diario: no tiene sentido reintentar hoy.
            if "daily" in msg and ("limit" in msg or "exceeded" in msg):
                raise RuntimeError(f"Open-Meteo marine: cupo diario agotado ({exc})") from exc
            if "429" in msg or "too many requests" in msg:
                # A veces el cuerpo trae el motivo real.
                body = ""
                resp = getattr(exc, "response", None)
                if resp is not None:
                    try:
                        body = (resp.text or "").lower()
                    except Exception:  # noqa: BLE001
                        body = ""
                if "daily" in body and ("limit" in body or "exceeded" in body):
                    raise RuntimeError("Open-Meteo marine: cupo diario agotado") from exc
                sleep_s = 8.0 * (attempt + 1)
                log.warning("Open-Meteo marine 429 (reintento %s/4): esperando %.0fs", attempt + 1, sleep_s)
                time.sleep(sleep_s)
                continue
            log.warning("Open-Meteo marine: %s", exc)
            break

    if data is None:
        raise RuntimeError(f"Open-Meteo marine no disponible: {last_exc or 'sin respuesta'}")

    items = data if isinstance(data, list) else [data]
    resultado: dict = {}
    for i, clave in enumerate(claves):
        mar = MARES[clave]
        item = items[i] if i < len(items) and isinstance(items[i], dict) else {}
        try:
            serie = _hourly(item, {
                "sst_c": "sea_surface_temperature",
                "corriente_vel_ms": "ocean_current_velocity",
                "corriente_dir_grados": "ocean_current_direction",
            })
        except (TypeError, ValueError, KeyError) as exc:
            log.warning("Open-Meteo marine parse %s: %s", clave, exc)
            resultado[clave] = _bloque_oce_vacio(mar.get("punto"))
            continue

        resultado[clave] = {
            "punto": mar["punto"],
            "serie_horaria": serie,
            "resumen": _resumen_oce(serie),
        }

    con_datos = sum(1 for v in resultado.values() if v.get("serie_horaria"))
    log.info("Oceanografía: %d/%d zonas con serie", con_datos, len(resultado))
    if con_datos == 0:
        raise RuntimeError("Open-Meteo marine: sin series (posible 429 o respuesta vacía)")
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

    aforos, estados_aforos = descargar_aforos_con_estado(alertas_cap, estado_fuente)
    fuentes_estado.update(estados_aforos)
    termico_ccaa, fuentes_estado["termico_ccaa"] = estado_fuente(
        "Térmico CCAA",
        construir_termico_ccaa,
        lambda mid, nombre=None: meteo_localidad(mid, nombre, prefer_aemet=False),
        default={"generado_en": None, "provincias": [], "ccaa": []},
    )
    oceanografia, fuentes_estado["open_meteo_marine"] = estado_fuente(
        "Open-Meteo marine", descargar_oceanografia, default={},
    )
    sst_med_grid, fuentes_estado["cmems_sst_med"] = estado_fuente(
        "CMEMS SST Med", descargar_sst_med_cuadricula, default={},
    )
    if isinstance(sst_med_grid, dict):
        fuentes_estado["cmems_sst_med"]["registros"] = len(sst_med_grid.get("celdas") or [])
    if not isinstance(oceanografia, dict):
        oceanografia = {}
    oceanografia = completar_oceanografia_desde_sst_grid(oceanografia, sst_med_grid)
    fuentes_estado["open_meteo_marine"]["registros"] = sum(
        1 for v in oceanografia.values() if isinstance(v, dict) and v.get("serie_horaria")
    )
    if fuentes_estado["open_meteo_marine"]["registros"] and not fuentes_estado["open_meteo_marine"].get("ok"):
        fuentes_estado["open_meteo_marine"]["ok"] = True
        fuentes_estado["open_meteo_marine"]["error"] = "Parcial: Mediterráneo desde CMEMS"
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
        "sst_med_grid": sst_med_grid if isinstance(sst_med_grid, dict) else {},
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
