"""Servicio de aplicación: ensambla datos del mapa geográfico (sin UI Dash)."""
from __future__ import annotations

import time

import requests

from sira.config.settings import AEMET_MUNICIPIO, API_BASE_URL, ZONA
from sira.domain.seismic.sismos import enriquecer_local
from sira.domain.seismic.tsunami_oficial import anexar_boletin_tsunami
from sira.infrastructure.geo.es import coords_observacion, provincia_de_municipio, viewport_mapa_geo
from sira.infrastructure.sources.fire.firms import enriquecer_local as enriquecer_incendio_local
from sira.infrastructure.sources.hydrology.chj import aforos_para_mapa
from sira.infrastructure.sources.hydrology.reservoirs import embalses_para_mapa
from sira.infrastructure.sources.meteo.aemet_alerts import (
    alerta_coincide_zona,
    alertas_para_dia,
    deduplicar_alertas,
)
from sira.infrastructure.sources.meteo.live import meteo_localidad

DEFAULT_MUNI = "46250"
DEFAULT_PROV = "46"

# Cache meteo en memoria del proceso dashboard (evita /api/meteo en cada pintado).
_METEO_CACHE: dict[str, tuple[float, dict]] = {}
_METEO_TTL_SEC = 180.0


def geo_resuelto_min(geo: dict) -> dict:
    """Normaliza ids de provincia/municipio sin dependencia del dashboard."""
    out = dict(geo or {})
    mid = str(out.get("municipio_id") or DEFAULT_MUNI).zfill(5)
    out["municipio_id"] = mid
    if not out.get("provincia_id"):
        out["provincia_id"] = provincia_de_municipio(mid) or DEFAULT_PROV
    out["provincia_id"] = str(out["provincia_id"]).zfill(2)
    return out


def meteo_para_geo(
    municipio_id: str,
    localidad: str | None = None,
    *,
    dashboard: dict | None = None,
) -> dict:
    """Meteo para el municipio: cache → meteo de la ingesta → API (timeout corto)."""
    mid = str(municipio_id or DEFAULT_MUNI).zfill(5)
    loc = (localidad or "").strip() or ""
    cache_key = f"{mid}|{loc}"
    now = time.monotonic()
    hit = _METEO_CACHE.get(cache_key)
    if hit and (now - hit[0]) < _METEO_TTL_SEC:
        return hit[1]

    # Reutilizar meteo ya ingerido cuando coincide el municipio de referencia.
    ref = str(AEMET_MUNICIPIO or DEFAULT_MUNI).zfill(5)
    met_ing = (dashboard or {}).get("meteorologia") if isinstance(dashboard, dict) else None
    if (
        mid == ref
        and isinstance(met_ing, dict)
        and (met_ing.get("serie_horaria") or met_ing.get("resumen"))
    ):
        _METEO_CACHE[cache_key] = (now, met_ing)
        return met_ing

    params = {"localidad": loc} if loc else None
    try:
        r = requests.get(f"{API_BASE_URL}/api/meteo/{mid}", params=params, timeout=8)
        if r.ok:
            data = r.json()
            if isinstance(data, dict):
                _METEO_CACHE[cache_key] = (now, data)
                return data
    except requests.RequestException:
        pass
    data = meteo_localidad(mid, loc or None)
    if isinstance(data, dict):
        _METEO_CACHE[cache_key] = (now, data)
    return data


def alertas_meteo_fuente(d: dict) -> list[dict]:
    local = list(d.get("meteo_alertas_test", [])) if isinstance(d.get("meteo_alertas_test"), list) else []
    live = list(d.get("meteo_alertas_live", [])) if isinstance(d.get("meteo_alertas_live"), list) else []
    return [*local, *live]


def alertas_meteo_locales(geo: dict, alertas: list[dict]) -> list[dict]:
    geo = geo_resuelto_min(geo)
    filtradas = [
        a for a in alertas
        if alerta_coincide_zona(
            a,
            provincia_id=geo.get("provincia_id"),
            municipio_id=geo.get("municipio_id"),
            provincia=geo.get("provincia"),
            municipio=geo.get("municipio"),
        )
    ]
    return deduplicar_alertas(filtradas)


def map_viewport(geo: dict | None) -> dict:
    zoom = (geo or {}).get("map_zoom")
    if zoom and zoom.get("lat_centro") is not None:
        return zoom
    muni_id = (geo or {}).get("municipio_id") or DEFAULT_MUNI
    pid = str((geo or {}).get("provincia_id") or provincia_de_municipio(muni_id) or DEFAULT_PROV).zfill(2)
    loc_id = (geo or {}).get("localidad_id")
    lat_obs, lon_obs, _ = coords_observacion(muni_id, loc_id)
    return viewport_mapa_geo(pid, lat_obs, lon_obs, alejado=True)


def datos_mapa(geo: dict, d: dict, *, geo_resolver=None) -> dict:
    """Enriquece sismos/incendios/hidro/alertas para el mapa (sin UI)."""
    resolve = geo_resolver or geo_resuelto_min
    geo = resolve(geo)
    muni_id = geo.get("municipio_id") or DEFAULT_MUNI
    localidad = geo.get("localidad") or ZONA["ciudad_ref"]
    lat_obs, lon_obs, _ = coords_observacion(muni_id, geo.get("localidad_id"))

    sismos_mapa = [enriquecer_local(s, lat_obs, lon_obs) for s in d.get("sismos", [])]
    sismos_mapa = [
        anexar_boletin_tsunami(s, lat_obs, lon_obs, muni_id)
        if s.get("alerta_tsunami")
        else s
        for s in sismos_mapa
    ]
    for s in sismos_mapa:
        if s.get("alerta_tsunami") and s.get("tsunami_texto_ola"):
            s["area_desc"] = str(s["tsunami_texto_ola"])

    incendios_mapa = [enriquecer_incendio_local(i, lat_obs, lon_obs) for i in d.get("incendios", [])]
    lluvia_24 = float((d.get("meteo") or {}).get("resumen", {}).get("precip_prox_24h_mm") or 0)
    embalses_mapa = embalses_para_mapa(d.get("embalses", []), lat_obs, lon_obs, lluvia_24h_mm=lluvia_24)
    aforos_mapa = aforos_para_mapa(d.get("aforos", []), lat_obs, lon_obs)
    alertas_fuente = alertas_meteo_fuente(d)
    alertas_mapa_hoy = alertas_para_dia(alertas_fuente)

    return {
        "geo": geo,
        "muni_id": muni_id,
        "localidad": localidad,
        "lat_obs": lat_obs,
        "lon_obs": lon_obs,
        "sismos_mapa": sismos_mapa,
        "incendios_mapa": incendios_mapa,
        "embalses_mapa": embalses_mapa,
        "aforos_mapa": aforos_mapa,
        "alertas_mapa_hoy": alertas_mapa_hoy,
        "sst_med_grid": d.get("sst_med_grid") if isinstance(d.get("sst_med_grid"), dict) else {},
    }


def calcular_riesgos_panel(
    *,
    alertas_meteo: list[dict],
    meteo: dict,
    sismos_mapa: list[dict],
    incendios_local: list[dict],
    resumen_embalses: dict,
    resumen_aforos: dict,
    termico_ccaa: dict | None,
    provincia_id: str | None,
    horas_meteo: int,
) -> tuple[dict, dict]:
    """Devuelve (riesgo_meteo, riesgo_local)."""
    from sira.domain.risks.local import calcular_riesgo_local
    from sira.domain.risks.meteo import calcular_riesgo_meteo

    riesgo_met = calcular_riesgo_meteo(alertas_meteo, meteo, horas=horas_meteo)
    riesgo_local = calcular_riesgo_local(
        alertas_meteo=alertas_meteo,
        meteo=meteo,
        sismos=sismos_mapa,
        incendios_local=incendios_local,
        resumen_embalses=resumen_embalses,
        resumen_aforos=resumen_aforos,
        termico_ccaa=termico_ccaa,
        provincia_id=provincia_id,
        horas_meteo=horas_meteo,
    )
    return riesgo_met, riesgo_local
