"""Filtro de límites administrativos: solo fronteras interiores (sin costa)."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import requests

from geo_topojson import rings_from_geometry

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
TIERRA_FILE = ROOT / "data" / "geo" / "espana_tierra.json"
BORDER_URL = "https://unpkg.com/es-atlas/es/provinces.json"


def _clave_segmento(lon1: float, lat1: float, lon2: float, lat2: float, *, prec: int = 4) -> tuple:
    a = (round(lon1, prec), round(lat1, prec))
    b = (round(lon2, prec), round(lat2, prec))
    return (a, b) if a <= b else (b, a)


def _tramos_interiores(
    lats: list[float],
    lons: list[float],
    interiores: set[tuple],
    *,
    cerrado: bool = True,
) -> list[dict[str, list[float]]]:
    if len(lats) < 2:
        return []
    n = len(lats)
    limites = range(n) if cerrado else range(n - 1)

    tramos: list[dict[str, list[float]]] = []
    cur_lat: list[float] = []
    cur_lon: list[float] = []

    def _flush() -> None:
        nonlocal cur_lat, cur_lon
        if len(cur_lat) >= 2:
            tramos.append({"lat": cur_lat, "lon": cur_lon})
        cur_lat, cur_lon = [], []

    for i in limites:
        j = (i + 1) % n
        lat1, lon1 = float(lats[i]), float(lons[i])
        lat2, lon2 = float(lats[j]), float(lons[j])
        if _clave_segmento(lon1, lat1, lon2, lat2) in interiores:
            if not cur_lat:
                cur_lat.append(lat1)
                cur_lon.append(lon1)
            cur_lat.append(lat2)
            cur_lon.append(lon2)
        else:
            _flush()
    _flush()
    return tramos


def solo_bordes_interiores(
    features: list[dict],
    *,
    umbral_costa_km: float = 18.0,
) -> list[dict]:
    """Conserva solo fronteras entre unidades administrativas, lejos del litoral."""
    conteo: dict[tuple, int] = {}
    for feat in features:
        for ring in feat.get("rings", []):
            lats = ring.get("lat") or []
            lons = ring.get("lon") or []
            n = len(lats)
            if n < 2:
                continue
            for i in range(n):
                j = (i + 1) % n
                key = _clave_segmento(float(lons[i]), float(lats[i]), float(lons[j]), float(lats[j]))
                conteo[key] = conteo.get(key, 0) + 1

    candidatos = {k for k, v in conteo.items() if v >= 2}
    if umbral_costa_km > 0:
        borde_pts = [(lon, lat) for ring in anillos_tierra() for lon, lat in ring]
        interiores = {k for k in candidatos if not _cerca_costa_nacional(k, borde_pts, umbral_costa_km)}
    else:
        interiores = candidatos

    out: list[dict] = []
    for feat in features:
        rings: list[dict[str, list[float]]] = []
        for ring in feat.get("rings", []):
            rings.extend(_tramos_interiores(ring.get("lat") or [], ring.get("lon") or [], interiores))
        if rings:
            out.append({**{k: v for k, v in feat.items() if k != "rings"}, "rings": rings})
    return out


def _dist_costa_km(lon: float, lat: float, borde_pts: list[tuple[float, float]]) -> float:
    from sismos import distancia_km

    mejor = float("inf")
    for blon, blat in borde_pts:
        if abs(blon - lon) > 0.3 or abs(blat - lat) > 0.3:
            continue
        mejor = min(mejor, distancia_km(lat, lon, blat, blon))
    if mejor == float("inf"):
        for blon, blat in borde_pts:
            mejor = min(mejor, distancia_km(lat, lon, blat, blon))
    return mejor


def _cerca_costa_nacional(
    segmento: tuple,
    borde_pts: list[tuple[float, float]],
    umbral_km: float,
) -> bool:
    lon1, lat1 = segmento[0]
    lon2, lat2 = segmento[1]
    mid_lon = (lon1 + lon2) / 2
    mid_lat = (lat1 + lat2) / 2
    dists = (
        _dist_costa_km(lon1, lat1, borde_pts),
        _dist_costa_km(lon2, lat2, borde_pts),
        _dist_costa_km(mid_lon, mid_lat, borde_pts),
    )
    return min(dists) < umbral_km


# --- utilidades tierra (tests / referencia) ---

def _punto_en_poligono(lon: float, lat: float, anillo: list[list[float]]) -> bool:
    dentro = False
    n = len(anillo)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi):
            dentro = not dentro
        j = i
    return dentro


def punto_en_tierra(lon: float, lat: float, tierra: list[list[list[float]]]) -> bool:
    return any(_punto_en_poligono(lon, lat, anillo) for anillo in tierra)


def segmento_en_tierra(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    tierra: list[list[list[float]]],
) -> bool:
    if punto_en_tierra(lon1, lat1, tierra) and punto_en_tierra(lon2, lat2, tierra):
        return True
    return punto_en_tierra((lon1 + lon2) / 2, (lat1 + lat2) / 2, tierra)


def _extraer_cadenas(
    lats: list[float],
    lons: list[float],
    tierra: list[list[list[float]]],
    *,
    cerrado: bool = True,
) -> list[dict[str, list[float]]]:
    if len(lats) < 2:
        return []
    n = len(lats)
    limites = range(n) if cerrado else range(n - 1)

    tramos: list[dict[str, list[float]]] = []
    cur_lat: list[float] = []
    cur_lon: list[float] = []

    def _flush() -> None:
        nonlocal cur_lat, cur_lon
        if len(cur_lat) >= 2:
            tramos.append({"lat": cur_lat, "lon": cur_lon})
        cur_lat, cur_lon = [], []

    for i in limites:
        j = (i + 1) % n
        lat1, lon1 = float(lats[i]), float(lons[i])
        lat2, lon2 = float(lats[j]), float(lons[j])
        if segmento_en_tierra(lon1, lat1, lon2, lat2, tierra):
            if not cur_lat:
                cur_lat.append(lat1)
                cur_lon.append(lon1)
            cur_lat.append(lat2)
            cur_lon.append(lon2)
        else:
            _flush()
    _flush()
    return tramos


def recortar_anillo(
    lats: list[float],
    lons: list[float],
    tierra: list[list[list[float]]],
) -> list[dict[str, list[float]]]:
    """Divide un anillo en tramos que no atraviesan mar."""
    return _extraer_cadenas(lats, lons, tierra, cerrado=True)


def recortar_feature_rings(
    rings: list[dict[str, list[float]]],
    tierra: list[list[list[float]]],
) -> list[dict[str, list[float]]]:
    out: list[dict[str, list[float]]] = []
    for ring in rings:
        lats = ring.get("lat") or []
        lons = ring.get("lon") or []
        out.extend(recortar_anillo(lats, lons, tierra))
    return out


def build_tierra() -> Path:
    r = requests.get(BORDER_URL, timeout=120)
    r.raise_for_status()
    topology = r.json()
    geometry = topology["objects"]["border"]["geometries"][0]
    rings = rings_from_geometry(topology, geometry)
    payload = {
        "fuente": "IGN — contorno España (es-atlas border)",
        "url": BORDER_URL,
        "rings": [{"lat": [pt[1] for pt in ring], "lon": [pt[0] for pt in ring]} for ring in rings],
    }
    TIERRA_FILE.parent.mkdir(parents=True, exist_ok=True)
    TIERRA_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("España tierra: %d polígonos → %s", len(rings), TIERRA_FILE)
    return TIERRA_FILE


def ensure_tierra() -> None:
    if not TIERRA_FILE.is_file():
        build_tierra()


@lru_cache(maxsize=1)
def anillos_tierra() -> list[list[list[float]]]:
    ensure_tierra()
    data = json.loads(TIERRA_FILE.read_text(encoding="utf-8"))
    return [
        [[lon, lat] for lon, lat in zip(ring["lon"], ring["lat"])]
        for ring in data.get("rings", [])
    ]
