"""Fronteras administrativas interiores (sin costa)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from geo_bordes_clip import solo_bordes_interiores  # noqa: E402


def test_solo_bordes_interiores_omite_costa_exterior():
    a = {
        "id": "A",
        "nombre": "A",
        "rings": [{"lat": [40, 40, 39, 39, 40], "lon": [-1, 0, 0, -1, -1]}],
    }
    b = {
        "id": "B",
        "nombre": "B",
        "rings": [{"lat": [40, 40, 39, 39, 40], "lon": [0, 1, 1, 0, 0]}],
    }
    out = solo_bordes_interiores([a, b], umbral_costa_km=0)
    by_id = {f["id"]: f for f in out}
    assert "A" in by_id and "B" in by_id
    a_lons = [lo for r in by_id["A"]["rings"] for lo in r["lon"]]
    b_lons = [lo for r in by_id["B"]["rings"] for lo in r["lon"]]
    assert 0 in a_lons or 0.0 in a_lons
    assert 1 not in a_lons and 1 not in b_lons


def test_provincias_contorno_completo_llega_a_costa():
    import json

    data = json.loads((ROOT / "data" / "geo" / "provincias_bordes.json").read_text(encoding="utf-8"))
    castellon = next(f for f in data["features"] if f["id"] == "12")
    lons = [lo for r in castellon["rings"] for lo in r["lon"]]
    assert max(lons) > 0.3


def test_ccaa_contorno_completo_llega_a_costa():
    import json

    data = json.loads((ROOT / "data" / "geo" / "ccaa_bordes.json").read_text(encoding="utf-8"))
    vc = next(f for f in data["features"] if f["id"] == "VC")
    lons = [lo for r in vc["rings"] for lo in r["lon"]]
    assert max(lons) > 0.3
