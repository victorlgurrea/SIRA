"""Rejilla visual SST en mapa."""
from __future__ import annotations

from charts.map_layers import rejilla_visual_sst


def test_rejilla_visual_agrupa_celdas_densas():
    celdas = [
        {"lat": 41.00 + i * 0.02, "lon": -9.00 + j * 0.02, "sst_c": 20.0 + i + j}
        for i in range(6)
        for j in range(6)
    ]
    out = rejilla_visual_sst(celdas, paso=0.12)
    assert 0 < len(out) < len(celdas)
