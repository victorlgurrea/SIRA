"""Aforos SAIH Confederación Hidrográfica del Ebro (CHE).

La CHE no expone actualmente un endpoint público equivalente al embed CHJ
(`mapa-niveles`) ni al visor ivisor/sadder1.php de Segura. Este módulo
intenta el formato CHJ en `CHE_SAIH_BASE` por si MITECO lo habilita en el futuro.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sira.infrastructure.sources.hydrology.chj import nivel_riesgo_aforo
from sira.config.settings import CHE_SAIH_BASE
from sira.infrastructure.http.client import fetch_text

log = logging.getLogger(__name__)

_RE_EMBED = re.compile(r"let\s+(estaciones|aforos)\s*=\s*(\[.+?\]);", re.S)
_PATHS = ("mapa-niveles", "MapaNiveles", "mapas/mapa-niveles")


def _parse_embed(html: str, var_name: str) -> list[dict]:
    for m in _RE_EMBED.finditer(html):
        if m.group(1) == var_name:
            data = json.loads(m.group(2))
            return data if isinstance(data, list) else []
    return []


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _intenta_embed_chj() -> list[dict]:
    base = CHE_SAIH_BASE.rstrip("/")
    for path in _PATHS:
        try:
            html = fetch_text(f"{base}/{path}")
        except Exception:
            continue
        estaciones = _parse_embed(html, "estaciones")
        if estaciones:
            log.info("SAIH Ebro: embed CHJ en %s/%s (%d estaciones)", base, path, len(estaciones))
            return estaciones
    return []


def descargar_aforos(_alertas_meteo: list[dict] | None = None) -> list[dict]:
    """Intenta obtener aforos CHE; devuelve [] si no hay API pública disponible."""
    estaciones = _intenta_embed_chj()
    if not estaciones:
        log.warning(
            "SAIH Ebro: sin API pública tipo CHJ/Segura en %s (pendiente MITECO/CHE)",
            CHE_SAIH_BASE,
        )
        return []

    out: list[dict] = []
    for est in estaciones:
        if not isinstance(est, dict):
            continue
        nombre = str(est.get("nombreEstacion") or "").strip()
        caudal = _num(est.get("caudal") or est.get("ultimoCaudal"), default=-1)
        nivel = _num(est.get("nivel") or est.get("ultimoNivel"), default=-1)
        nivel_riesgo, _ = nivel_riesgo_aforo(
            caudal_m3s=caudal if caudal >= 0 else None,
            umbrales=None,
            datos_recientes=True,
            en_fallo=False,
        )
        est_id = str(est.get("idEstacion") or nombre)
        out.append({
            "id": f"che-{est_id}",
            "id_estacion": est_id,
            "nombre": nombre,
            "subcuenca": str(est.get("subcuenca") or ""),
            "provincia": str(est.get("provincia") or ""),
            "poblacion": str(est.get("poblacion") or ""),
            "tipo": "aforo",
            "es_rambla": False,
            "lat": _num(est.get("latitud")),
            "lon": _num(est.get("longitud")),
            "nivel_m": nivel if nivel >= 0 else None,
            "caudal_m3s": caudal if caudal >= 0 else None,
            "datos_recientes": True,
            "sin_datos_recientes": False,
            "nivel_riesgo": nivel_riesgo,
            "fuente": "SAIH Ebro / CHE",
        })
    return out
