"""Aforos SAIH CHJ (MITECO) — nivel y caudal en tiempo casi real."""
from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from config import (
    AFORO_CAUDAL_VIGILANCIA_M3S,
    AFORO_DATOS_MAX_MIN,
    AFORO_MAP_MAX,
    AFORO_RADIO_LOCAL_KM,
    CHJ_SAIH_BASE,
    MAPA,
)
from core import fetch_text
from sismos import distancia_km

log = logging.getLogger(__name__)

_FENOMENOS_LLUVIA_TORMENTA = frozenset({"PR", "TO"})

_NIVEL_PRIORIDAD = {"critico": 4, "alerta": 3, "vigilancia": 2, "fallo": 1, "normal": 0}
_NIVEL_ETIQUETA = {
    "critico": "Crítico",
    "alerta": "Alerta",
    "vigilancia": "Vigilancia",
    "fallo": "Fallo sensor",
    "normal": "Normal",
}

_RE_EMBED = re.compile(r"let\s+(estaciones|aforos)\s*=\s*(\[.+?\]);", re.S)


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _utm30n_a_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """EPSG:25830 (ETRS89 UTM 30N) → (lat, lon) WGS84 aproximado."""
    a = 6378137.0
    f = 1 / 298.257222101
    k0 = 0.9996
    lon0 = math.radians(-3.0)
    e2 = 2 * f - f * f
    e_prime2 = e2 / (1 - e2)
    x = easting - 500_000.0
    y = northing
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
    phi1 += (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
    phi1 += (151 * e1**3 / 96) * math.sin(6 * mu)
    sin_phi = math.sin(phi1)
    cos_phi = math.cos(phi1)
    tan_phi = math.tan(phi1)
    n1 = a / math.sqrt(1 - e2 * sin_phi**2)
    t1 = tan_phi**2
    c1 = e_prime2 * cos_phi**2
    r1 = a * (1 - e2) / (1 - e2 * sin_phi**2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * tan_phi / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e_prime2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e_prime2 - 3 * c1**2) * d**6 / 720
    )
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e_prime2 + 24 * t1**2) * d**5 / 120
    ) / cos_phi
    return math.degrees(lat), math.degrees(lon)


def _en_bbox(lat: float, lon: float) -> bool:
    return MAPA["lat_min"] <= lat <= MAPA["lat_max"] and MAPA["lon_min"] <= lon <= MAPA["lon_max"]


def _parse_embed(html: str, var_name: str) -> list[dict]:
    for m in _RE_EMBED.finditer(html):
        if m.group(1) == var_name:
            data = json.loads(m.group(2))
            return data if isinstance(data, list) else []
    return []


def _fetch_pagina(path: str) -> str:
    url = f"{CHJ_SAIH_BASE.rstrip('/')}/{path.lstrip('/')}"
    return fetch_text(url)


def _variable_reciente(var: dict | None) -> bool:
    if not var:
        return False
    diff = var.get("diferenciaHoraria") or [99, 99]
    if not isinstance(diff, list) or len(diff) < 2:
        return False
    return int(diff[1]) <= AFORO_DATOS_MAX_MIN


def _variable_fallo(var: dict | None) -> bool:
    if not var:
        return False
    estados = var.get("estadosVariable") or []
    return isinstance(estados, list) and len(estados) > 1 and estados[1] == 1


def _tipo_estacion(nombre: str) -> str:
    nom = (nombre or "").strip().upper()
    if nom.startswith("MC "):
        return "marco"
    if nom.startswith("EA "):
        return "aforo"
    if nom.startswith("AZUD"):
        return "azud"
    if "EMBALSE" in nom:
        return "embalse"
    return "otro"


def _es_rambla(nombre: str, variables: list[str]) -> bool:
    txt = f"{nombre} {' '.join(variables)}".upper()
    return any(k in txt for k in ("RAMBLA", "BARRANCO", "RAMBLA"))


def _idx_umbrales_aforos(html_aforos: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in _parse_embed(html_aforos, "aforos"):
        vid = str(row.get("idVariable") or "")
        if not vid:
            continue
        out[vid] = {
            "umbral_bajo": _num(row.get("fldFUmbralBajo"), 0),
            "umbral_medio": _num(row.get("fldFUmbralMedio"), 0),
            "umbral_alto": _num(row.get("fldFUmbralAlto"), 0),
        }
    return out


def _primera_variable(items: list[dict] | None) -> dict | None:
    if not items:
        return None
    return items[0] if isinstance(items[0], dict) else None


def alerta_lluvia_tormenta_zona(provincia: str | None, alertas: list[dict] | None) -> bool:
    """¿Hay aviso AEMET PR/TO activo que afecte a la provincia del aforo?"""
    if not alertas or not provincia:
        return False
    from aemet_alerts import alerta_coincide_zona

    prov_norm = str(provincia).strip().lower()
    for alerta in alertas:
        if not isinstance(alerta, dict):
            continue
        fen = str(alerta.get("fenomeno") or "").upper()
        if fen not in _FENOMENOS_LLUVIA_TORMENTA:
            continue
        if alerta_coincide_zona(alerta, provincia=provincia):
            return True
        area = str(alerta.get("area_desc") or "").lower()
        if prov_norm and prov_norm in area:
            return True
    return False


def nivel_riesgo_aforo(
    *,
    caudal_m3s: float | None,
    umbrales: dict[str, float] | None,
    datos_recientes: bool,
    en_fallo: bool,
    es_rambla: bool = False,
    alerta_lluvia_tormenta: bool = False,
) -> tuple[str, bool]:
    """Devuelve (nivel_riesgo, sin_datos_recientes)."""
    if en_fallo:
        return "fallo", False
    if not datos_recientes:
        if alerta_lluvia_tormenta:
            return "vigilancia", True
        return "normal", False
    q = float(caudal_m3s or 0)
    u = umbrales or {}
    alto = _num(u.get("umbral_alto"))
    medio = _num(u.get("umbral_medio"))
    bajo = _num(u.get("umbral_bajo"))
    if alto > 0 and q >= alto:
        return "critico", False
    if medio > 0 and q >= medio:
        return "alerta", False
    if bajo > 0 and q > bajo:
        return "vigilancia", False
    if es_rambla and q >= AFORO_CAUDAL_VIGILANCIA_M3S:
        return "vigilancia", False
    return "normal", False


def _normalizar_estacion(est: dict, umbrales_idx: dict[str, dict], alertas_meteo: list[dict] | None = None) -> dict | None:
    east = _num(est.get("latitud"))
    north = _num(est.get("longitud"))
    if east == 0.0 and north == 0.0:
        return None
    lat, lon = _utm30n_a_wgs84(east, north)
    if not _en_bbox(lat, lon):
        return None

    nombre = str(est.get("nombreEstacion") or "").strip()
    niveles = est.get("niveles") if isinstance(est.get("niveles"), list) else []
    caudales = est.get("caudales") if isinstance(est.get("caudales"), list) else []
    nv = _primera_variable(niveles)
    ca = _primera_variable(caudales)

    nombres_var = [str(v.get("nombreVariable") or "") for v in niveles + caudales if isinstance(v, dict)]
    es_rambla = _es_rambla(nombre, nombres_var)
    tipo = _tipo_estacion(nombre)

    caudal_id = str(ca.get("idVariable") or "") if ca else ""
    nivel_id = str(nv.get("idVariable") or "") if nv else ""
    umbrales = umbrales_idx.get(caudal_id, {})

    datos_recientes = _variable_reciente(ca) or _variable_reciente(nv)
    en_fallo = _variable_fallo(ca) or _variable_fallo(nv)
    caudal = _num(ca.get("ultimoValor")) if ca else None
    nivel = _num(nv.get("ultimoValor")) if nv else None

    provincia = str(est.get("provincia") or "")
    alerta_meteo = alerta_lluvia_tormenta_zona(provincia, alertas_meteo)
    nivel_riesgo, sin_datos = nivel_riesgo_aforo(
        caudal_m3s=caudal,
        umbrales=umbrales,
        datos_recientes=datos_recientes,
        en_fallo=en_fallo,
        es_rambla=es_rambla,
        alerta_lluvia_tormenta=alerta_meteo,
    )

    est_id = str(est.get("idEstacion") or nombre)
    return {
        "id": f"chj-{est_id}",
        "id_estacion": est_id,
        "nombre": nombre,
        "subcuenca": str(est.get("subcuenca") or ""),
        "provincia": str(est.get("provincia") or ""),
        "poblacion": str(est.get("poblacion") or ""),
        "tipo": tipo,
        "es_rambla": es_rambla,
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "nivel_m": round(nivel, 3) if nv and nivel is not None else None,
        "nivel_variable": str(nv.get("nombreVariable") or "") if nv else "",
        "nivel_fecha": str(nv.get("fecha") or "") if nv else "",
        "caudal_m3s": round(caudal, 3) if ca and caudal is not None else None,
        "caudal_variable": str(ca.get("nombreVariable") or "") if ca else "",
        "caudal_fecha": str(ca.get("fecha") or "") if ca else "",
        "umbral_caudal_bajo": umbrales.get("umbral_bajo"),
        "umbral_caudal_medio": umbrales.get("umbral_medio"),
        "umbral_caudal_alto": umbrales.get("umbral_alto"),
        "datos_recientes": datos_recientes,
        "sin_datos_recientes": sin_datos,
        "nivel_riesgo": nivel_riesgo,
        "fuente": "SAIH CHJ / MITECO",
    }


def descargar_aforos(alertas_meteo: list[dict] | None = None) -> list[dict]:
    """Estaciones CHJ con nivel y caudal (mapa-niveles + umbrales de mapa-aforos)."""
    try:
        html_niveles = _fetch_pagina("mapa-niveles")
        html_aforos = _fetch_pagina("mapa-aforos")
    except Exception as exc:  # noqa: BLE001
        log.warning("SAIH CHJ: %s", exc)
        return []

    estaciones = _parse_embed(html_niveles, "estaciones")
    if not estaciones:
        log.warning("SAIH CHJ: sin datos en mapa-niveles")
        return []

    umbrales_idx = _idx_umbrales_aforos(html_aforos)
    out: list[dict] = []
    for est in estaciones:
        if not isinstance(est, dict):
            continue
        row = _normalizar_estacion(est, umbrales_idx, alertas_meteo)
        if row:
            out.append(row)

    out.sort(
        key=lambda r: (
            -_NIVEL_PRIORIDAD.get(str(r.get("nivel_riesgo")), 0),
            -(float(r.get("caudal_m3s") or 0)),
        )
    )
    log.info(
        "Aforos SAIH CHJ: %d estaciones (%d en alerta)",
        len(out),
        sum(1 for r in out if r.get("nivel_riesgo") in ("vigilancia", "alerta", "critico")),
    )
    return out


def enriquecer_local(aforo: dict, lat_obs: float, lon_obs: float) -> dict:
    d = distancia_km(lat_obs, lon_obs, float(aforo["lat"]), float(aforo["lon"]))
    riesgo = str(aforo.get("nivel_riesgo") or "normal")
    cerca = d <= AFORO_RADIO_LOCAL_KM
    en_alerta = riesgo in ("vigilancia", "alerta", "critico")
    return {
        **aforo,
        "dist_local_km": round(d, 1),
        "cerca_local": cerca,
        "en_mapa": (en_alerta or aforo.get("sin_datos_recientes")) and cerca,
        "mostrar_alerta": en_alerta and cerca,
    }


def aforos_para_mapa(aforos: list[dict], lat_obs: float, lon_obs: float) -> list[dict]:
    rows = [enriquecer_local(a, lat_obs, lon_obs) for a in aforos]
    alertas = [r for r in rows if r.get("en_mapa") and r.get("nivel_riesgo") != "normal"]
    alertas.sort(
        key=lambda r: (
            -_NIVEL_PRIORIDAD.get(str(r.get("nivel_riesgo")), 0),
            float(r.get("dist_local_km") or 9999),
        )
    )
    max_n = max(0, int(AFORO_MAP_MAX))
    return alertas[:max_n] if max_n else []


def resumen_aforos(aforos: list[dict], lat_obs: float, lon_obs: float) -> dict:
    locales = [enriquecer_local(a, lat_obs, lon_obs) for a in aforos]
    alertas = [a for a in locales if a.get("mostrar_alerta")]
    alertas.sort(
        key=lambda r: (
            -_NIVEL_PRIORIDAD.get(str(r.get("nivel_riesgo")), 0),
            -(float(r.get("caudal_m3s") or 0)),
        )
    )
    top = alertas[:3]
    return {
        "n_total": len(aforos),
        "n_vigilancia": sum(1 for a in alertas if a.get("nivel_riesgo") == "vigilancia"),
        "n_alerta": sum(1 for a in alertas if a.get("nivel_riesgo") == "alerta"),
        "n_critico": sum(1 for a in alertas if a.get("nivel_riesgo") == "critico"),
        "n_alertas_local": len(alertas),
        "principales": top,
        "texto_linea": _texto_resumen(top, len(alertas)),
    }


def _texto_resumen(top: list[dict], n_alertas: int) -> str:
    if n_alertas <= 0:
        return "Aforos CHJ cercanos sin alerta de caudal"
    if not top:
        return f"{n_alertas} aforo(s) en vigilancia"
    a = top[0]
    nom = a.get("nombre", "Aforo")
    if a.get("sin_datos_recientes"):
        nivel = "Sensor sin datos"
        icon = "📡"
    else:
        nivel = _NIVEL_ETIQUETA.get(str(a.get("nivel_riesgo")), "Vigilancia")
        icon = ""
    q = a.get("caudal_m3s")
    n = a.get("nivel_m")
    partes: list[str] = []
    if q is not None:
        partes.append(f"Q={q} m³/s")
    if n is not None:
        partes.append(f"h={n} m")
    med = " · ".join(partes) if partes else "—"
    extra = f" · +{n_alertas - 1} más" if n_alertas > 1 else ""
    pref = f"{icon} " if icon else ""
    return f"{pref}{nivel}: {nom} {med}{extra}"
