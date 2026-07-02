"""Recorte de bordes administrativos a tierra firme."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from geo_bordes_clip import (  # noqa: E402
    anillos_tierra,
    punto_en_tierra,
    recortar_anillo,
    segmento_en_tierra,
)


def test_punto_castello_ciudad_en_tierra():
    tierra = anillos_tierra()
    assert punto_en_tierra(-0.037, 39.986, tierra)


def test_segmento_mar_castellon_recortado():
    tierra = anillos_tierra()
    # Cordón simplificado que atraviesa mar (este de la costa)
    lats = [40.0, 40.0, 40.0]
    lons = [0.0, 0.25, 0.5]
    assert not segmento_en_tierra(0.0, 40.0, 0.25, 40.0, tierra)
    tramos = recortar_anillo(lats, lons, tierra)
    assert tramos == [] or all(len(t["lat"]) >= 2 for t in tramos)


def test_recorte_devuelve_tramos_validos():
    tierra = anillos_tierra()
    lats = [39.99, 39.99, 40.05, 40.05, 39.99]
    lons = [-0.10, -0.04, -0.04, -0.10, -0.10]
    tramos = recortar_anillo(lats, lons, tierra)
    assert tramos
    assert all(len(t["lat"]) == len(t["lon"]) >= 2 for t in tramos)
