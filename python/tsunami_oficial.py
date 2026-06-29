"""Boletines NOAA tsunami.gov + zona costera · sin inventar alturas."""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any

from config import TSUNAMI_GOV_CACHE_SEC, TSUNAMI_GOV_FEED_URL
from core import fetch_text
from geo_es import provincia_nombre_de_municipio
from sismos import distancia_km

log = logging.getLogger(__name__)

IGN_TSUNAMI_URL = "https://www.ign.es/web/ign/portal/tsunami"
DGPC_URL = "https://www.dsn.gob.es/es/que-hacemos/proteccion-civil"

_ZONAS_COSTA: tuple[dict[str, Any], ...] = (
    {"keywords": ("valencia", "castellon", "castello", "alicante", "alacant"), "nombre": "Mediterráneo — Valencia y Murcia", "aemet": "Costa de Valencia y Murcia"},
    {"keywords": ("murcia", "cartagena", "lorca"), "nombre": "Levante — Murcia", "aemet": "Costa de Valencia y Murcia"},
    {"keywords": ("balear", "mallorca", "menorca", "ibiza", "illes"), "nombre": "Illes Balears", "aemet": "Costa de Illes Balears"},
    {"keywords": ("catalu", "catalun", "barcelona", "tarragona", "girona"), "nombre": "Mediterráneo — Cataluña", "aemet": "Costa de Cataluña"},
    {"keywords": ("andaluc", "cadiz", "huelva", "malaga", "almeria", "granada"), "nombre": "Andalucía", "aemet": "Costa de Andalucía"},
    {"keywords": ("galicia", "coruna", "pontevedra"), "nombre": "Atlántico — Galicia", "aemet": "Costa de Galicia"},
    {"keywords": ("cantabria", "asturias", "cantabrico", "bizkaia", "gipuzkoa", "vasco"), "nombre": "Cantábrico", "aemet": "Costa de Asturias, Cantabria y País Vasco"},
    {"keywords": ("canarias", "tenerife", "palmas"), "nombre": "Canarias", "aemet": "Costa de las Islas Canarias"},
    {"keywords": ("ceuta",), "nombre": "Ceuta", "aemet": "Ceuta"},
    {"keywords": ("melilla",), "nombre": "Melilla", "aemet": "Melilla"},
)

_feed_cache: dict[str, Any] = {"ts": 0.0, "items": []}


def _norm(value: str | None) -> str:
    if not value:
        return ""
    txt = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", txt).strip().lower()


def zona_costera_usuario(
    lat: float,
    lon: float,
    municipio_id: str | None = None,
) -> dict[str, str]:
    """Zona litoral orientativa para el usuario (AEMET / IGN)."""
    candidatos = [_norm(provincia_nombre_de_municipio(municipio_id))]
    for zona in _ZONAS_COSTA:
        if any(k in c for c in candidatos for k in zona["keywords"] if c):
            return {"nombre": zona["nombre"], "aemet": zona["aemet"]}
    # Fallback por proximidad a segmentos conocidos
    if 38.0 <= lat <= 40.8 and -1.0 <= lon <= 0.8:
        return {"nombre": "Mediterráneo — Valencia y Murcia", "aemet": "Costa de Valencia y Murcia"}
    if 39.0 <= lat <= 40.5 and 2.0 <= lon <= 3.5:
        return {"nombre": "Illes Balears", "aemet": "Costa de Illes Balears"}
    if 40.0 <= lat <= 42.5 and 0.5 <= lon <= 3.5:
        return {"nombre": "Mediterráneo — Cataluña", "aemet": "Costa de Cataluña"}
    return {"nombre": "Costa española", "aemet": "Predicción marítima AEMET"}


def _limpiar_feed_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("("):
        text = text[1:]
    if text.endswith(")"):
        text = text[:-1]
    text = re.sub(r",\s*]", "]", text)
    return re.sub(r",\s*}", "}", text)


def _parse_feed(raw: str) -> list[dict]:
    text = _limpiar_feed_json(raw)
    start = text.find('{"title"')
    if start < 0:
        return []
    obj, _ = json.JSONDecoder().raw_decode(text, start)
    items = obj.get("items") if isinstance(obj, dict) else None
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _cargar_eventos_gov() -> list[dict]:
    now = time.monotonic()
    if now - float(_feed_cache.get("ts") or 0) < TSUNAMI_GOV_CACHE_SEC:
        return list(_feed_cache.get("items") or [])
    try:
        raw = fetch_text(TSUNAMI_GOV_FEED_URL)
        items = _parse_feed(raw)
        _feed_cache["ts"] = now
        _feed_cache["items"] = items
        log.info("tsunami.gov: %d eventos en feed", len(items))
    except Exception as exc:  # noqa: BLE001
        log.warning("tsunami.gov: %s", exc)
        items = list(_feed_cache.get("items") or [])
    return items


def _parse_tiempo(value: str | None) -> datetime | None:
    if not value:
        return None
    txt = str(value).strip().replace(" UTC", "Z").replace(" ", "T")
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _a_metros(valor: Any, unidades: str | None) -> float | None:
    if valor is None:
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    u = _norm(unidades)
    if "feet" in u or u == "ft":
        return round(v * 0.3048, 3)
    if "centimeter" in u or u == "cm":
        return round(v / 100.0, 3)
    if "meter" in u or u == "m":
        return round(v, 3)
    return round(v * 0.3048, 3) if "foot" in u else round(v, 3)


def _emparejar_evento(sismo: dict, eventos: list[dict]) -> dict | None:
    try:
        slat, slon = float(sismo["lat"]), float(sismo["lon"])
        smag = float(sismo.get("magnitud") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    sts = _parse_tiempo(str(sismo.get("timestamp") or ""))
    mejor: dict | None = None
    mejor_score = 9999.0
    for ev in eventos:
        try:
            elat = float(ev.get("eventLat"))
            elon = float(ev.get("eventLon"))
            emag = float(ev.get("eventMagnitude") or 0)
        except (TypeError, ValueError):
            continue
        d_km = distancia_km(slat, slon, elat, elon)
        if d_km > 350:
            continue
        if abs(smag - emag) > 0.6:
            continue
        ets = _parse_tiempo(str(ev.get("originTime") or ev.get("bulletinIssueTime") or ""))
        delta_h = 48.0
        if sts and ets:
            delta_h = abs((sts - ets).total_seconds()) / 3600.0
            if delta_h > 36:
                continue
        score = d_km + delta_h * 5.0
        if score < mejor_score:
            mejor_score = score
            mejor = ev
    return mejor


def _texto_segmentos(evento: dict, zona: dict[str, str]) -> str:
    zonas_txt = _norm(zona.get("nombre")) + " " + _norm(zona.get("aemet"))
    hits: list[str] = []
    for seg in evento.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        headline = str(seg.get("headline") or "").strip()
        if not headline:
            continue
        hnorm = _norm(headline)
        if any(k in hnorm for k in ("spain", "espana", "mediterranean", "europe", "valencia", "balear")):
            hits.append(headline)
        elif any(k in hnorm for k in zonas_txt.split() if len(k) > 4):
            hits.append(headline)
    return hits[0] if hits else ""


def _amplitudes_evento(evento: dict) -> list[dict]:
    out: list[dict] = []
    for obs in evento.get("observations") or []:
        if not isinstance(obs, dict):
            continue
        pred = _a_metros(obs.get("predictedPosAmplitude"), obs.get("predictedPosAmplitudeUnits"))
        obsv = _a_metros(obs.get("observedPosAmplitude"), obs.get("observedPosAmplitudeUnits"))
        val = pred if pred is not None else obsv
        if val is None:
            continue
        out.append({
            "metros": val,
            "tipo": "predicha" if pred is not None else "observada",
            "lugar": str(obs.get("locationName") or "").strip(),
            "llegada": str(obs.get("predictedArrivalTime") or obs.get("observedMaxTime") or "").strip(),
        })
    for bp in evento.get("breakpointLocations") or []:
        if not isinstance(bp, dict):
            continue
        for key, tipo in (("maxAmplitude", "máxima"), ("predictedAmplitude", "predicha")):
            val = _a_metros(bp.get(key), bp.get("amplitudeUnits") or bp.get("units"))
            if val is not None:
                out.append({
                    "metros": val,
                    "tipo": tipo,
                    "lugar": str(bp.get("locationName") or bp.get("name") or "").strip(),
                    "llegada": str(bp.get("predictedArrivalTime") or "").strip(),
                })
    return out


def _resumir_amplitudes(amplitudes: list[dict]) -> tuple[float | None, float | None, str]:
    if not amplitudes:
        return None, None, ""
    vals = [float(a["metros"]) for a in amplitudes if a.get("metros") is not None]
    if not vals:
        return None, None, ""
    mn, mx = min(vals), max(vals)
    llegadas = sorted({a.get("llegada") for a in amplitudes if a.get("llegada")})
    llegada_txt = llegadas[0] if llegadas else ""
    return mn, mx, llegada_txt


def anexar_boletin_tsunami(
    sismo: dict,
    lat_usuario: float,
    lon_usuario: float,
    municipio_id: str | None = None,
) -> dict:
    """Añade texto oficial (NOAA si hay emparejamiento) o aviso IGN · sin estimar ola."""
    zona = zona_costera_usuario(lat_usuario, lon_usuario, municipio_id)
    base = {
        "tsunami_zona_costa": zona["nombre"],
        "tsunami_aemet_costa": zona["aemet"],
        "tsunami_fuente": "IGN / Protección Civil",
        "tsunami_estado": "pendiente",
        "tsunami_amplitud_m": None,
        "tsunami_amplitud_max_m": None,
        "tsunami_llegada": "",
        "tsunami_texto_ola": "Altura en costa: pendiente de boletín oficial (IGN)",
        "tsunami_enlaces": {
            "ign": IGN_TSUNAMI_URL,
            "proteccion_civil": DGPC_URL,
            "noaa": "https://www.tsunami.gov/",
        },
    }
    if sismo.get("es_prueba") or str(sismo.get("id") or "").startswith("sim"):
        base.update({
            "tsunami_estado": "simulacion",
            "tsunami_texto_ola": "Simulación SIRA — sin boletín oficial",
        })
        return {**sismo, **base}

    evento = _emparejar_evento(sismo, _cargar_eventos_gov())
    if not evento:
        return {**sismo, **base}

    amps = _amplitudes_evento(evento)
    mn, mx, llegada = _resumir_amplitudes(amps)
    headline = _texto_segmentos(evento, zona)
    twc = str(evento.get("TWCID") or "NOAA")
    base["tsunami_fuente"] = f"NOAA {twc} / tsunami.gov"
    base["tsunami_llegada"] = llegada
    if headline and not mn:
        base.update({
            "tsunami_estado": "oficial_texto",
            "tsunami_texto_ola": f"Boletín {twc}: {headline[:180]}",
        })
        return {**sismo, **base}

    if mn is None:
        cat = ""
        for seg in evento.get("segments") or []:
            if isinstance(seg, dict) and seg.get("category"):
                cat = str(seg["category"])
                break
        if cat and cat.lower() != "cancellation":
            base.update({
                "tsunami_estado": "oficial_sin_dato",
                "tsunami_texto_ola": f"Evento {twc} ({cat}) — sin amplitud publicada para {zona['nombre']}",
            })
        return {**sismo, **base}

    if abs(mn - mx) < 0.05:
        amp_txt = f"{mn:.2f} m"
    else:
        amp_txt = f"{mn:.2f}–{mx:.2f} m"
    llegada_txt = f" · llegada ~{llegada}" if llegada else ""
    base.update({
        "tsunami_estado": "oficial",
        "tsunami_amplitud_m": mn,
        "tsunami_amplitud_max_m": mx,
        "tsunami_texto_ola": f"Amplitud referencia NOAA: {amp_txt}{llegada_txt} (no es predicción IGN)",
    })
    return {**sismo, **base}


def texto_push_tsunami(enriquecido: dict, *, zona: str, dist_km: float) -> str:
    """Línea de cuerpo para notificación push."""
    mag = enriquecido.get("magnitud", "—")
    radio = enriquecido.get("radio_tsunami_km", "—")
    ola = enriquecido.get("tsunami_texto_ola") or "Consultar IGN"
    radio_txt = f"~{radio} km" if isinstance(radio, (int, float)) else str(radio)
    return f"M{mag} · aviso {radio_txt} · a {dist_km:.0f} km de {zona} · {ola}"
