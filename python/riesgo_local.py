"""Índice compuesto de impacto grave local (0–100 %) por ejes ponderados."""
from __future__ import annotations

from config import (
    RIESGO_LOCAL_BONO_CONCURRENCIA,
    RIESGO_LOCAL_CONCURRENCIA_EJES,
    RIESGO_LOCAL_CONCURRENCIA_MIN,
    RIESGO_LOCAL_PESOS,
    RIESGO_METEO_HORAS,
)
from riesgo_meteo import _nivel_indice, calcular_riesgo_meteo

_NIVEL_HIDRO = {
    "normal": 0,
    "fallo": 25,
    "vigilancia": 40,
    "alerta": 70,
    "critico": 90,
}
_NIVEL_TERMICO_ALERTA = {"rojo": 90, "naranja": 70, "amarillo": 45, "verde": 15}
_EJE_NOMBRES = {
    "meteo": "Meteo",
    "hidrologia": "Hidrología",
    "sismico": "Sísmico",
    "incendio": "Incendios",
    "termico": "Calor",
}
_FENOMENOS_HIDRO = frozenset({"PR", "TO"})


def _max_nivel_hidro(items: list[dict]) -> int:
    best = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        nivel = str(item.get("nivel_riesgo") or "normal").lower()
        best = max(best, _NIVEL_HIDRO.get(nivel, 0))
    return best


def _eje_hidrologia(
    resumen_emb: dict,
    resumen_afor: dict,
    alertas: list[dict],
) -> int:
    emb_principales = resumen_emb.get("principales") if isinstance(resumen_emb, dict) else []
    afor_principales = resumen_afor.get("principales") if isinstance(resumen_afor, dict) else []
    score = max(
        _max_nivel_hidro(emb_principales if isinstance(emb_principales, list) else []),
        _max_nivel_hidro(afor_principales if isinstance(afor_principales, list) else []),
    )
    if any(str(a.get("fenomeno") or "").upper() in _FENOMENOS_HIDRO for a in alertas if isinstance(a, dict)):
        score = min(100, score + 15)
    return score


def _eje_sismico(sismos: list[dict]) -> int:
    best = 0
    for s in sismos:
        if not isinstance(s, dict):
            continue
        if s.get("alerta_tsunami"):
            return 95
        raw = int(s.get("score_local") or s.get("score_total") or 0)
        best = max(best, min(100, round(raw / 80 * 100)))
    return best


def _eje_incendio(incendios: list[dict]) -> int:
    if not incendios:
        return 0
    n = len(incendios)
    max_frp = max((float(i.get("frp_mw") or 0) for i in incendios if isinstance(i, dict)), default=0.0)
    if n >= 5 or max_frp >= 100:
        return 85
    if n >= 3 or max_frp >= 50:
        return 60
    if n >= 1:
        return 30
    return 0


def _eje_termico(alertas: list[dict], termico_ccaa: dict | None, provincia_id: str | None) -> int:
    score = 0
    for alerta in alertas:
        if not isinstance(alerta, dict):
            continue
        if str(alerta.get("fenomeno") or "").upper() not in ("AT", "BT"):
            continue
        nivel = str(alerta.get("level") or "amarillo").lower()
        score = max(score, _NIVEL_TERMICO_ALERTA.get(nivel, 30))

    pid = str(provincia_id or "").zfill(2)
    if pid and isinstance(termico_ccaa, dict):
        for row in termico_ccaa.get("provincias") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("provincia_id") or "").zfill(2) != pid:
                continue
            tmax = row.get("temp_max_c")
            if tmax is None:
                break
            try:
                t = float(tmax)
            except (TypeError, ValueError):
                break
            if t >= 42:
                score = max(score, 90)
            elif t >= 38:
                score = max(score, 70)
            elif t >= 35:
                score = max(score, 45)
            break
    return score


def calcular_riesgo_local(
    *,
    alertas_meteo: list[dict],
    meteo: dict | None,
    sismos: list[dict],
    incendios_local: list[dict],
    resumen_embalses: dict,
    resumen_aforos: dict,
    termico_ccaa: dict | None = None,
    provincia_id: str | None = None,
    horas_meteo: int | None = None,
) -> dict:
    """Combina señales activas locales en un índice 0–100 con desglose por eje."""
    h = max(1, int(horas_meteo or RIESGO_METEO_HORAS))
    alertas = alertas_meteo or []
    riesgo_met = calcular_riesgo_meteo(alertas, meteo, horas=h)

    ejes_val = {
        "meteo": int(riesgo_met.get("indice_global") or 0),
        "hidrologia": _eje_hidrologia(resumen_embalses, resumen_aforos, alertas),
        "sismico": _eje_sismico(sismos or []),
        "incendio": _eje_incendio(incendios_local or []),
        "termico": _eje_termico(alertas, termico_ccaa, provincia_id),
    }

    pesos = RIESGO_LOCAL_PESOS
    peso_sum = sum(pesos.values()) or 1.0
    weighted = sum(pesos[k] * ejes_val[k] for k in pesos) / peso_sum

    umbral = RIESGO_LOCAL_CONCURRENCIA_EJES
    n_altos = sum(1 for v in ejes_val.values() if v >= umbral)
    concurrencia = n_altos >= RIESGO_LOCAL_CONCURRENCIA_MIN
    if concurrencia:
        weighted = min(100.0, weighted * RIESGO_LOCAL_BONO_CONCURRENCIA)

    indice = int(round(min(100, max(0, weighted))))
    nivel = _nivel_indice(indice)

    ejes_out: list[dict] = []
    for clave, nombre in _EJE_NOMBRES.items():
        pct = ejes_val[clave]
        peso_norm = round(pesos[clave] / peso_sum * 100)
        contrib = round(pesos[clave] / peso_sum * pct)
        ejes_out.append({
            "id": clave,
            "nombre": nombre,
            "pct": pct,
            "peso_pct": peso_norm,
            "contrib": contrib,
        })
    ejes_out.sort(key=lambda e: e["contrib"], reverse=True)

    activos = [e["nombre"].lower() for e in ejes_out if e["pct"] >= 20]
    if not activos:
        texto = f"Sin señales de impacto grave destacadas (horizonte meteo {h} h)."
    elif concurrencia:
        texto = f"Varias amenazas activas: {', '.join(activos[:4])}."
    else:
        texto = f"Principal: {activos[0]}."
        if len(activos) > 1:
            texto += f" También: {', '.join(activos[1:3])}."

    return {
        "indice": indice,
        "nivel": nivel,
        "ejes": ejes_out,
        "concurrencia": concurrencia,
        "horas_meteo": h,
        "texto": texto,
        "riesgo_meteo": riesgo_met,
    }
