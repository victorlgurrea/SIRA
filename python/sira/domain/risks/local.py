"""Índice compuesto de impacto grave local (0–100 %) por ejes ponderados."""
from __future__ import annotations

from sira.config.settings import (
    RIESGO_LOCAL_BONO_CONCURRENCIA,
    RIESGO_LOCAL_CONCURRENCIA_EJES,
    RIESGO_LOCAL_CONCURRENCIA_MIN,
    RIESGO_LOCAL_PESOS,
    RIESGO_METEO_HORAS,
)
from sira.domain.risks.meteo import _nivel_indice, calcular_riesgo_meteo
from sira.domain.types import RiesgoLocal

_NIVEL_HIDRO = {
    "normal": 0,
    "fallo": 25,
    "vigilancia": 40,
    "alerta": 70,
    "critico": 90,
}
_NIVEL_HIDRO_ETQ = {
    "normal": "normal",
    "fallo": "fallo de datos",
    "vigilancia": "vigilancia",
    "alerta": "alerta",
    "critico": "crítico",
}
_NIVEL_TERMICO_ALERTA = {"rojo": 90, "naranja": 70, "amarillo": 45, "verde": 15}
_NIVEL_TERMICO_ETQ = {"rojo": "rojo", "naranja": "naranja", "amarillo": "amarillo", "verde": "verde"}
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


def _desc_item_hidro(item: dict, tipo: str) -> str:
    nom = str(item.get("nombre") or tipo).strip()
    nivel = str(item.get("nivel_riesgo") or "normal").lower()
    etiqueta = _NIVEL_HIDRO_ETQ.get(nivel, nivel)
    pts = _NIVEL_HIDRO.get(nivel, 0)
    extra = ""
    if tipo == "Embalse" and item.get("porcentaje") is not None:
        extra = f" al {item['porcentaje']}% de capacidad"
    elif tipo == "Aforo" and item.get("caudal_m3s") is not None:
        extra = f", caudal {item['caudal_m3s']} m³/s"
    return f"{tipo} «{nom}» en {etiqueta}{extra} ({pts}%)"


def _eje_hidrologia(
    resumen_emb: dict,
    resumen_afor: dict,
    alertas: list[dict],
) -> tuple[int, str]:
    emb_principales = resumen_emb.get("principales") if isinstance(resumen_emb, dict) else []
    afor_principales = resumen_afor.get("principales") if isinstance(resumen_afor, dict) else []
    candidatos: list[tuple[int, str]] = []
    for item in emb_principales if isinstance(emb_principales, list) else []:
        if isinstance(item, dict):
            pts = _NIVEL_HIDRO.get(str(item.get("nivel_riesgo") or "normal").lower(), 0)
            if pts > 0:
                candidatos.append((pts, _desc_item_hidro(item, "Embalse")))
    for item in afor_principales if isinstance(afor_principales, list) else []:
        if isinstance(item, dict):
            pts = _NIVEL_HIDRO.get(str(item.get("nivel_riesgo") or "normal").lower(), 0)
            if pts > 0:
                candidatos.append((pts, _desc_item_hidro(item, "Aforo")))

    base = max((c[0] for c in candidatos), default=0)
    aviso_hidro: dict | None = None
    for alerta in alertas:
        if not isinstance(alerta, dict):
            continue
        if str(alerta.get("fenomeno") or "").upper() in _FENOMENOS_HIDRO:
            aviso_hidro = alerta
            break

    bono = 15 if aviso_hidro else 0
    score = min(100, base + bono)

    if score <= 0:
        return 0, "Sin señales hidrológicas activas en embalses o aforos cercanos."

    partes: list[str] = []
    if candidatos:
        candidatos.sort(key=lambda c: -c[0])
        partes.append(f"Señal principal: {candidatos[0][1]}")
        if len(candidatos) > 1:
            partes.append(f"{len(candidatos) - 1} punto(s) adicional(es) en vigilancia o alerta")
    if bono and aviso_hidro:
        desc = aviso_hidro.get("fenomeno_desc") or "lluvia/tormentas"
        area = aviso_hidro.get("area_desc")
        aviso_txt = f"Aviso AEMET de {str(desc).lower()}"
        if area:
            aviso_txt += f" en {area}"
        partes.append(f"+15% por {aviso_txt}")

    return score, f"{score}%: " + ". ".join(partes) + "."


def _eje_sismico(sismos: list[dict]) -> tuple[int, str]:
    best = 0
    mejor_txt = ""
    for s in sismos:
        if not isinstance(s, dict):
            continue
        if s.get("alerta_tsunami"):
            lugar = s.get("lugar") or "evento en mar"
            return 95, f"95%: alerta de tsunami por {lugar}."
        raw = int(s.get("score_local") or s.get("score_total") or 0)
        pct = min(100, round(raw / 80 * 100))
        if pct <= best:
            continue
        best = pct
        mag = s.get("magnitud")
        dist = s.get("dist_local_km")
        lugar = s.get("lugar") or "evento sísmico"
        trozos = [lugar]
        if mag is not None:
            trozos.append(f"M{mag}")
        if dist is not None:
            trozos.append(f"a {dist} km")
        trozos.append(f"score local {raw}/80")
        mejor_txt = ", ".join(trozos)

    if best <= 0:
        return 0, "Sin actividad sísmica relevante cerca de la localidad."
    return best, f"{best}%: {mejor_txt}."


def _eje_incendio(incendios: list[dict]) -> tuple[int, str]:
    if not incendios:
        return 0, "Sin focos térmicos detectados en la zona local."
    n = len(incendios)
    max_frp = max((float(i.get("frp_mw") or 0) for i in incendios if isinstance(i, dict)), default=0.0)
    if n >= 5 or max_frp >= 100:
        pct, razon = 85, f"{n} foco(s) y FRP máximo {max_frp:.0f} MW (actividad alta)"
    elif n >= 3 or max_frp >= 50:
        pct, razon = 60, f"{n} foco(s) y FRP máximo {max_frp:.0f} MW (actividad moderada-alta)"
    else:
        pct, razon = 30, f"{n} foco(s) con FRP máximo {max_frp:.0f} MW"
    return pct, f"{pct}%: {razon}."


def _motivo_meteo(riesgo_met: dict, horas: int) -> str:
    idx = int(riesgo_met.get("indice_global") or 0)
    if idx <= 0:
        return f"Sin fenómenos meteorológicos adversos destacados en las próximas {horas} h."
    elementos = riesgo_met.get("elementos") or []
    if not elementos:
        return f"{idx}%: índice meteo según predicción horaria ({horas} h)."

    partes: list[str] = []
    for elem in elementos[:2]:
        desc = elem.get("desc") or "Fenómeno"
        nivel = elem.get("nivel_label") or "—"
        prob = elem.get("prob_principal") or "—"
        linea = f"{desc} (peligro {str(nivel).lower()}, prob. {prob})"
        area = elem.get("area")
        if area:
            linea += f" en {area}"
        param = elem.get("parametro")
        if param:
            linea += f" · {param}"
        partes.append(linea)
    extra = f" y {len(elementos) - 2} señal(es) más" if len(elementos) > 2 else ""
    return f"{idx}%: " + "; ".join(partes) + extra + "."


def _eje_termico(alertas: list[dict], termico_ccaa: dict | None, provincia_id: str | None) -> tuple[int, str]:
    score = 0
    aviso_termico: dict | None = None
    for alerta in alertas:
        if not isinstance(alerta, dict):
            continue
        if str(alerta.get("fenomeno") or "").upper() not in ("AT", "BT"):
            continue
        nivel = str(alerta.get("level") or "amarillo").lower()
        pts = _NIVEL_TERMICO_ALERTA.get(nivel, 30)
        if pts >= score:
            score = pts
            aviso_termico = alerta

    tmax_txt = ""
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
            prov = row.get("provincia") or f"provincia {pid}"
            if t >= 42:
                score = max(score, 90)
                tmax_txt = f"máx. prevista {t:.0f}°C en {prov} (≥42°C → 90%)"
            elif t >= 38:
                score = max(score, 70)
                tmax_txt = f"máx. prevista {t:.0f}°C en {prov} (≥38°C → 70%)"
            elif t >= 35:
                score = max(score, 45)
                tmax_txt = f"máx. prevista {t:.0f}°C en {prov} (≥35°C → 45%)"
            break

    if score <= 0:
        return 0, "Sin avisos térmicos ni picos de temperatura destacados en la provincia."

    partes: list[str] = []
    if aviso_termico:
        fen = str(aviso_termico.get("fenomeno") or "AT").upper()
        tipo = "calor extremo" if fen == "AT" else "temperaturas mínimas"
        nivel = str(aviso_termico.get("level") or "amarillo").lower()
        etiqueta = _NIVEL_TERMICO_ETQ.get(nivel, nivel)
        pts = _NIVEL_TERMICO_ALERTA.get(nivel, 30)
        area = aviso_termico.get("area_desc")
        aviso_txt = f"Aviso AEMET {etiqueta} por {tipo} ({pts}%)"
        if area:
            aviso_txt += f" en {area}"
        partes.append(aviso_txt)
    if tmax_txt:
        partes.append(tmax_txt)

    return score, f"{score}%: " + ". ".join(partes) + "."


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
) -> RiesgoLocal:
    """Combina señales activas locales en un índice 0–100 con desglose por eje."""
    h = max(1, int(horas_meteo or RIESGO_METEO_HORAS))
    alertas = alertas_meteo or []
    riesgo_met = calcular_riesgo_meteo(alertas, meteo, horas=h)

    hidro_pct, hidro_motivo = _eje_hidrologia(resumen_embalses, resumen_aforos, alertas)
    sismo_pct, sismo_motivo = _eje_sismico(sismos or [])
    incendio_pct, incendio_motivo = _eje_incendio(incendios_local or [])
    termico_pct, termico_motivo = _eje_termico(alertas, termico_ccaa, provincia_id)
    meteo_pct = int(riesgo_met.get("indice_global") or 0)
    meteo_motivo = _motivo_meteo(riesgo_met, h)

    ejes_val = {
        "meteo": meteo_pct,
        "hidrologia": hidro_pct,
        "sismico": sismo_pct,
        "incendio": incendio_pct,
        "termico": termico_pct,
    }
    ejes_motivo = {
        "meteo": meteo_motivo,
        "hidrologia": hidro_motivo,
        "sismico": sismo_motivo,
        "incendio": incendio_motivo,
        "termico": termico_motivo,
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
            "motivo": ejes_motivo.get(clave) or "",
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
