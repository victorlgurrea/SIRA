"""Límites CCAA y provincias para el mapa."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.geo.ccaa_mapa import (  # noqa: E402
    _bordes,
    _bordes_provincias,
    anadir_bordes_ccaa,
    anadir_bordes_provincias,
    anadir_costa_ign,
)


def test_ccaa_bordes_json_tiene_comunidades_con_bordes():
    feats = _bordes()
    assert len(feats) >= 10
    ids = {f["id"] for f in feats}
    assert "VC" in ids
    assert all(f.get("rings") for f in feats)


def test_provincias_bordes_json_tiene_52_provincias():
    feats = _bordes_provincias()
    assert len(feats) == 52
    ids = {f["id"] for f in feats}
    assert "46" in ids
    assert "03" in ids


def test_anadir_bordes_ccaa_crea_trazas():
    fig = go.Figure()
    anadir_bordes_ccaa(fig, "46")
    assert len(fig.data) > 0
    assert any(getattr(t, "legendgroup", None) == "ccaa" for t in fig.data)


def test_anadir_bordes_provincias_crea_trazas():
    fig = go.Figure()
    anadir_bordes_provincias(fig, "46")
    assert len(fig.data) > 0
    assert any(getattr(t, "legendgroup", None) == "provincias" for t in fig.data)


def test_anadir_costa_ign_crea_trazas_y_filtra_viewport():
    fig = go.Figure()
    anadir_costa_ign(fig)
    assert len(fig.data) > 0
    assert all(getattr(t, "legendgroup", None) == "costa" for t in fig.data)

    fig_zoom = go.Figure()
    vp_valencia = {"lat_min": 38.0, "lat_max": 41.0, "lon_min": -1.5, "lon_max": 0.5}
    anadir_costa_ign(fig_zoom, vp_valencia)
    assert 0 < len(fig_zoom.data) < len(fig.data)
