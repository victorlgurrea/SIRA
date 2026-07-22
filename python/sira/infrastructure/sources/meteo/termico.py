"""Resumen térmico por provincia/CCAA para el mapa del dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
from zoneinfo import ZoneInfo

from sira.infrastructure.geo.es import CCAA_NOMBRES, ccaa_de_provincia, municipios, provincias

_MADRID = ZoneInfo("Europe/Madrid")


def _parse_ts(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_MADRID)
    return dt.astimezone(_MADRID)


def pico_termico_24h(meteo: dict | None, *, now: datetime | None = None) -> dict:
    """Temperatura máxima y sensación asociada en las próximas 24 h."""
    serie = meteo.get("serie_horaria") if isinstance(meteo, dict) else []
    if not isinstance(serie, list) or not serie:
        return {"temp_max_c": None, "sensacion_max_c": None, "hora_pico": None}

    ahora = now.astimezone(_MADRID) if now else datetime.now(_MADRID)
    inicio = ahora.replace(minute=0, second=0, microsecond=0)
    fin = inicio + timedelta(hours=24)

    mejor: dict | None = None
    for row in serie:
        if not isinstance(row, dict):
            continue
        dt = _parse_ts(row.get("timestamp"))
        if not dt or dt < inicio or dt > fin:
            continue
        temp = row.get("temp_c")
        try:
            temp_val = round(float(temp), 1) if temp is not None else None
        except (TypeError, ValueError):
            temp_val = None
        if temp_val is None:
            continue
        sens = row.get("sensacion_c")
        try:
            sens_val = round(float(sens), 1) if sens is not None else None
        except (TypeError, ValueError):
            sens_val = None
        cand = {
            "temp_max_c": temp_val,
            "sensacion_max_c": sens_val,
            "hora_pico": dt.isoformat(),
        }
        if mejor is None or temp_val > mejor["temp_max_c"]:
            mejor = cand

    return mejor or {"temp_max_c": None, "sensacion_max_c": None, "hora_pico": None}


def construir_termico_ccaa(
    fetch_meteo: Callable[[str, str | None], dict],
    *,
    now: datetime | None = None,
    max_workers: int = 6,
) -> dict:
    """Precalcula un resumen térmico compacto por provincia para todas las CCAA."""
    tareas: list[tuple[str, str, str, str | None, str, str]] = []
    por_ccaa: dict[str, dict] = {}

    for prov in provincias():
        pid = str(prov.get("id") or "").zfill(2)
        if not pid:
            continue
        munis = municipios(pid)
        if not munis:
            continue
        municipio = munis[0]
        mid = str(municipio.get("id") or "").zfill(5)
        if not mid:
            continue
        ccaa_id = ccaa_de_provincia(pid)
        ccaa = CCAA_NOMBRES.get(ccaa_id or "", ccaa_id or "")
        prov_nombre = str(prov.get("nombre") or pid)
        muni_nombre = str(municipio.get("nombre") or prov_nombre)
        tareas.append((pid, prov_nombre, mid, ccaa_id, ccaa, muni_nombre))

    filas: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as pool:
        future_map = {
            pool.submit(fetch_meteo, mid, muni_nombre): (pid, prov_nombre, mid, ccaa_id, ccaa, muni_nombre)
            for pid, prov_nombre, mid, ccaa_id, ccaa, muni_nombre in tareas
        }
        for future in as_completed(future_map):
            pid, prov_nombre, mid, ccaa_id, ccaa, muni_nombre = future_map[future]
            met = future.result() or {}
            pico = pico_termico_24h(met, now=now)
            fila = {
                "provincia_id": pid,
                "provincia": prov_nombre,
                "municipio_ref_id": mid,
                "municipio_ref": muni_nombre,
                "ccaa_id": ccaa_id,
                "ccaa": ccaa,
                "fuente": met.get("fuente") or "—",
                **pico,
            }
            filas.append(fila)
            if not ccaa_id:
                continue
            agg = por_ccaa.setdefault(
                ccaa_id,
                {
                    "ccaa_id": ccaa_id,
                    "ccaa": ccaa,
                    "provincias": [],
                    "temp_max_c": None,
                },
            )
            agg["provincias"].append(pid)
            temp = fila.get("temp_max_c")
            if temp is not None and (agg["temp_max_c"] is None or temp > agg["temp_max_c"]):
                agg["temp_max_c"] = temp

    filas.sort(key=lambda x: (str(x.get("ccaa_id") or ""), str(x.get("provincia_id") or "")))
    for agg in por_ccaa.values():
        agg["provincias"].sort()

    ts = now.astimezone(_MADRID) if now else datetime.now(_MADRID)
    return {
        "generado_en": ts.isoformat(),
        "provincias": filas,
        "ccaa": [por_ccaa[k] for k in sorted(por_ccaa)],
    }
