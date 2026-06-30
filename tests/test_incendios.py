"""Tests de incendios.py — clustering por transitividad."""
from __future__ import annotations

from incendios import _agrupar_focos, radio_desde_area_km2


def test_radio_desde_area():
    r = radio_desde_area_km2(10)
    assert 1.5 <= r <= 35.0


def test_clustering_transitivo():
    # A-B y B-C cercanos → un solo grupo con A,B,C
    puntos = [
        {"lat": 40.0, "lon": -3.0, "area_km2": 1},
        {"lat": 40.02, "lon": -3.01, "area_km2": 1},
        {"lat": 40.04, "lon": -3.02, "area_km2": 1},
        {"lat": 41.0, "lon": -1.0, "area_km2": 1},
    ]
    grupos = _agrupar_focos(puntos, sep_km=4.0)
    assert len(grupos) == 2
    assert max(len(g) for g in grupos) == 3


def test_clustering_aislado():
    puntos = [
        {"lat": 40.0, "lon": -3.0, "area_km2": 1},
        {"lat": 42.0, "lon": -5.0, "area_km2": 1},
    ]
    grupos = _agrupar_focos(puntos, sep_km=4.0)
    assert len(grupos) == 2
