"""Puntos en mar Cantábrico / Atlántico ibérico sin invadir tierra."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import requests

from sira.infrastructure.geo import REPO_ROOT as ROOT
from sira.infrastructure.geo.bordes_clip import anillos_tierra, punto_en_tierra
from sira.infrastructure.geo.topojson import rings_from_geometry

log = logging.getLogger(__name__)

TIERRA_FILE = ROOT / "data" / "geo" / "mundo_tierra_atlantico.json"
LAND_URL = "https://unpkg.com/world-atlas@2/land-50m.json"

# lon_min, lat_min, lon_max, lat_max — costa atlántica PT/ES + Cantábrico + golfo Cádiz.
BBOX: tuple[float, float, float, float] = (-11.5, 35.5, 1.0, 45.0)

_BANDA_DEG = 0.25


def _interseca_bbox(ring: list[list[float]]) -> bool:
    lon_min, lat_min, lon_max, lat_max = BBOX
    r_lon_min = min(p[0] for p in ring)
    r_lon_max = max(p[0] for p in ring)
    r_lat_min = min(p[1] for p in ring)
    r_lat_max = max(p[1] for p in ring)
    return not (r_lon_max < lon_min or r_lon_min > lon_max or r_lat_max < lat_min or r_lat_min > lat_max)


def build_tierra_atlantico() -> Path:
    r = requests.get(LAND_URL, timeout=120)
    r.raise_for_status()
    topology = r.json()
    geometry = topology["objects"]["land"]["geometries"][0]
    rings = rings_from_geometry(topology, geometry)
    rings_atl = [ring for ring in rings if _interseca_bbox(ring)]
    payload = {
        "fuente": "Natural Earth 50m (world-atlas land-50m.json)",
        "url": LAND_URL,
        "bbox": list(BBOX),
        "rings": [
            {"lat": [p[1] for p in ring], "lon": [p[0] for p in ring]}
            for ring in rings_atl
        ],
    }
    TIERRA_FILE.parent.mkdir(parents=True, exist_ok=True)
    TIERRA_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    log.info(
        "Mundo tierra (Atlántico): %d/%d polígonos → %s",
        len(rings_atl), len(rings), TIERRA_FILE,
    )
    return TIERRA_FILE


def ensure_tierra_atlantico() -> None:
    if not TIERRA_FILE.is_file():
        build_tierra_atlantico()


@lru_cache(maxsize=1)
def anillos_tierra_atlantico() -> list[list[list[float]]]:
    ensure_tierra_atlantico()
    data = json.loads(TIERRA_FILE.read_text(encoding="utf-8"))
    return [
        [[lon, lat] for lon, lat in zip(ring["lon"], ring["lat"])]
        for ring in data.get("rings", [])
    ]


def _construir_indice(ring: list[list[float]]) -> dict[int, list[tuple[float, float, float, float]]]:
    bandas: dict[int, list[tuple[float, float, float, float]]] = {}
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        b_lo = int(min(y1, y2) // _BANDA_DEG)
        b_hi = int(max(y1, y2) // _BANDA_DEG)
        for b in range(b_lo, b_hi + 1):
            bandas.setdefault(b, []).append((x1, y1, x2, y2))
    return bandas


@lru_cache(maxsize=1)
def _anillos_indexados() -> list[
    tuple[tuple[float, float, float, float], dict[int, list[tuple[float, float, float, float]]]]
]:
    salida = []
    for ring in anillos_tierra_atlantico():
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        bbox = (min(lons), min(lats), max(lons), max(lats))
        salida.append((bbox, _construir_indice(ring)))
    return salida


def punto_en_tierra_mundo_atlantico(lat: float, lon: float) -> bool:
    """True si (lat, lon) cae en tierra (PT, FR, IE…) según Natural Earth indexado."""
    banda = int(lat // _BANDA_DEG)
    for (lon_min, lat_min, lon_max, lat_max), indice in _anillos_indexados():
        if lon < lon_min or lon > lon_max or lat < lat_min or lat > lat_max:
            continue
        aristas = indice.get(banda)
        if not aristas:
            continue
        dentro = False
        for x1, y1, x2, y2 in aristas:
            if (y1 > lat) != (y2 > lat):
                x_int = (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1
                if lon < x_int:
                    dentro = not dentro
        if dentro:
            return True
    return False


@lru_cache(maxsize=1)
def _anillos_ign() -> list[list[list[float]]]:
    return anillos_tierra()


def _en_bbox_mar_atlantico(lat: float, lon: float) -> bool:
    """Envolvente laxa Atlántico PT/ES + Cantábrico + golfo Cádiz / Estrecho."""
    # Costa atlántica PT/ES (Galicia → Estrecho de Gibraltar).
    if 35.85 <= lat <= 42.35 and -10.95 <= lon <= -4.95:
        return True
    # Cantábrico (Rías Altas → País Vasco).
    if 42.10 <= lat <= 44.55 and -10.95 <= lon <= -1.15:
        return True
    return False


def punto_en_mar_costa_atlantica(lat: float, lon: float) -> bool:
    """True si el punto es mar en los bbox SST Cantábrico/Atlántico."""
    if not _en_bbox_mar_atlantico(lat, lon):
        return False
    if punto_en_tierra(lon, lat, _anillos_ign()):
        return False
    if punto_en_tierra_mundo_atlantico(lat, lon):
        return False
    return True


def fraccion_mar_celda(lat: float, lon: float, half: float) -> float:
    """Proporción de muestras en mar (centro + esquinas + midpoints)."""
    h = float(half)
    muestras = [
        (lat, lon),
        (lat - h, lon - h),
        (lat + h, lon - h),
        (lat + h, lon + h),
        (lat - h, lon),
        (lat + h, lon),
        (lat, lon - h),
        (lat, lon + h),
    ]
    mar = sum(1 for la, lo in muestras if punto_en_mar_costa_atlantica(la, lo))
    return mar / len(muestras)


def densificar_celdas_mar(
    celdas: list[dict],
    *,
    paso: float,
    umbral_mar: float = 0.85,
    max_celdas: int | None = None,
    vecinos: tuple[tuple[int, int], ...] = (
        (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (-1, 1), (1, -1), (1, 1),
    ),
    max_pasadas: int = 10,
) -> list[dict]:
    """Rellena huecos de mar en la malla Cantábrico/Atlántico."""
    step = round(float(paso), 4)
    half = max(step * 0.48, 0.05)
    umbral = float(umbral_mar)
    idx: dict[tuple[float, float], float] = {}
    for c in celdas:
        if c.get("sst_c") is None:
            continue
        key = (round(float(c["lat"]), 4), round(float(c["lon"]), 4))
        if not punto_en_mar_costa_atlantica(key[0], key[1]):
            continue
        if fraccion_mar_celda(key[0], key[1], half) < umbral:
            continue
        idx[key] = float(c["sst_c"])
    if not idx:
        return []

    tope = int(max_celdas) if max_celdas and max_celdas > 0 else None
    for _ in range(max(1, int(max_pasadas))):
        if tope is not None and len(idx) >= tope:
            break
        candidatos: dict[tuple[float, float], list[tuple[float, float]]] = {}
        for la, lo in list(idx.keys()):
            for di, dj in vecinos:
                nk = (round(la + di * step, 4), round(lo + dj * step, 4))
                if nk in idx:
                    continue
                candidatos.setdefault(nk, []).append((idx[(la, lo)], 1.0))
        added = 0
        for key, vecinos in candidatos.items():
            if tope is not None and len(idx) >= tope:
                break
            if not vecinos:
                continue
            if not punto_en_mar_costa_atlantica(key[0], key[1]):
                continue
            if fraccion_mar_celda(key[0], key[1], half) < umbral:
                continue
            num = sum(val * w for val, w in vecinos)
            den = sum(w for _, w in vecinos)
            idx[key] = round(num / den, 2)
            added += 1
        if added == 0:
            break

    return [{"lat": la, "lon": lo, "sst_c": round(t, 2)} for (la, lo), t in idx.items()]
