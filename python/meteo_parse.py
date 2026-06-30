"""Utilidades compartidas de parseo meteorológico (ingesta + meteo_live)."""
from __future__ import annotations

VACIO_METEO = {"fuente": "—", "serie_horaria": [], "resumen": {}}


def hourly(data: dict, mapping: dict[str, str]) -> list[dict]:
    h = data.get("hourly", {})
    times = h.get("time", [])
    return [
        {"timestamp": t, **{out: h.get(src, [None] * len(times))[i] for out, src in mapping.items()}}
        for i, t in enumerate(times)
    ]


def aemet_val(obj) -> str | int | float | None:
    return obj.get("value") if isinstance(obj, dict) else obj


def num(val, default: float = 0.0) -> float:
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("", "ip", "0"):
        return default
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return default


def resumen_lluvia(serie: list[dict]) -> dict:
    s24 = serie[:24]
    probs = [x["prob_precip_pct"] for x in s24 if x.get("prob_precip_pct") is not None]
    return {
        "precip_prox_24h_mm": round(sum(x.get("precip_mm", 0) for x in s24), 1),
        "prob_max_pct": max(probs, default=0),
        "prob_actual_pct": s24[0].get("prob_precip_pct") if s24 else None,
    }


def pack_meteo(fuente: str, municipio: str, serie: list[dict]) -> dict:
    serie = serie[:48]
    return {"fuente": fuente, "municipio": municipio, "serie_horaria": serie, "resumen": resumen_lluvia(serie)}


def parse_aemet(data: dict | list) -> list[dict]:
    item = (data[0] if isinstance(data, list) else data) or {}
    serie = []
    for dia in item.get("prediccion", {}).get("dia", []):
        fecha = dia.get("fecha", "")
        for h in dia.get("hora", []):
            periodo = str(h.get("periodo", ""))
            ts = f"{fecha}T{periodo.zfill(2)}:00" if periodo.isdigit() else fecha
            prob = aemet_val(h.get("probPrecipitacion"))
            serie.append({
                "timestamp": ts,
                "precip_mm": num(aemet_val(h.get("precipitacion"))),
                "prob_precip_pct": int(prob) if prob is not None and str(prob).strip().isdigit() else None,
            })
    return serie
