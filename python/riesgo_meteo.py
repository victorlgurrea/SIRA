"""Riesgo meteorológico adverso: probabilidad AEMET + nivel de peligro + índice opcional."""
from __future__ import annotations

import re

from aemet_alerts import fmt_alerta_detalle, icono_alerta
from config import RIESGO_METEO_HORAS

_LEVEL_WEIGHT = {"rojo": 100, "naranja": 68, "amarillo": 38, "verde": 10}
_NIVEL_AEMET = {"amarillo": "AMARILLO", "naranja": "NARANJA", "rojo": "ROJO", "verde": "VERDE"}


def _parse_prob_aemet(prob: str | None) -> tuple[int, int, str]:
    if not prob:
        return 40, 70, "40%-70%"
    raw = str(prob).strip()
    low = raw.lower().replace(" ", "")
    if "mayor" in low or low.startswith(">") or "másde70" in low.replace("á", "a"):
        return 70, 95, ">70%"
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    if len(nums) >= 2:
        a, b = sorted(nums[:2])
        return a, b, f"{a}%-{b}%"
    if len(nums) == 1:
        n = nums[0]
        return n, min(100, n + 15), f"~{n}%"
    return 40, 70, raw


def _indice_alerta(alerta: dict) -> int:
    level = str(alerta.get("level") or "amarillo").lower()
    pmin, pmax, _ = _parse_prob_aemet(alerta.get("probabilidad"))
    prob_mid = (pmin + pmax) / 2
    return int(_LEVEL_WEIGHT.get(level, 30) * prob_mid / 100)


def _indice_precip(serie: list[dict], horas: int) -> tuple[int, dict]:
    ventana = serie[:horas] if serie else []
    probs = [int(x["prob_precip_pct"]) for x in ventana if x.get("prob_precip_pct") is not None]
    precips = [float(x.get("precip_mm") or 0) for x in ventana]
    max_prob = max(probs, default=0)
    acum = round(sum(precips), 1)
    idx = 0
    if max_prob >= 80:
        idx = 58
    elif max_prob >= 60:
        idx = 42
    elif max_prob >= 40:
        idx = 26
    if acum >= 30:
        idx = max(idx, 52)
    elif acum >= 15:
        idx = max(idx, 36)
    return idx, {"precip_max_pct": max_prob or None, "precip_acum_mm": acum}


def _nivel_indice(idx: int) -> str:
    if idx >= 75:
        return "MUY ALTO"
    if idx >= 50:
        return "ALTO"
    if idx >= 28:
        return "MODERADO"
    if idx >= 12:
        return "BAJO"
    return "MÍNIMO"


def _nivel_peligro_precip(max_prob: int, acum: float) -> str | None:
    if max_prob >= 70 or acum >= 25:
        return "naranja"
    if max_prob >= 40 or acum >= 12:
        return "amarillo"
    if max_prob > 0 or acum > 0:
        return None
    return None


def _linea_tiempo_actual(fenomeno: str, resumen: dict) -> str | None:
    if not resumen:
        return None
    fen = str(fenomeno or "").upper()
    if fen in ("AT", "BT"):
        temp = resumen.get("temp_c")
        if temp is not None:
            return f"Ahora: {temp} °C"
    if fen == "VI":
        vel = resumen.get("viento_vel")
        unidad = resumen.get("viento_unidad") or "m/s"
        if vel is not None:
            dir_txt = resumen.get("viento_dir_texto")
            if not dir_txt and resumen.get("viento_dir_grados") is not None:
                g = float(resumen["viento_dir_grados"]) % 360
                puntos = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
                dir_txt = f"{g:.0f}° ({puntos[int((g + 22.5) / 45) % 8]})"
            base = f"Ahora: {vel} {unidad}"
            return f"{base} · {dir_txt}" if dir_txt else base
    return None


def _elemento_alerta(alerta: dict, resumen: dict | None = None) -> dict:
    nivel = str(alerta.get("level") or "amarillo").lower()
    fen = str(alerta.get("fenomeno") or "").upper()
    _, _, prob = _parse_prob_aemet(alerta.get("probabilidad"))
    parametro = fmt_alerta_detalle(alerta)
    return {
        "fenomeno": fen,
        "desc": alerta.get("fenomeno_desc") or "Fenómeno adverso",
        "icon": icono_alerta(alerta),
        "prob_principal": prob,
        "prob_etiqueta": "Probabilidad AEMET",
        "parametro": parametro if parametro and parametro != "Sin detalle" else None,
        "tiempo_actual": _linea_tiempo_actual(fen, resumen or {}),
        "area": alerta.get("area_desc"),
        "nivel_peligro": nivel,
        "nivel_label": _NIVEL_AEMET.get(nivel, nivel.upper()),
        "nivel_etiqueta": "Nivel de peligro",
        "fuente": "AEMET Meteoalerta",
        "indice": _indice_alerta(alerta),
    }


def _elemento_precip(precip: dict, fuente: str, horas: int, *, indice: int = 0) -> dict | None:
    max_prob = int(precip.get("precip_max_pct") or 0)
    acum = float(precip.get("precip_acum_mm") or 0)
    if max_prob <= 0 and acum <= 0:
        return None
    nivel = _nivel_peligro_precip(max_prob, acum)
    return {
        "fenomeno": "PR",
        "desc": "Lluvia",
        "icon": "🌧️",
        "prob_principal": f"{max_prob}%",
        "prob_etiqueta": f"Prob. máx. predicción ({horas} h)",
        "parametro": f"Acumulado: {acum} mm",
        "tiempo_actual": None,
        "nivel_peligro": nivel,
        "nivel_label": _NIVEL_AEMET.get(nivel, "—") if nivel else "—",
        "nivel_etiqueta": "Nivel estimado",
        "fuente": fuente,
        "indice": indice,
    }


def calcular_riesgo_meteo(
    alertas: list[dict],
    meteo: dict | None,
    *,
    horas: int | None = None,
) -> dict:
    """Perspectiva de riesgo: prob. AEMET (principal), peligro (secundario), índice (opcional)."""
    h = max(1, int(horas or RIESGO_METEO_HORAS))
    meteo = meteo or {}
    serie = meteo.get("serie_horaria") if isinstance(meteo.get("serie_horaria"), list) else []
    resumen = meteo.get("resumen") if isinstance(meteo.get("resumen"), dict) else {}

    elementos = [_elemento_alerta(a, resumen) for a in alertas if isinstance(a, dict)]
    tiene_pr = any(e.get("fenomeno") == "PR" for e in elementos)

    idx_precip, precip = _indice_precip(serie, h)
    if not tiene_pr:
        elem_pr = _elemento_precip(precip, str(meteo.get("fuente") or "Predicción horaria"), h, indice=idx_precip)
        if elem_pr and (idx_precip >= 26 or not elementos):
            elementos.append(elem_pr)

    elementos.sort(key=lambda e: e.get("indice", 0), reverse=True)

    idx_cap = max((e["indice"] for e in elementos if e.get("fuente") == "AEMET Meteoalerta"), default=0)
    indice = max(idx_cap, idx_precip) if elementos else idx_precip
    nivel_global = _nivel_indice(indice)

    if elementos:
        fuente = elementos[0].get("fuente", "AEMET Meteoalerta")
    else:
        fuente = meteo.get("fuente") or "—"

    if not elementos:
        texto = f"Sin fenómenos adversos destacados en las próximas {h} h."
    else:
        nombres = ", ".join(e["desc"].lower() for e in elementos[:3])
        texto = f"Perspectiva adversa en {h} h: {nombres}."

    return {
        "horas": h,
        "elementos": elementos,
        "indice_global": indice,
        "nivel_global": nivel_global,
        "precip_max_pct": precip.get("precip_max_pct"),
        "precip_acum_mm": precip.get("precip_acum_mm"),
        "fuente_principal": fuente,
        "texto": texto,
        # Compatibilidad con código previo
        "indice": indice,
        "nivel": nivel_global,
        "fenomenos": elementos,
    }
