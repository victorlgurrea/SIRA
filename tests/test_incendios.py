"""Tests de incendios.py — clustering y radio por extensión espacial."""
from __future__ import annotations

from sira.infrastructure.sources.fire.firms import (
    _agrupar_focos,
    _foco_desde_grupo,
    en_espana,
    radio_desde_area_km2,
)


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


def test_en_espana_filtra_paises_vecinos():
    # España (Madrid)
    assert en_espana(40.4168, -3.7038) is True
    # Portugal (Lisboa)
    assert en_espana(38.7223, -9.1393) is False
    # Francia (Marsella)
    assert en_espana(43.2965, 5.3698) is False
    # Marruecos (Rabat)
    assert en_espana(34.0209, -6.8416) is False


def test_foco_radio_no_infla_por_frp():
    """FRP alto no debe generar círculos enormes (antes FRP×0.15 → miles de km²)."""
    grupo = [
        {
            "lat": 39.87,
            "lon": -0.24,
            "scan_km": 0.75,
            "track_km": 0.75,
            "area_km2": 0.56,
            "frp_mw": 500.0,
            "satelite": "N20",
            "timestamp": "2026-07-27T03:00:00",
        },
        {
            "lat": 39.88,
            "lon": -0.23,
            "scan_km": 0.8,
            "track_km": 0.8,
            "area_km2": 0.64,
            "frp_mw": 800.0,
            "satelite": "N20",
            "timestamp": "2026-07-27T03:15:00",
        },
    ]
    foco = _foco_desde_grupo(grupo, 0)
    assert foco["frp_mw"] == 1300.0
    assert foco["n_detecciones"] == 2
    # Extensión ~1–2 km + margen píxel → radio acotado, no ~32 km
    assert foco["radio_km"] <= 8.0
    assert foco["area_km2"] < 250.0


def test_foco_unico_respeta_radio_minimo():
    grupo = [
        {
            "lat": 40.0,
            "lon": -3.0,
            "scan_km": 0.5,
            "track_km": 0.5,
            "area_km2": 0.25,
            "frp_mw": 5.0,
            "satelite": "NPP",
            "timestamp": "2026-07-27T01:00:00",
        }
    ]
    foco = _foco_desde_grupo(grupo, 0)
    assert foco["radio_km"] >= 1.5
