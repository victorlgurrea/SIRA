"""Aforos SAIH Confederación Hidrográfica del Segura (CHS)."""
from __future__ import annotations

import html as html_module
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aforos import (
    _en_bbox,
    _es_rambla,
    _tipo_estacion,
    _utm30n_a_wgs84,
    alerta_lluvia_tormenta_zona,
    nivel_riesgo_aforo,
)
from config import AFORO_DATOS_MAX_MIN, CHS_SAIH_BASE
from core import fetch_json, fetch_text

log = logging.getLogger(__name__)

_HORA_ES = ZoneInfo("Europe/Madrid")
_NIVEL_PRIORIDAD = {"critico": 4, "alerta": 3, "vigilancia": 2, "fallo": 1, "normal": 0}

_ARCGIS_BASE = (
    f"{CHS_SAIH_BASE.rstrip('/')}/server/rest/services/"
    "VISOR_CHSIC3/VISOR_PUBLICO_ETRS89_v5_vectorial_dinamico/MapServer"
)
_SADDER_URL = "https://saihweb.chsegura.es/apps/iVisor/sadder1.php"
_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SIRA/1.0)"}
_ARCGIS_FIELDS = (
    "ESRI_OID,CodPuntoMedicion,DenominacionPtoMedicion,CodVariableHidrologica,"
    "DenominacionVariable,CodTipoVariableHidrologica,X_ETRS89,Y_ETRS89"
)
_RE_CSV = re.compile(r'id="csv"\s+value="([^"]+)"', re.I)
_RE_PUNTO = re.compile(r"^(\d{2}[A-Z]\d{2})")
_SADDER_WORKERS = 6


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _punto_codigo(cod_punto: str) -> str:
    cod = str(cod_punto or "").strip().upper()
    m = _RE_PUNTO.match(cod)
    return m.group(1) if m else cod[:5]


def _variable_sufijo(cod_variable: str, punto: str) -> str:
    cod = str(cod_variable or "").strip().upper()
    if cod.startswith(punto):
        return cod[len(punto) :]
    return cod[-3:] if len(cod) >= 3 else cod


def _parse_fecha_segura(texto: str) -> datetime | None:
    raw = str(texto or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=_HORA_ES)
        except ValueError:
            continue
    return None


def _datos_recientes(fecha_txt: str) -> bool:
    dt = _parse_fecha_segura(fecha_txt)
    if not dt:
        return False
    ahora = datetime.now(_HORA_ES)
    return (ahora - dt).total_seconds() <= AFORO_DATOS_MAX_MIN * 60


def parse_sadder_csv(html: str) -> dict[str, dict[str, Any]]:
    """Extrae variables del campo oculto csv de sadder1.php."""
    m = _RE_CSV.search(html or "")
    if not m:
        return {}
    csv = html_module.unescape(m.group(1))
    out: dict[str, dict[str, Any]] = {}
    for part in csv.split("***"):
        chunk = part.strip()
        if not chunk or chunk.startswith("Relación") or chunk.startswith("VARIABLE"):
            continue
        fields = [f.strip() for f in chunk.split(";")]
        if len(fields) < 4:
            continue
        code = fields[0].strip()
        if not code:
            continue
        valor_raw = fields[3].replace(",", ".")
        try:
            valor = float(valor_raw)
        except ValueError:
            valor = None
        out[code] = {
            "valor": valor,
            "fecha": fields[2].strip() if len(fields) > 2 else "",
            "descripcion": fields[1].strip() if len(fields) > 1 else "",
        }
    return out


def _fetch_capa(layer_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = fetch_json(
            f"{_ARCGIS_BASE}/{layer_id}/query",
            headers=_FETCH_HEADERS,
            params={
                "where": "1=1",
                "outFields": _ARCGIS_FIELDS,
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": 1000,
                "orderByFields": "ESRI_OID",
            },
        )
        if not isinstance(data, dict):
            break
        if data.get("error"):
            raise ValueError(f"ArcGIS capa {layer_id}: {data['error']}")
        feats = data.get("features") or []
        if not isinstance(feats, list) or not feats:
            break
        for feat in feats:
            if isinstance(feat, dict) and isinstance(feat.get("attributes"), dict):
                rows.append(feat["attributes"])
        offset += len(feats)
        if len(feats) < 1000:
            break
    return rows


def _fetch_sadder(punto: str) -> dict[str, dict[str, Any]]:
    html = fetch_text(
        _SADDER_URL,
        params={"zona": "I", "punto": punto, "callVisSerie": "N"},
        headers=_FETCH_HEADERS,
    )
    return parse_sadder_csv(html)


def _fetch_sadder_paralelo(puntos: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    if not puntos:
        return cache
    workers = min(_SADDER_WORKERS, len(puntos))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_sadder, p): p for p in puntos}
        for fut in as_completed(futures):
            punto = futures[fut]
            try:
                cache[punto] = fut.result()
            except Exception as exc:  # noqa: BLE001
                log.debug("SAIH Segura sadder %s: %s", punto, exc)
                cache[punto] = {}
    return cache


def _normalizar_fila(
    attrs: dict[str, Any],
    valores_punto: dict[str, dict[str, Any]],
    alertas_meteo: list[dict] | None,
) -> dict | None:
    east = _num(attrs.get("X_ETRS89"))
    north = _num(attrs.get("Y_ETRS89"))
    if east == 0.0 and north == 0.0:
        return None
    lat, lon = _utm30n_a_wgs84(east, north)
    if not _en_bbox(lat, lon):
        return None

    cod_punto = str(attrs.get("CodPuntoMedicion") or "").strip()
    cod_var = str(attrs.get("CodVariableHidrologica") or "").strip()
    punto = _punto_codigo(cod_punto)
    sufijo = _variable_sufijo(cod_var, punto)
    lectura = valores_punto.get(sufijo) or {}

    nombre = str(attrs.get("DenominacionPtoMedicion") or attrs.get("DenominacionVariable") or "").strip()
    tipo_var = str(attrs.get("CodTipoVariableHidrologica") or "").upper()
    desc_var = str(attrs.get("DenominacionVariable") or lectura.get("descripcion") or "")
    es_rambla = _es_rambla(nombre, [desc_var])
    tipo = _tipo_estacion(nombre)

    valor = lectura.get("valor")
    fecha = str(lectura.get("fecha") or "")
    datos_recientes = bool(fecha) and _datos_recientes(fecha)

    caudal = nivel = None
    if tipo_var == "Q" or sufijo.upper().startswith("Q"):
        caudal = valor
    elif tipo_var in ("U", "H") or sufijo.upper().startswith(("U", "H")):
        nivel = valor
    else:
        unidad = desc_var.lower()
        if "m3" in unidad or "m³" in unidad:
            caudal = valor
        elif unidad.endswith("m"):
            nivel = valor

    alerta_meteo = alerta_lluvia_tormenta_zona(None, alertas_meteo)
    nivel_riesgo, sin_datos = nivel_riesgo_aforo(
        caudal_m3s=caudal,
        umbrales=None,
        datos_recientes=datos_recientes,
        en_fallo=False,
        es_rambla=es_rambla,
        alerta_lluvia_tormenta=alerta_meteo,
    )

    est_id = cod_punto or cod_var or punto
    return {
        "id": f"chs-{est_id}",
        "id_estacion": est_id,
        "nombre": nombre,
        "subcuenca": "",
        "provincia": "",
        "poblacion": "",
        "tipo": tipo,
        "es_rambla": es_rambla,
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "nivel_m": round(nivel, 3) if nivel is not None else None,
        "nivel_variable": desc_var if nivel is not None else "",
        "nivel_fecha": fecha if nivel is not None else "",
        "caudal_m3s": round(caudal, 3) if caudal is not None else None,
        "caudal_variable": desc_var if caudal is not None else "",
        "caudal_fecha": fecha if caudal is not None else "",
        "umbral_caudal_bajo": None,
        "umbral_caudal_medio": None,
        "umbral_caudal_alto": None,
        "datos_recientes": datos_recientes,
        "sin_datos_recientes": sin_datos,
        "nivel_riesgo": nivel_riesgo,
        "fuente": "SAIH Segura / CHS",
        "punto_saih": punto,
        "variable_saih": cod_var,
    }


def descargar_aforos(alertas_meteo: list[dict] | None = None) -> list[dict]:
    """Estaciones CHS: metadatos ArcGIS + valores en tiempo real vía sadder1.php."""
    try:
        filas = _fetch_capa(10) + _fetch_capa(11)
    except Exception as exc:  # noqa: BLE001
        log.warning("SAIH Segura ArcGIS: %s", exc)
        return []

    if not filas:
        log.warning("SAIH Segura: sin estaciones en ArcGIS")
        return []

    puntos_bbox: set[str] = set()
    for attrs in filas:
        east = _num(attrs.get("X_ETRS89"))
        north = _num(attrs.get("Y_ETRS89"))
        if east == 0.0 and north == 0.0:
            continue
        lat, lon = _utm30n_a_wgs84(east, north)
        if _en_bbox(lat, lon):
            puntos_bbox.add(_punto_codigo(str(attrs.get("CodPuntoMedicion") or "")))

    valores = _fetch_sadder_paralelo(sorted(puntos_bbox))

    out: list[dict] = []
    vistos: set[str] = set()
    for attrs in filas:
        cod_punto = str(attrs.get("CodPuntoMedicion") or "").strip()
        cod_var = str(attrs.get("CodVariableHidrologica") or "").strip()
        clave = f"{cod_punto}|{cod_var}"
        if clave in vistos:
            continue
        vistos.add(clave)
        punto = _punto_codigo(cod_punto)
        row = _normalizar_fila(attrs, valores.get(punto, {}), alertas_meteo)
        if row:
            out.append(row)

    out.sort(
        key=lambda r: (
            -_NIVEL_PRIORIDAD.get(str(r.get("nivel_riesgo")), 0),
            -(float(r.get("caudal_m3s") or 0)),
        )
    )
    log.info(
        "Aforos SAIH Segura: %d variables (%d puntos, %d en alerta)",
        len(out),
        len(puntos_bbox),
        sum(1 for r in out if r.get("nivel_riesgo") in ("vigilancia", "alerta", "critico")),
    )
    return out
