"""Límites CCAA para el mapa."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from geo_ccaa_mapa import _bordes, anadir_bordes_ccaa  # noqa: E402


def test_ccaa_bordes_json_tiene_19_comunidades():
    feats = _bordes()
    assert len(feats) == 19
    ids = {f["id"] for f in feats}
    assert "VC" in ids
    assert all(f.get("rings") for f in feats)


def test_anadir_bordes_ccaa_crea_trazas():
    fig = go.Figure()
    anadir_bordes_ccaa(fig, "46")
    assert len(fig.data) > 0
    assert any(getattr(t, "legendgroup", None) == "ccaa" for t in fig.data)
