"""Genera data/geo/ccaa_bordes.json desde IGN (es-atlas / TopoJSON)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from geo_topojson import norm_geo, rings_from_geometry

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo" / "ccaa_bordes.json"
SOURCE_URL = "https://unpkg.com/es-atlas/es/autonomous_regions.json"

NOMBRE_CCAA: dict[str, str] = {
    "andalucia": "AN",
    "aragon": "AR",
    "principado de asturias": "AS",
    "asturias": "AS",
    "illes balears": "IB",
    "islas baleares": "IB",
    "canarias": "CN",
    "islas canarias": "CN",
    "cantabria": "CB",
    "castilla y leon": "CL",
    "castilla la mancha": "CM",
    "cataluna": "CT",
    "catalunya": "CT",
    "ciudad de ceuta": "CE",
    "ceuta": "CE",
    "comunitat valenciana": "VC",
    "comunidad valenciana": "VC",
    "extremadura": "EX",
    "galicia": "GA",
    "comunidad de madrid": "MD",
    "madrid": "MD",
    "melilla": "ML",
    "region de murcia": "MC",
    "murcia": "MC",
    "comunidad foral de navarra": "NC",
    "navarra": "NC",
    "la rioja": "RI",
    "pais vasco": "PV",
    "euskadi": "PV",
}


def _ccaa_id(nombre: str) -> str | None:
    key = norm_geo(nombre)
    if key in NOMBRE_CCAA:
        return NOMBRE_CCAA[key]
    for frag, ccaa in NOMBRE_CCAA.items():
        if frag in key or key in frag:
            return ccaa
    return None


def build() -> Path:
    r = requests.get(SOURCE_URL, timeout=120)
    r.raise_for_status()
    topology = r.json()
    geometries = topology["objects"]["autonomous_regions"]["geometries"]

    raw: list[dict] = []
    for geometry in geometries:
        nombre = (geometry.get("properties") or {}).get("name", "")
        ccaa_id = _ccaa_id(nombre)
        if not ccaa_id:
            log.warning("CCAA sin mapear: %s", nombre)
            continue
        rings = []
        for ring in rings_from_geometry(topology, geometry):
            if len(ring) < 3:
                continue
            rings.append({"lat": [pt[1] for pt in ring], "lon": [pt[0] for pt in ring]})
        if rings:
            raw.append({"id": ccaa_id, "nombre": nombre, "rings": rings})

    features = raw
    features.sort(key=lambda x: x["id"])
    payload = {
        "fuente": "IGN — TopoJSON es-atlas (martgnz/es-atlas), contorno CCAA completo",
        "url": SOURCE_URL,
        "features": features,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("CCAA bordes: %d comunidades → %s", len(features), OUT)
    return OUT


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build()
