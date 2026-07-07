"""Límites administrativos (CCAA y provincias) para el mapa Plotly."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go

from geo_bordes_clip import ensure_tierra
from geo_bordes_clip import TIERRA_FILE, ensure_tierra
from geo_es import CCAA_NOMBRES, CCAA_PROVINCIAS, ccaa_de_provincia, provincia_nombre_de_municipio

ROOT = Path(__file__).resolve().parent.parent
CCAA_FILE = ROOT / "data" / "geo" / "ccaa_bordes.json"
PROV_FILE = ROOT / "data" / "geo" / "provincias_bordes.json"
TIERRA_FILE = ROOT / "data" / "geo" / "espana_tierra.json"


def ensure_ccaa_bordes() -> None:
    if not CCAA_FILE.is_file():
        from build_geo_ccaa import build

        build()


def ensure_provincias_bordes() -> None:
    if not PROV_FILE.is_file():
        from build_geo_provincias import build

        build()


@lru_cache(maxsize=1)
def _bordes_ccaa() -> list[dict]:
    ensure_ccaa_bordes()
    data = json.loads(CCAA_FILE.read_text(encoding="utf-8"))
    return data.get("features", [])


@lru_cache(maxsize=1)
def _bordes_provincias() -> list[dict]:
    ensure_provincias_bordes()
    data = json.loads(PROV_FILE.read_text(encoding="utf-8"))
    return data.get("features", [])


@lru_cache(maxsize=1)
def _costa_espana_rings() -> list[dict]:
    ensure_tierra()
    data = json.loads(TIERRA_FILE.read_text(encoding="utf-8"))
    return data.get("rings", [])


def _ring_en_viewport(ring: dict, viewport: dict | None) -> bool:
    if not viewport:
        return True
    lat_min = viewport.get("lat_min")
    lat_max = viewport.get("lat_max")
    lon_min = viewport.get("lon_min")
    lon_max = viewport.get("lon_max")
    if lat_min is None or lat_max is None or lon_min is None or lon_max is None:
        return True
    lats = ring.get("lat") or []
    lons = ring.get("lon") or []
    return any(
        lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
        for lat, lon in zip(lats, lons)
    )


def _bordes() -> list[dict]:
    """Compatibilidad con tests anteriores."""
    return _bordes_ccaa()


def _features_ccaa_visibles(provincia_id: str | None) -> list[dict]:
    feats = _bordes_ccaa()
    if not provincia_id:
        return feats
    ccaa = ccaa_de_provincia(provincia_id)
    if not ccaa:
        return feats
    return [f for f in feats if f.get("id") == ccaa]


def _features_provincias_visibles(provincia_id: str | None) -> list[dict]:
    feats = _bordes_provincias()
    if not provincia_id:
        return feats
    ccaa = ccaa_de_provincia(provincia_id)
    if ccaa:
        provs = set(CCAA_PROVINCIAS.get(ccaa, []))
        return [f for f in feats if f.get("id") in provs]
    pid = str(provincia_id).zfill(2)
    return [f for f in feats if f.get("id") == pid]


def _add_lineas(
    fig: go.Figure,
    features: list[dict],
    *,
    legend_name: str,
    legendgroup: str,
    provincia_id: str | None,
    activo_por: str,
    color_base: str,
    width_base: float,
    color_activa: str,
    width_activa: float,
    etiqueta,
) -> None:
    activo_id = str(provincia_id or "").zfill(2) if activo_por == "provincia" else ccaa_de_provincia(provincia_id)
    leyenda = False
    for feat in features:
        feat_id = feat.get("id")
        activa = feat_id == activo_id
        color = color_activa if activa else color_base
        width = width_activa if activa else width_base
        nombre = etiqueta(feat)
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
                    name=legend_name if not leyenda else None,
                    legendgroup=legendgroup,
                    showlegend=not leyenda,
                    line=dict(color=color, width=width),
                    hovertemplate=f"{nombre}<extra></extra>",
                )
            )
            leyenda = True


def anadir_costa_ign(
    fig: go.Figure,
    viewport: dict | None = None,
    *,
    color: str = "#94a3b8",
    width: float = 0.8,
) -> None:
    """Costa IGN (alta precisión); sustituye la costa Natural Earth de Plotly."""
    for ring in _costa_espana_rings():
        if not _ring_en_viewport(ring, viewport):
            continue
        lats = ring.get("lat") or []
        lons = ring.get("lon") or []
        if len(lats) < 2:
            continue
        fig.add_trace(
            go.Scattergeo(
                lat=lats,
                lon=lons,
                mode="lines",
                legendgroup="costa",
                showlegend=False,
                line=dict(color=color, width=width),
                hoverinfo="skip",
            )
        )


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
    _add_lineas(
        fig,
        _features_ccaa_visibles(provincia_id),
        legend_name="Límites CCAA",
        legendgroup="ccaa",
        provincia_id=provincia_id,
        activo_por="ccaa",
        color_base=color_base,
        width_base=width_base,
        color_activa=color_activa,
        width_activa=width_activa,
        etiqueta=lambda f: f.get("nombre") or CCAA_NOMBRES.get(f.get("id") or "", f.get("id") or "CCAA"),
    )


def anadir_bordes_provincias(
    fig: go.Figure,
    provincia_id: str | None = None,
    *,
    color_base: str = "rgba(100, 116, 139, 0.38)",
    width_base: float = 0.65,
    color_activa: str = "rgba(125, 211, 252, 0.9)",
    width_activa: float = 1.1,
) -> None:
    """Dibuja contornos provinciales (línea más fina que CCAA)."""
    _add_lineas(
        fig,
        _features_provincias_visibles(provincia_id),
        legend_name="Límites provincias",
        legendgroup="provincias",
        provincia_id=provincia_id,
        activo_por="provincia",
        color_base=color_base,
        width_base=width_base,
        color_activa=color_activa,
        width_activa=width_activa,
        etiqueta=lambda f: (
            f.get("nombre")
            or provincia_nombre_de_municipio(f.get("id"))
            or f.get("id")
            or "Provincia"
        ),
    )
