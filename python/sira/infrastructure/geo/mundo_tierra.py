"""
Máscara de tierra a escala mundial (Natural Earth 50m vía world-atlas).

IGN solo cubre España (ver bordes_clip.py) y las heurísticas de
mar_mediterraneo.py solo afinan el Mediterráneo occidental (Francia,
Magreb, Córcega/Cerdeña). Para el Mediterráneo central/oriental (Italia,
Adriático, Jónico, Egeo, Turquía, Chipre, Levante...) usamos un contorno
de tierra genérico, filtrado al bbox del Mediterráneo para no cargar los
~1400 polígonos del planeta.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import requests

from sira.infrastructure.geo import REPO_ROOT as ROOT
from sira.infrastructure.geo.topojson import rings_from_geometry

log = logging.getLogger(__name__)

TIERRA_FILE = ROOT / "data" / "geo" / "mundo_tierra_mediterraneo.json"
LAND_URL = "https://unpkg.com/world-atlas@2/land-50m.json"

# lon_min, lat_min, lon_max, lat_max — bbox amplio del Mediterráneo + margen.
BBOX: tuple[float, float, float, float] = (-10.0, 27.0, 37.5, 47.0)


def _interseca_bbox(ring: list[list[float]]) -> bool:
    lon_min, lat_min, lon_max, lat_max = BBOX
    r_lon_min = min(p[0] for p in ring)
    r_lon_max = max(p[0] for p in ring)
    r_lat_min = min(p[1] for p in ring)
    r_lat_max = max(p[1] for p in ring)
    return not (r_lon_max < lon_min or r_lon_min > lon_max or r_lat_max < lat_min or r_lat_min > lat_max)


def build_tierra_mediterraneo() -> Path:
    r = requests.get(LAND_URL, timeout=120)
    r.raise_for_status()
    topology = r.json()
    geometry = topology["objects"]["land"]["geometries"][0]
    rings = rings_from_geometry(topology, geometry)
    rings_med = [ring for ring in rings if _interseca_bbox(ring)]
    payload = {
        "fuente": "Natural Earth 50m (world-atlas land-50m.json)",
        "url": LAND_URL,
        "bbox": list(BBOX),
        "rings": [
            {"lat": [p[1] for p in ring], "lon": [p[0] for p in ring]}
            for ring in rings_med
        ],
    }
    TIERRA_FILE.parent.mkdir(parents=True, exist_ok=True)
    TIERRA_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    log.info(
        "Mundo tierra (Mediterráneo): %d/%d polígonos → %s",
        len(rings_med), len(rings), TIERRA_FILE,
    )
    return TIERRA_FILE


def ensure_tierra_mediterraneo() -> None:
    if not TIERRA_FILE.is_file():
        build_tierra_mediterraneo()


@lru_cache(maxsize=1)
def anillos_tierra_mediterraneo() -> list[list[list[float]]]:
    ensure_tierra_mediterraneo()
    data = json.loads(TIERRA_FILE.read_text(encoding="utf-8"))
    return [
        [[lon, lat] for lon, lat in zip(ring["lon"], ring["lat"])]
        for ring in data.get("rings", [])
    ]


# --- índice espacial (bandas de latitud) ---
#
# Uno de los anillos (Eurasia+África fusionadas) tiene ~10.600 vértices y su
# bbox cubre casi todo el planeta; sin índice, cada consulta punto-en-tierra
# haría un ray-casting completo contra esos ~10.600 vértices y la ingesta con
# el Mediterráneo entero (decenas de miles de celdas candidatas) tardaría
# minutos. Se indexan las aristas por banda de latitud para que cada consulta
# solo compare las aristas que realmente cruzan esa banda.
_BANDA_DEG = 0.25


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
    for ring in anillos_tierra_mediterraneo():
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        bbox = (min(lons), min(lats), max(lons), max(lats))
        salida.append((bbox, _construir_indice(ring)))
    return salida


def punto_en_tierra_mundo(lat: float, lon: float) -> bool:
    """True si (lat, lon) cae en tierra según el contorno mundial indexado."""
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
