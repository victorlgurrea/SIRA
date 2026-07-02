"""Genera data/geo/espana.json desde fuentes oficiales INE (codeforspain)."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo" / "espana.json"
BASE = "https://raw.githubusercontent.com/codeforspain/ds-organizacion-administrativa/master/data"
HF_CSV = "https://huggingface.co/datasets/jaimachu/spain-municipalities-2024/resolve/main/municipios_final.csv"


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_keys(nombre: str) -> list[str]:
    """Variantes normalizadas (p. ej. 'A/B' → claves para A y para B)."""
    partes = [p.strip() for p in str(nombre).split("/") if p.strip()]
    if not partes:
        return [_norm(nombre)]
    keys: list[str] = []
    for parte in partes:
        k = _norm(parte)
        if k and k not in keys:
            keys.append(k)
    return keys


def _prov_key(nombre: str) -> str:
    return _name_keys(nombre)[0]


def _muni_key(nombre: str) -> str:
    return _name_keys(nombre)[0]


def _cargar_coords_hf() -> dict[tuple[str, str], tuple[float, float]]:
    import csv
    import io

    r = requests.get(HF_CSV, timeout=120)
    r.raise_for_status()
    r.encoding = "utf-8"
    coords: dict[tuple[str, str], tuple[float, float]] = {}
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        lat_s, lon_s = row.get("Latitud", ""), row.get("Longitud", "")
        if not lat_s or not lon_s or lat_s.upper() == "NA" or lon_s.upper() == "NA":
            continue
        lat, lon = float(lat_s), float(lon_s)
        prov_keys = _name_keys(row["Provincia"])
        muni_keys = _name_keys(row["Municipio"])
        for pk in prov_keys:
            for mk in muni_keys:
                coords[(pk, mk)] = (lat, lon)
    log.info("Coordenadas CSV: %d claves municipio", len(coords))
    return coords


def _buscar_coords(
    coords_hf: dict[tuple[str, str], tuple[float, float]],
    prov_nombre: str,
    muni_nombre: str,
) -> tuple[float, float] | None:
    prov_keys = _name_keys(prov_nombre)
    muni_keys = _name_keys(muni_nombre)
    for pk in prov_keys:
        for mk in muni_keys:
            hit = coords_hf.get((pk, mk))
            if hit:
                return hit
    return None


def build() -> Path:
    provincias = requests.get(f"{BASE}/provincias.json", timeout=60).json()
    municipios = requests.get(f"{BASE}/municipios.json", timeout=120).json()
    coords_hf = _cargar_coords_hf()

    prov_nombre = {str(p["provincia_id"]).zfill(2): p["nombre"] for p in provincias}
    by_prov: dict[str, list[dict]] = defaultdict(list)
    sin_coords = 0

    for m in municipios:
        pid = str(m["provincia_id"]).zfill(2)
        mid = str(m["municipio_id"]).zfill(5)
        nombre = m["nombre"]
        entry: dict = {"id": mid, "nombre": nombre}
        hit = _buscar_coords(coords_hf, prov_nombre.get(pid, ""), nombre)
        if hit:
            entry["lat"], entry["lon"] = hit
        else:
            sin_coords += 1
        by_prov[pid].append(entry)

    for items in by_prov.values():
        items.sort(key=lambda x: x["nombre"].casefold())

    payload = {
        "fuente": "INE — codeforspain + coordenadas HuggingFace/spain-municipalities-2024",
        "provincias": [
            {"id": str(p["provincia_id"]).zfill(2), "nombre": p["nombre"]}
            for p in sorted(provincias, key=lambda x: x["nombre"].casefold())
        ],
        "municipios": dict(by_prov),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info(
        "Geo España: %d provincias, %d municipios (%d sin coords) → %s",
        len(payload["provincias"]), len(municipios), sin_coords, OUT,
    )
    return OUT


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build()
