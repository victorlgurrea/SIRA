"""Selección del payload dashboard más reciente."""
from __future__ import annotations

from sira.infrastructure.http.dashboard_fetch import _pick_fresher


def test_pick_fresher_elige_generado_en_mas_nuevo():
    old = {
        "generado_en": "2026-09-02T10:40:00+00:00",
        "sismos": [{"id": 1}],
        "sst_med_grid": {"celdas": [{"lat": 1, "lon": 1, "sst_c": 20}]},
    }
    new = {
        "generado_en": "2026-09-03T05:57:00+00:00",
        "sismos": [{"id": 1}, {"id": 2}],
        "sst_med_grid": {"celdas": [{"lat": 1, "lon": 1, "sst_c": 20}]},
        "sst_atl_grid": {"celdas": [{"lat": 2, "lon": 2, "sst_c": 18}]},
    }
    assert _pick_fresher(old, new) is new
    assert _pick_fresher(new, old) is new
