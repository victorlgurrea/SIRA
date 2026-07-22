"""Utilidades compartidas para decodificar TopoJSON (es-atlas / IGN)."""
from __future__ import annotations

import re
import unicodedata


def norm_geo(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def decode_arc(topology: dict, arc_index: int) -> list[list[float]]:
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


def decode_ring(topology: dict, arc_list: list[int]) -> list[list[float]]:
    coords: list[list[float]] = []
    for arc_index in arc_list:
        reverse = arc_index < 0
        idx = ~arc_index if reverse else arc_index
        arc_coords = decode_arc(topology, idx)
        if reverse:
            arc_coords = arc_coords[::-1]
        if coords and arc_coords and coords[-1] == arc_coords[0]:
            coords.extend(arc_coords[1:])
        else:
            coords.extend(arc_coords)
    return coords


def rings_from_geometry(topology: dict, geometry: dict) -> list[list[list[float]]]:
    gtype = geometry.get("type")
    arcs = geometry.get("arcs")
    if not arcs:
        return []
    if gtype == "Polygon":
        return [decode_ring(topology, ring) for ring in arcs]
    if gtype == "MultiPolygon":
        return [decode_ring(topology, ring) for part in arcs for ring in part]
    return []
