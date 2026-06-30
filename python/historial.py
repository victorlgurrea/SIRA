"""Snapshots diarios de riesgo por municipio."""
from __future__ import annotations

import logging
from datetime import date

from config import AEMET_MUNICIPIO
from aemet_alerts import alerta_coincide_zona, deduplicar_alertas
from db import historial_existe, insert_historial_municipio, list_subscriptions
from geo_es import coords_observacion, municipio_por_id
from meteo_live import meteo_localidad
from riesgo_meteo import calcular_riesgo_meteo
from sismos import enriquecer_local

log = logging.getLogger(__name__)


def municipios_a_snapshot() -> set[str]:
    ids = {str(AEMET_MUNICIPIO).zfill(5)}
    for sub in list_subscriptions():
        mid = sub.get("municipio_id")
        if mid:
            ids.add(str(mid).zfill(5))
    return ids


def guardar_snapshots_diarios(sismos: list[dict], alertas_meteo: list[dict] | None) -> int:
    """Un snapshot por municipio y día (idempotente)."""
    fecha = date.today().isoformat()
    alertas = alertas_meteo or []
    guardados = 0
    for mid in sorted(municipios_a_snapshot()):
        if historial_existe(fecha, mid):
            continue
        lat, lon, _ = coords_observacion(mid, None)
        scores = [
            int(enriquecer_local(s, lat, lon).get("score_local") or 0)
            for s in sismos
        ]
        score_max = max(scores, default=0)
        muni = municipio_por_id(mid)
        loc = muni["nombre"] if muni else ""
        met = meteo_localidad(mid, loc)
        alertas_loc = [
            a for a in alertas
            if isinstance(a, dict) and alerta_coincide_zona(a, municipio_id=mid)
        ]
        riesgo = calcular_riesgo_meteo(deduplicar_alertas(alertas_loc), met)
        insert_historial_municipio(
            fecha,
            mid,
            score_sismo_max=score_max,
            indice_riesgo_meteo=int(riesgo.get("indice_global") or 0),
        )
        guardados += 1
    if guardados:
        log.info("Historial municipal: %d snapshots nuevos (%s)", guardados, fecha)
    return guardados
