"""Provincias, municipios y localidades de España (INE)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO_FILE = ROOT / "data" / "geo" / "espana.json"


def ensure_geo() -> None:
    if not GEO_FILE.is_file():
        from build_geo_es import build

        build()


@lru_cache(maxsize=1)
def _data() -> dict:
    ensure_geo()
    return json.loads(GEO_FILE.read_text(encoding="utf-8"))


def provincias() -> list[dict]:
    return _data()["provincias"]


def municipios(provincia_id: str | None) -> list[dict]:
    if not provincia_id:
        return []
    return _data()["municipios"].get(str(provincia_id).zfill(2), [])


def municipio_por_id(municipio_id: str | None) -> dict | None:
    if not municipio_id:
        return None
    mid = str(municipio_id).zfill(5)
    for items in _data()["municipios"].values():
        for m in items:
            if m["id"] == mid:
                return m
    return None


def localidades(municipio_id: str | None) -> list[dict]:
    muni = municipio_por_id(municipio_id)
    if not muni:
        return []
    mid, nombre = muni["id"], muni["nombre"]
    if "/" in nombre:
        return [
            {"id": f"{mid}-{i}", "nombre": parte.strip()}
            for i, parte in enumerate(nombre.split("/"))
            if parte.strip()
        ]
    return [{"id": mid, "nombre": nombre}]


def provincia_de_municipio(municipio_id: str) -> str | None:
    mid = str(municipio_id).zfill(5)
    for pid, items in _data()["municipios"].items():
        if any(m["id"] == mid for m in items):
            return pid
    return None


def coords_municipio(municipio_id: str | None) -> tuple[float, float]:
    from config import ZONA

    if not municipio_id:
        return ZONA["lat_ref"], ZONA["lon_ref"]
    muni = municipio_por_id(municipio_id)
    if muni and muni.get("lat") is not None and muni.get("lon") is not None:
        return float(muni["lat"]), float(muni["lon"])
    return ZONA["lat_ref"], ZONA["lon_ref"]


def opciones(items: list[dict], placeholder: str = "Selecciona…") -> list[dict]:
    if not items:
        return [{"label": placeholder, "value": "__none__", "disabled": True}]
    return [{"label": i["nombre"], "value": str(i["id"])} for i in items]
