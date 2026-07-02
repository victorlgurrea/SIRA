"""Genera data/geo/provincias_bordes.json desde IGN (es-atlas / TopoJSON)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from geo_es import provincias
from geo_topojson import norm_geo, rings_from_geometry

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo" / "provincias_bordes.json"
SOURCE_URL = "https://unpkg.com/es-atlas/es/provinces.json"

# Nombres del atlas que no coinciden con INE tal cual
_PROV_ALIASES: dict[str, str] = {
    "alacant": "03",
    "alicante": "03",
    "illes balears": "07",
    "balears": "07",
    "a coruna": "15",
    "la coruna": "15",
    "coruna": "15",
    "las palmas": "35",
    "la rioja": "26",
    "rioja": "26",
    "castello": "12",
    "castellon": "12",
    "valencia": "46",
    "alava": "01",
    "araba": "01",
}


def _prov_lookup() -> dict[str, str]:
    lookup = dict(_PROV_ALIASES)
    for prov in provincias():
        pid = str(prov["id"]).zfill(2)
        nombre = prov["nombre"]
        keys = {norm_geo(nombre)}
        for parte in nombre.split("/"):
            keys.add(norm_geo(parte))
        if "," in nombre:
            a, b = [x.strip() for x in nombre.split(",", 1)]
            keys.add(norm_geo(f"{b} {a}"))
        for key in keys:
            if key:
                lookup[key] = pid
    return lookup


def _provincia_id(nombre: str, lookup: dict[str, str]) -> str | None:
    candidatos = [nombre]
    if "/" in nombre:
        candidatos.extend(p.strip() for p in nombre.split("/"))
    for cand in candidatos:
        key = norm_geo(cand)
        if key in lookup:
            return lookup[key]
        for frag, pid in lookup.items():
            if frag in key or key in frag:
                return pid
    return None


def build() -> Path:
    lookup = _prov_lookup()
    r = requests.get(SOURCE_URL, timeout=120)
    r.raise_for_status()
    topology = r.json()
    geometries = topology["objects"]["provinces"]["geometries"]

    raw: list[dict] = []
    for geometry in geometries:
        nombre = (geometry.get("properties") or {}).get("name", "")
        if "gibraltar" in norm_geo(nombre):
            continue
        prov_id = _provincia_id(nombre, lookup)
        if not prov_id:
            log.warning("Provincia sin mapear: %s", nombre)
            continue
        rings = []
        for ring in rings_from_geometry(topology, geometry):
            if len(ring) < 3:
                continue
            rings.append({"lat": [pt[1] for pt in ring], "lon": [pt[0] for pt in ring]})
        if rings:
            raw.append({"id": prov_id, "nombre": nombre, "rings": rings})

    features = raw
    features.sort(key=lambda x: x["id"])
    payload = {
        "fuente": "IGN — TopoJSON es-atlas (martgnz/es-atlas), contorno provincial completo",
        "url": SOURCE_URL,
        "features": features,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("Provincias bordes: %d provincias → %s", len(features), OUT)
    return OUT


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build()
