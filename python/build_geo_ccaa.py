"""Genera data/geo/ccaa_bordes.json desde IGN (es-atlas / TopoJSON)."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

import requests

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo" / "ccaa_bordes.json"
SOURCE_URL = "https://unpkg.com/es-atlas/es/autonomous_regions.json"


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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
    key = _norm(nombre)
    if key in NOMBRE_CCAA:
        return NOMBRE_CCAA[key]
    for frag, ccaa in NOMBRE_CCAA.items():
        if frag in key or key in frag:
            return ccaa
    return None


def _decode_arc(topology: dict, arc_index: int) -> list[list[float]]:
    arcs = topology["arcs"]
    transform = topology.get("transform")
    arc = arcs[arc_index]
    x = y = 0.0
    coords: list[list[float]] = []
    for dx, dy in arc:
        x += dx
        y += dy
        if transform:
            lon = x * transform["scale"][0] + transform["translate"][0]
            lat = y * transform["scale"][1] + transform["translate"][1]
        else:
            lon, lat = x, y
        coords.append([lon, lat])
    return coords


def _decode_ring(topology: dict, arc_list: list[int]) -> list[list[float]]:
    coords: list[list[float]] = []
    for arc_index in arc_list:
        reverse = arc_index < 0
        idx = ~arc_index if reverse else arc_index
        arc_coords = _decode_arc(topology, idx)
        if reverse:
            arc_coords = arc_coords[::-1]
        if coords and arc_coords and coords[-1] == arc_coords[0]:
            coords.extend(arc_coords[1:])
        else:
            coords.extend(arc_coords)
    return coords


def _rings_from_geometry(topology: dict, geometry: dict) -> list[list[list[float]]]:
    gtype = geometry.get("type")
    arcs = geometry.get("arcs")
    if not arcs:
        return []
    if gtype == "Polygon":
        return [_decode_ring(topology, ring) for ring in arcs]
    if gtype == "MultiPolygon":
        return [_decode_ring(topology, ring) for part in arcs for ring in part]
    return []


def build() -> Path:
    r = requests.get(SOURCE_URL, timeout=120)
    r.raise_for_status()
    topology = r.json()
    geometries = topology["objects"]["autonomous_regions"]["geometries"]

    features: list[dict] = []
    for geometry in geometries:
        nombre = (geometry.get("properties") or {}).get("name", "")
        ccaa_id = _ccaa_id(nombre)
        if not ccaa_id:
            log.warning("CCAA sin mapear: %s", nombre)
            continue
        rings = []
        for ring in _rings_from_geometry(topology, geometry):
            if len(ring) < 3:
                continue
            lons = [pt[0] for pt in ring]
            lats = [pt[1] for pt in ring]
            rings.append({"lat": lats, "lon": lons})
        if rings:
            features.append({"id": ccaa_id, "nombre": nombre, "rings": rings})

    features.sort(key=lambda x: x["id"])
    payload = {
        "fuente": "IGN — TopoJSON es-atlas (martgnz/es-atlas)",
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
