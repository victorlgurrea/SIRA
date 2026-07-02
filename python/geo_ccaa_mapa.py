"""Límites de comunidades autónomas para el mapa Plotly."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go

from geo_es import CCAA_NOMBRES, ccaa_de_provincia

ROOT = Path(__file__).resolve().parent.parent
BORDES_FILE = ROOT / "data" / "geo" / "ccaa_bordes.json"


def ensure_ccaa_bordes() -> None:
    if not BORDES_FILE.is_file():
        from build_geo_ccaa import build

        build()


@lru_cache(maxsize=1)
def _bordes() -> list[dict]:
    ensure_ccaa_bordes()
    data = json.loads(BORDES_FILE.read_text(encoding="utf-8"))
    return data.get("features", [])


def anadir_bordes_ccaa(
    fig: go.Figure,
    provincia_id: str | None = None,
    *,
    color_base: str = "rgba(148, 163, 184, 0.55)",
    width_base: float = 1.2,
    color_activa: str = "rgba(34, 211, 238, 0.95)",
    width_activa: float = 2.4,
) -> None:
    """Dibuja contornos CCAA; resalta la comunidad de la provincia seleccionada."""
    ccaa_activa = ccaa_de_provincia(provincia_id)
    leyenda = False
    for feat in _bordes():
        ccaa_id = feat.get("id")
        activa = ccaa_id == ccaa_activa
        color = color_activa if activa else color_base
        width = width_activa if activa else width_base
        nombre = feat.get("nombre") or CCAA_NOMBRES.get(ccaa_id or "", ccaa_id or "CCAA")
        for ring in feat.get("rings", []):
            lats = ring.get("lat") or []
            lons = ring.get("lon") or []
            if len(lats) < 2:
                continue
            fig.add_trace(
                go.Scattergeo(
                    lat=lats,
                    lon=lons,
                    mode="lines",
                    name="Límites CCAA" if not leyenda else None,
                    legendgroup="ccaa",
                    showlegend=not leyenda,
                    line=dict(color=color, width=width),
                    hovertemplate=f"{nombre}<extra></extra>",
                )
            )
            leyenda = True
