"""Snapshots diarios de riesgo por municipio."""
from __future__ import annotations

import logging
from datetime import date

from sira.config.settings import AEMET_MUNICIPIO
from sira.infrastructure.sources.meteo.aemet_alerts import alerta_coincide_zona, deduplicar_alertas
from sira.infrastructure.sources.hydrology.chj import resumen_aforos
from sira.infrastructure.persistence.sqlite import historial_existe, insert_historial_municipio, list_subscriptions, municipios_con_historial
from sira.infrastructure.geo.es import coords_observacion, municipio_por_id, provincia_de_municipio
from sira.infrastructure.sources.hydrology.reservoirs import resumen_embalses
from sira.infrastructure.sources.fire.firms import enriquecer_local as enriquecer_incendio_local
from sira.infrastructure.sources.meteo.live import meteo_localidad
from sira.domain.risks.local import calcular_riesgo_local
from sira.domain.risks.meteo import calcular_riesgo_meteo
from sira.domain.seismic.sismos import enriquecer_local

log = logging.getLogger(__name__)


def municipios_a_snapshot() -> set[str]:
    ids = {str(AEMET_MUNICIPIO).zfill(5)}
    for sub in list_subscriptions():
        mid = sub.get("municipio_id")
        if mid:
            ids.add(str(mid).zfill(5))
    ids.update(municipios_con_historial())
    return ids


def _calcular_e_insertar_snapshot(
    fecha: str,
    mid: str,
    *,
    sismos: list[dict],
    alertas: list[dict],
    emb_list: list[dict],
    afor_list: list[dict],
    inc_list: list[dict],
    termico_ccaa: dict | None,
) -> bool:
    """Calcula métricas del día y persiste si no existía fila para (fecha, municipio)."""
    if historial_existe(fecha, mid):
        return False
    lat, lon, _ = coords_observacion(mid, None)
    sismos_loc = [enriquecer_local(s, lat, lon) for s in sismos]
    scores = [int(s.get("score_local") or 0) for s in sismos_loc]
    score_max = max(scores, default=0)
    muni = municipio_por_id(mid)
    loc = muni["nombre"] if muni else ""
    met = meteo_localidad(mid, loc)
    lluvia_24 = float((met.get("resumen") or {}).get("precip_prox_24h_mm") or 0)
    res_emb = resumen_embalses(emb_list, lat, lon, lluvia_24h_mm=lluvia_24)
    res_afor = resumen_aforos(afor_list, lat, lon)
    inc_local = [
        i for i in (enriquecer_incendio_local(i, lat, lon) for i in inc_list)
        if i.get("cerca_local")
    ]
    alertas_loc = [
        a for a in alertas
        if isinstance(a, dict) and alerta_coincide_zona(a, municipio_id=mid)
    ]
    alertas_loc = deduplicar_alertas(alertas_loc)
    riesgo_met = calcular_riesgo_meteo(alertas_loc, met)
    riesgo_loc = calcular_riesgo_local(
        alertas_meteo=alertas_loc,
        meteo=met,
        sismos=sismos_loc,
        incendios_local=inc_local,
        resumen_embalses=res_emb,
        resumen_aforos=res_afor,
        termico_ccaa=termico_ccaa,
        provincia_id=provincia_de_municipio(mid),
    )
    insert_historial_municipio(
        fecha,
        mid,
        score_sismo_max=score_max,
        indice_riesgo_meteo=int(riesgo_met.get("indice_global") or 0),
        indice_impacto_local=int(riesgo_loc.get("indice") or 0),
    )
    return True


def snapshot_municipio_desde_dashboard(municipio_id: str, dashboard: dict) -> bool:
    """Registra el snapshot de hoy para un municipio usando el JSON del dashboard."""
    from sira.services.mapa.panel_data import alertas_meteo_fuente

    fecha = date.today().isoformat()
    mid = str(municipio_id).zfill(5)
    alertas = alertas_meteo_fuente(dashboard)
    return _calcular_e_insertar_snapshot(
        fecha,
        mid,
        sismos=dashboard.get("sismos") or [],
        alertas=alertas,
        emb_list=dashboard.get("embalses") or [],
        afor_list=dashboard.get("aforos") or [],
        inc_list=dashboard.get("incendios") or [],
        termico_ccaa=dashboard.get("termico_ccaa") or {},
    )


def guardar_snapshots_diarios(
    sismos: list[dict],
    alertas_meteo: list[dict] | None,
    *,
    embalses: list[dict] | None = None,
    aforos: list[dict] | None = None,
    incendios: list[dict] | None = None,
    termico_ccaa: dict | None = None,
) -> int:
    """Un snapshot por municipio y día (idempotente)."""
    fecha = date.today().isoformat()
    alertas = alertas_meteo or []
    emb_list = embalses or []
    afor_list = aforos or []
    inc_list = incendios or []
    guardados = 0
    for mid in sorted(municipios_a_snapshot()):
        if _calcular_e_insertar_snapshot(
            fecha,
            mid,
            sismos=sismos,
            alertas=alertas,
            emb_list=emb_list,
            afor_list=afor_list,
            inc_list=inc_list,
            termico_ccaa=termico_ccaa,
        ):
            guardados += 1
    if guardados:
        log.info("Historial municipal: %d snapshots nuevos (%s)", guardados, fecha)
    return guardados
