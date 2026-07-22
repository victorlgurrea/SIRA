"""Genera data/geo/aemet_zonas_aviso.json desde el shapefile oficial Meteoalerta."""
from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path

import requests
import shapefile
from pyproj import Transformer

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "geo" / "aemet_zonas_aviso.json"
SOURCE_URL = (
    "https://www.aemet.es/documentos/es/eltiempo/prediccion/avisos/"
    "plan_meteoalerta/AEMET-meteoalerta-delimitacion-zonas.zip"
)
SHAPEFILES = (
    "AEMET-meteoalerta-v6-zonas-32630",
    "AEMET-meteoalerta-v6-zonas-costeras-32630",
)


def _simplify_ring(coords: list[list[float]], *, step: int = 2, precision: int = 3) -> list[list[float]]:
    """Reduce vértices: muestreo + redondeo (~100 m) para JSON liviano."""
    if len(coords) <= 4:
        out = coords
    else:
        out = [coords[0]]
        for i in range(1, len(coords) - 1, max(1, step)):
            out.append(coords[i])
        if out[-1] != coords[-1]:
            out.append(coords[-1])
    factor = 10**precision
    return [[round(lon * factor) / factor, round(lat * factor) / factor] for lon, lat in out]


def _rings_from_shape(shape, transformer: Transformer) -> list[dict]:
    rings: list[dict] = []
    parts = list(shape.parts) + [len(shape.points)]
    for i in range(len(shape.parts)):
        pts = shape.points[parts[i] : parts[i + 1]]
        if len(pts) < 3:
            continue
        wgs = [transformer.transform(x, y) for x, y in pts]
        simp = _simplify_ring(wgs, step=3 if len(wgs) > 120 else 2)
        if len(simp) >= 3:
            rings.append({"lat": [p[1] for p in simp], "lon": [p[0] for p in simp]})
    return rings


def _record_dict(sf: shapefile.Reader, record) -> dict:
    names = [f[0] for f in sf.fields[1:]]
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in zip(names, record)}


def build() -> Path:
    r = requests.get(SOURCE_URL, timeout=180)
    r.raise_for_status()
    tmp = OUT.parent / "_aemet_zonas.zip"
    tmp.write_bytes(r.content)

    transformer = Transformer.from_crs("EPSG:32630", "EPSG:4326", always_xy=True)
    features: list[dict] = []
    seen: set[str] = set()

    with zipfile.ZipFile(tmp) as zf:
        zf.extractall(OUT.parent / "_aemet_zonas_src")

    src_dir = OUT.parent / "_aemet_zonas_src"
    for base in SHAPEFILES:
        shp = next(src_dir.rglob(f"{base}.shp"), None)
        if not shp:
            log.warning("No encontrado: %s", base)
            continue
        sf = shapefile.Reader(str(shp), encoding="latin1")
        try:
            for sr in sf.iterShapeRecords():
                rec = _record_dict(sf, sr.record)
                cod = str(rec.get("COD_Z") or "").strip()
                if not cod or cod in seen:
                    continue
                rings = _rings_from_shape(sr.shape, transformer)
                if not rings:
                    continue
                seen.add(cod)
                features.append(
                    {
                        "id": cod,
                        "nombre": rec.get("NOM_Z") or cod,
                        "provincia_id": str(rec.get("COD_PROV") or "").zfill(2)[:2] or None,
                        "provincia": rec.get("NOM_PROV") or "",
                        "ccaa_id": str(rec.get("COD_CCAA") or "").strip() or None,
                        "ccaa": rec.get("NOM_CCAA") or "",
                        "costera": base.endswith("costeras-32630"),
                        "rings": rings,
                    }
                )
        finally:
            sf.close()

    tmp.unlink(missing_ok=True)
    for p in src_dir.rglob("*"):
        if p.is_file():
            p.unlink()
    if src_dir.exists():
        for d in sorted(src_dir.rglob("*"), reverse=True):
            if d.is_dir():
                d.rmdir()
        try:
            src_dir.rmdir()
        except OSError:
            pass

    features.sort(key=lambda f: f["id"])
    payload = {
        "fuente": "AEMET Plan Meteoalerta — delimitación oficial de zonas de aviso",
        "url": SOURCE_URL,
        "crs_origen": "EPSG:32630",
        "features": features,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("Zonas AEMET: %d zonas → %s (%.1f KB)", len(features), OUT, OUT.stat().st_size / 1024)
    return OUT


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build()
