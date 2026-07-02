"""Genera data/geo/ccaa_bordes.json a partir de contornos provinciales (perímetro exterior)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from geo_bordes_clip import contorno_exterior
from geo_es import CCAA_NOMBRES, CCAA_PROVINCIAS

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo" / "ccaa_bordes.json"
PROV_FILE = ROOT / "data" / "geo" / "provincias_bordes.json"


def build() -> Path:
    if not PROV_FILE.is_file():
        from build_geo_provincias import build as build_provincias

        build_provincias()

    prov_data = json.loads(PROV_FILE.read_text(encoding="utf-8"))
    prov_by_id = {f["id"]: f for f in prov_data.get("features", [])}

    features: list[dict] = []
    for ccaa_id, prov_ids in CCAA_PROVINCIAS.items():
        group = [prov_by_id[pid] for pid in prov_ids if pid in prov_by_id]
        if not group:
            log.warning("CCAA %s sin provincias en provincias_bordes.json", ccaa_id)
            continue
        rings = contorno_exterior(group)
        if rings:
            features.append(
                {
                    "id": ccaa_id,
                    "nombre": CCAA_NOMBRES.get(ccaa_id, ccaa_id),
                    "rings": rings,
                }
            )

    features.sort(key=lambda x: x["id"])
    payload = {
        "fuente": "Perímetro exterior CCAA derivado de provincias_bordes.json (IGN es-atlas)",
        "url": str(PROV_FILE.relative_to(ROOT)).replace("\\", "/"),
        "features": features,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("CCAA bordes: %d comunidades → %s", len(features), OUT)
    return OUT


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build()
