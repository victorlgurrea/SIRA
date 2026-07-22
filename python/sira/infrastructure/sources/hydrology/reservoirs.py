"""Embalses en vigilancia vía embals.es (SAIH + MITECO agregados)."""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from sira.config.settings import (
    EMBALSE_CUENCAS,
    EMBALSE_MAP_MAX,
    EMBALSE_RADIO_LOCAL_KM,
    EMBALSE_UMBRAL_ALERTA,
    EMBALSE_UMBRAL_CRITICO,
    EMBALSE_UMBRAL_VIGILANCIA,
    EMBALS_API_BASE,
    EMBALS_API_KEY,
    MAPA,
)
from sira.infrastructure.http.client import fetch_json
from sira.domain.seismic.sismos import distancia_km

log = logging.getLogger(__name__)

_NIVEL_PRIORIDAD = {"critico": 3, "alerta": 2, "vigilancia": 1, "normal": 0}
_NIVEL_ETIQUETA = {
    "critico": "Crítico",
    "alerta": "Alerta",
    "vigilancia": "Vigilancia",
    "normal": "Normal",
}


def _norm_nombre(value: str | None) -> str:
    if not value:
        return ""
    txt = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    txt = re.sub(r"\s*-\s*la\s+ribera.*$", "", txt, flags=re.I)
    txt = re.sub(r"\s+(I{1,3}|IV|V|VI{0,3})$", "", txt, flags=re.I)
    return re.sub(r"[^A-Z0-9]+", "", txt.upper())


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _headers() -> dict[str, str]:
    if not EMBALS_API_KEY:
        return {}
    return {"apikey": EMBALS_API_KEY, "Authorization": f"Bearer {EMBALS_API_KEY}"}


def _fetch_endpoint(path: str) -> dict | list:
    url = f"{EMBALS_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    data = fetch_json(url, headers=_headers() or None)
    if not isinstance(data, (dict, list)):
        raise ValueError(f"embals.es {path}: JSON inválido")
    return data


def _en_bbox(lat: float, lon: float) -> bool:
    return MAPA["lat_min"] <= lat <= MAPA["lat_max"] and MAPA["lon_min"] <= lon <= MAPA["lon_max"]


def _cuenca_permitida(cuenca: str | None) -> bool:
    if not EMBALSE_CUENCAS:
        return True
    norm = unicodedata.normalize("NFKD", str(cuenca or "")).encode("ascii", "ignore").decode().lower()
    return any(allowed in norm for allowed in EMBALSE_CUENCAS)


def nivel_riesgo_embalse(
    porcentaje: float,
    *,
    variacion_semanal_hm3: float = 0.0,
    variacion_semanal_pct: float = 0.0,
    lluvia_24h_mm: float = 0.0,
) -> str:
    """Clasificación orientativa de riesgo hidráulico (no predicción de rotura de presa)."""
    pct = float(porcentaje)
    if pct >= EMBALSE_UMBRAL_CRITICO:
        return "critico"
    if pct >= EMBALSE_UMBRAL_ALERTA:
        return "alerta"
    sube = variacion_semanal_hm3 > 0 or variacion_semanal_pct > 0.5
    if pct >= EMBALSE_UMBRAL_VIGILANCIA:
        return "vigilancia"
    if pct >= EMBALSE_UMBRAL_VIGILANCIA - 10 and sube and lluvia_24h_mm >= 15:
        return "vigilancia"
    if pct >= 70 and sube and lluvia_24h_mm >= 30:
        return "vigilancia"
    return "normal"


def _merge_registros(v2_list: list[dict], saih_list: list[dict]) -> list[dict]:
    saih_idx: dict[str, dict] = {}
    for row in saih_list:
        key = _norm_nombre(row.get("nombre"))
        if key:
            saih_idx[key] = row

    out: list[dict] = []
    usados: set[str] = set()

    for base in v2_list:
        lat = _num(base.get("lat") or base.get("latitude"))
        lon = _num(base.get("lng") or base.get("lon") or base.get("longitude"))
        if lat == 0.0 and lon == 0.0:
            continue
        if not _en_bbox(lat, lon):
            continue
        cuenca = str(base.get("cuenca") or "")
        if not _cuenca_permitida(cuenca):
            continue

        nombre = str(base.get("nombre") or "").strip()
        key = _norm_nombre(nombre)
        live = saih_idx.get(key)

        pct_v2 = _num(base.get("porcentaje"))
        var_hm3 = _num(base.get("variacionSemanal"))
        var_pct = _num(base.get("variacionPorcentaje"))
        pct = _num(live.get("porcentaje")) if live else pct_v2
        volumen = _num(live.get("volumen")) if live else _num(base.get("aguaActual"))
        capacidad = _num(base.get("capacidadTotal"))
        actualizado = ""
        if live:
            actualizado = f"{live.get('fechaActualizacion', '')} {live.get('horaActualizacion', '')}".strip()

        embalse_id = str(base.get("id") or f"emb-{_norm_nombre(nombre) or key}")
        out.append({
            "id": embalse_id,
            "nombre": nombre,
            "cuenca": cuenca,
            "provincia": str(base.get("provincia") or live.get("provincia") if live else ""),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "porcentaje": round(pct, 2),
            "volumen_hm3": round(volumen, 2),
            "capacidad_hm3": round(capacidad, 2),
            "variacion_semanal_hm3": round(var_hm3, 2),
            "variacion_semanal_pct": round(var_pct, 2),
            "actualizado": actualizado,
            "fuente": "embals.es / SAIH",
        })
        if key:
            usados.add(key)

    for row in saih_list:
        key = _norm_nombre(row.get("nombre"))
        if not key or key in usados:
            continue
        if not _cuenca_permitida(str(row.get("cuenca") or "")):
            continue
        out.append({
            "id": f"saih-{key}",
            "nombre": str(row.get("nombre") or "").strip(),
            "cuenca": str(row.get("cuenca") or ""),
            "provincia": str(row.get("provincia") or ""),
            "lat": 0.0,
            "lon": 0.0,
            "porcentaje": round(_num(row.get("porcentaje")), 2),
            "volumen_hm3": round(_num(row.get("volumen")), 2),
            "capacidad_hm3": 0.0,
            "variacion_semanal_hm3": 0.0,
            "variacion_semanal_pct": 0.0,
            "actualizado": f"{row.get('fechaActualizacion', '')} {row.get('horaActualizacion', '')}".strip(),
            "fuente": "embals.es / SAIH",
        })

    return out


def descargar_embalses() -> list[dict]:
    """Embalses peninsulares con coordenadas y lectura SAIH reciente."""
    try:
        raw_v2 = _fetch_endpoint("embalses-data-v2")
        raw_saih = _fetch_endpoint("saih-data")
    except Exception as exc:  # noqa: BLE001
        log.warning("embals.es: %s", exc)
        return []

    v2_list = raw_v2.get("embalses", []) if isinstance(raw_v2, dict) else []
    saih_list = raw_saih.get("embalses", []) if isinstance(raw_saih, dict) else []
    if not v2_list and not saih_list:
        return []

    merged = _merge_registros(v2_list, saih_list)
    for row in merged:
        row["nivel_riesgo"] = nivel_riesgo_embalse(
            row["porcentaje"],
            variacion_semanal_hm3=row["variacion_semanal_hm3"],
            variacion_semanal_pct=row["variacion_semanal_pct"],
        )
    merged.sort(key=lambda r: (-_NIVEL_PRIORIDAD.get(r["nivel_riesgo"], 0), -r["porcentaje"]))
    log.info("Embalses embals.es: %d (%d en mapa potencial)", len(merged), sum(1 for r in merged if r["lat"]))
    return merged


def enriquecer_local(
    embalse: dict,
    lat_obs: float,
    lon_obs: float,
    *,
    lluvia_24h_mm: float = 0.0,
) -> dict:
    d = distancia_km(lat_obs, lon_obs, float(embalse["lat"]), float(embalse["lon"])) if embalse.get("lat") else 9999.0
    nivel = nivel_riesgo_embalse(
        embalse.get("porcentaje", 0),
        variacion_semanal_hm3=embalse.get("variacion_semanal_hm3", 0),
        variacion_semanal_pct=embalse.get("variacion_semanal_pct", 0),
        lluvia_24h_mm=lluvia_24h_mm,
    )
    cerca = d <= EMBALSE_RADIO_LOCAL_KM
    en_alerta = nivel in ("vigilancia", "alerta", "critico")
    return {
        **embalse,
        "nivel_riesgo": nivel,
        "dist_local_km": round(d, 1) if embalse.get("lat") else None,
        "cerca_local": cerca,
        "en_mapa": bool(embalse.get("lat")) and en_alerta and cerca,
        "mostrar_alerta": en_alerta and cerca,
    }


def embalses_para_mapa(embalses: list[dict], lat_obs: float, lon_obs: float, *, lluvia_24h_mm: float = 0.0) -> list[dict]:
    rows = [enriquecer_local(e, lat_obs, lon_obs, lluvia_24h_mm=lluvia_24h_mm) for e in embalses]
    alertas = [r for r in rows if r.get("en_mapa") and r.get("nivel_riesgo") != "normal"]
    alertas.sort(
        key=lambda r: (
            -_NIVEL_PRIORIDAD.get(str(r.get("nivel_riesgo")), 0),
            float(r.get("dist_local_km") or 9999),
        )
    )
    max_n = max(0, int(EMBALSE_MAP_MAX))
    return alertas[:max_n] if max_n else []


def resumen_embalses(embalses: list[dict], lat_obs: float, lon_obs: float, *, lluvia_24h_mm: float = 0.0) -> dict:
    """Resumen para la tarjeta de lluvia 24h."""
    locales = [enriquecer_local(e, lat_obs, lon_obs, lluvia_24h_mm=lluvia_24h_mm) for e in embalses]
    alertas = [e for e in locales if e.get("mostrar_alerta")]
    alertas.sort(
        key=lambda r: (
            -_NIVEL_PRIORIDAD.get(str(r.get("nivel_riesgo")), 0),
            -float(r.get("porcentaje") or 0),
        )
    )
    top = alertas[:3]
    return {
        "n_total": len(embalses),
        "n_vigilancia": sum(1 for e in alertas if e.get("nivel_riesgo") == "vigilancia"),
        "n_alerta": sum(1 for e in alertas if e.get("nivel_riesgo") == "alerta"),
        "n_critico": sum(1 for e in alertas if e.get("nivel_riesgo") == "critico"),
        "n_alertas_local": len(alertas),
        "principales": top,
        "texto_linea": _texto_resumen(top, len(alertas)),
    }


def _texto_resumen(top: list[dict], n_alertas: int) -> str:
    if n_alertas <= 0:
        return "Embalses cercanos sin vigilancia activa"
    if not top:
        return f"{n_alertas} embalse(s) en vigilancia"
    e = top[0]
    nom = e.get("nombre", "Embalse")
    pct = e.get("porcentaje", "—")
    nivel = _NIVEL_ETIQUETA.get(str(e.get("nivel_riesgo")), "Vigilancia")
    extra = f" · +{n_alertas - 1} más" if n_alertas > 1 else ""
    return f"{nivel}: {nom} {pct}%{extra}"
