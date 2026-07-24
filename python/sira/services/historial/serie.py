"""Serie de evolución municipal: sísmico desde USGS + índices desde snapshots SQLite."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sira.config.settings import HISTORIAL_DIAS_DEFAULT
from sira.domain.seismic.sismos import enriquecer_local
from sira.infrastructure.geo.es import coords_observacion
from sira.infrastructure.persistence.sqlite import get_historial_municipio


def _fecha_sismo(ts: str | None) -> str | None:
    if not ts:
        return None
    raw = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.date().isoformat()


def serie_evolucion_municipio(
    municipio_id: str,
    dashboard: dict,
    *,
    dias: int | None = None,
) -> list[dict]:
    """Un punto por día en los últimos ``dias`` días.

    - ``score_sismo_max``: máximo score local ese día (sismos USGS del dashboard).
    - ``indice_riesgo_meteo`` / ``indice_impacto_local``: snapshots diarios en SQLite (si existen).
    """
    mid = str(municipio_id).zfill(5)
    n = max(1, min(int(dias or HISTORIAL_DIAS_DEFAULT), 365))
    lat, lon, _ = coords_observacion(mid, None)

    por_dia: dict[str, int] = defaultdict(int)
    for s in dashboard.get("sismos") or []:
        if not isinstance(s, dict):
            continue
        dia = _fecha_sismo(s.get("timestamp"))
        if not dia:
            continue
        loc = enriquecer_local(s, lat, lon)
        score = int(loc.get("score_local") or 0)
        if score > por_dia[dia]:
            por_dia[dia] = score

    db_por_fecha = {r["fecha"]: r for r in get_historial_municipio(mid, n)}
    hoy = date.today()
    serie: list[dict] = []
    for offset in range(n - 1, -1, -1):
        fecha = (hoy - timedelta(days=offset)).isoformat()
        snap = db_por_fecha.get(fecha) or {}
        score_usgs = por_dia.get(fecha, 0)
        score_snap = int(snap.get("score_sismo_max") or 0)
        serie.append({
            "fecha": fecha,
            "municipio_id": mid,
            "score_sismo_max": max(score_usgs, score_snap),
            "indice_riesgo_meteo": snap.get("indice_riesgo_meteo"),
            "indice_impacto_local": snap.get("indice_impacto_local"),
        })
    return serie


def serie_tiene_datos(serie: list[dict]) -> bool:
    if not serie:
        return False
    if any(int(r.get("score_sismo_max") or 0) > 0 for r in serie):
        return True
    if any(r.get("indice_riesgo_meteo") is not None for r in serie):
        return True
    if any(r.get("indice_impacto_local") is not None for r in serie):
        return True
    return False
