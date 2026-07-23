"""Riesgo meteorológico adverso: probabilidad AEMET + nivel de peligro + índice opcional."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sira.domain.risks.presentacion import fmt_alerta_detalle, icono_alerta
from sira.config.settings import RIESGO_METEO_HORAS

_MADRID = ZoneInfo("Europe/Madrid")
_LEVEL_WEIGHT = {"rojo": 100, "naranja": 68, "amarillo": 38, "verde": 10}
_NIVEL_AEMET = {"amarillo": "AMARILLO", "naranja": "NARANJA", "rojo": "ROJO", "verde": "VERDE"}
_NIVEL_SIGNIFICADO = {
    "rojo": "Rojo: riesgo extremo; tome medidas excepcionales y siga instrucciones oficiales.",
    "naranja": "Naranja: riesgo importante; evite desplazamientos y actividades al aire libre.",
    "amarillo": "Amarillo: riesgo bajo o moderado; extreme precaución y esté atento a la evolución.",
    "verde": "Verde: sin peligro significativo.",
}


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


def _serie_proximas_horas(serie: list[dict], horas: int) -> list[dict]:
    """Ventana futura desde ahora (evita horas pasadas en series AEMET desde medianoche)."""
    if not serie:
        return []
    ahora = datetime.now(_MADRID)
    futuras: list[dict] = []
    for row in serie:
        raw = str(row.get("timestamp") or "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_MADRID)
            else:
                dt = dt.astimezone(_MADRID)
        except ValueError:
            continue
        if dt >= ahora.replace(minute=0, second=0, microsecond=0):
            futuras.append(row)
        if len(futuras) >= horas:
            break
    return futuras if futuras else serie[:horas]


def _indice_precip(serie: list[dict], horas: int) -> tuple[int, dict]:
    ventana = _serie_proximas_horas(serie, horas)
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


def _explicacion_alerta(elem: dict) -> str:
    """Texto plano: qué es el aviso y qué significa su nivel AEMET."""
    desc = elem.get("desc") or "Fenómeno adverso"
    nivel = str(elem.get("nivel_peligro") or "").lower()
    significado = _NIVEL_SIGNIFICADO.get(nivel)
    prob = elem.get("prob_principal") or "—"
    partes = [f"{desc}: probabilidad AEMET {prob}"]
    area = elem.get("area")
    if area:
        partes.append(f"zona {area}")
    param = elem.get("parametro")
    if param:
        partes.append(str(param))
    base = ". ".join(partes) + "."
    if significado:
        return f"{base} {significado}"
    return base


def _motivo_indice_combinado(
    indice: int,
    nivel_global: str,
    elementos: list[dict],
    *,
    horas: int,
    idx_cap: int,
    idx_precip: int,
    tiene_pr: bool,
) -> str:
    """Explica por qué sale el índice combinado y qué implican las alertas activas."""
    if indice <= 0 and not elementos:
        return (
            f"Índice 0/100: sin avisos AEMET ni precipitación relevante en las próximas {horas} h. "
            "Los colores AEMET: amarillo = precaución; naranja = riesgo importante; rojo = riesgo extremo."
        )

    partes: list[str] = [
        f"Índice combinado {indice}/100 ({nivel_global}): pondera el nivel de peligro AEMET "
        f"por la probabilidad del aviso (amarillo≈38, naranja≈68, rojo≈100 a probabilidad 100%)."
    ]
    if tiene_pr and idx_cap:
        partes.append(f"Hay aviso de lluvia/tormenta: se usa el índice CAP ({idx_cap}).")
    elif idx_cap and idx_precip and idx_precip > idx_cap:
        partes.append(
            f"Sin aviso de lluvia: se toma el máximo entre avisos CAP ({idx_cap}) "
            f"y predicción horaria de precipitación ({idx_precip})."
        )
    elif idx_cap:
        partes.append(f"Derivado del aviso AEMET con mayor índice ({idx_cap}).")
    elif idx_precip:
        partes.append(f"Derivado de la predicción horaria de precipitación ({idx_precip}).")

    if elementos:
        partes.append("Alertas activas:")
        for elem in elementos[:3]:
            partes.append(_explicacion_alerta(elem))
        if len(elementos) > 3:
            partes.append(f"… y {len(elementos) - 3} aviso(s) más.")
    return " ".join(partes)


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
    if tiene_pr:
        indice = idx_cap if elementos else 0
    else:
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
        texto = f"Riesgo en {h} h: {nombres}."

    motivo_indice = _motivo_indice_combinado(
        indice,
        nivel_global,
        elementos,
        horas=h,
        idx_cap=idx_cap,
        idx_precip=idx_precip,
        tiene_pr=tiene_pr,
    )

    for elem in elementos:
        elem["motivo"] = _explicacion_alerta(elem)

    return {
        "horas": h,
        "elementos": elementos,
        "indice_global": indice,
        "nivel_global": nivel_global,
        "precip_max_pct": precip.get("precip_max_pct"),
        "precip_acum_mm": precip.get("precip_acum_mm"),
        "fuente_principal": fuente,
        "texto": texto,
        "indice": indice,
        "nivel": nivel_global,
        "fenomenos": elementos,
        "motivo_indice": motivo_indice,
    }
