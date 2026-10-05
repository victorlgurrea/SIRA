"""Payload del mapa LAB unificado (provincias T.máx + meta radar)."""
from __future__ import annotations

import logging
from typing import Any

import requests

from sira.infrastructure.http.client import read_dashboard
from sira.infrastructure.sources.meteo.weathernext import construir_weathernext_ccaa_cache

log = logging.getLogger(__name__)


def _color_temp(temp_c: float | None) -> str:
    """Misma escala que el mapa Plotly LAB (figures.color_temp)."""
    if temp_c is None:
        return "rgba(100,116,139,0.35)"
    stops = [
        (-20.0, "#f8fafc"),
        (15.0, "#fde047"),
        (25.0, "#f59e0b"),
        (32.0, "#f97316"),
        (38.0, "#ef4444"),
        (50.0, "#b91c1c"),
    ]
    color = stops[0][1]
    for threshold, c in stops:
        if temp_c >= threshold:
            color = c
    return color


def _ring_to_lonlat(ring: dict) -> list[list[float]]:
    lats = ring.get("lat") or []
    lons = ring.get("lon") or []
    n = min(len(lats), len(lons))
    coords = [[float(lons[i]), float(lats[i])] for i in range(n)]
    if len(coords) >= 3 and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _termico_para_lab() -> dict:
    d = read_dashboard()
    termico_ing = d.get("termico_ccaa") if isinstance(d.get("termico_ccaa"), dict) else {}
    try:
        wn_ccaa = construir_weathernext_ccaa_cache()
    except Exception:  # noqa: BLE001
        log.exception("construir_weathernext_ccaa_cache en lab_mapa")
        wn_ccaa = {"provincias": []}
    n_wn = sum(
        1
        for p in (wn_ccaa.get("provincias") or [])
        if isinstance(p, dict) and p.get("temp_max_c") is not None
    )
    n_ing = sum(
        1
        for p in (termico_ing.get("provincias") or [])
        if isinstance(p, dict) and p.get("temp_max_c") is not None
    )
    return wn_ccaa if n_wn >= max(20, n_ing) else (termico_ing or wn_ccaa)


def _rainviewer_frame() -> dict[str, Any] | None:
    try:
        rv = requests.get(
            "https://api.rainviewer.com/public/weather-maps.json",
            timeout=12,
        )
        if not rv.ok:
            return None
        payload = rv.json()
        past = (payload.get("radar") or {}).get("past") or []
        frame = past[-1] if past else None
        if not frame or not frame.get("path"):
            return None
        return {
            "host": payload.get("host") or "https://tilecache.rainviewer.com",
            "path": frame["path"],
            "time": frame.get("time"),
        }
    except (requests.RequestException, ValueError, TypeError) as exc:
        log.warning("RainViewer frame falló: %s", exc)
        return None


def lab_mapa_geojson(*, provincia_id: str | None = None) -> dict[str, Any]:
    """GeoJSON de provincias + frame RainViewer para el mapa Leaflet LAB."""
    # Import perezoso: charts vive en el proceso dashboard.
    from charts.figures import _prov_rings

    termico = _termico_para_lab()
    por_prov = {
        str(p.get("provincia_id") or "").zfill(2): p
        for p in (termico.get("provincias") or [])
        if isinstance(p, dict)
    }
    pid_sel = str(provincia_id or "").zfill(2) if provincia_id else ""
    features: list[dict] = []
    for pid, feat in _prov_rings().items():
        row = por_prov.get(pid, {})
        tmax = row.get("temp_max_c")
        try:
            tmax_f = float(tmax) if tmax is not None else None
        except (TypeError, ValueError):
            tmax_f = None
        precip = row.get("precip_24h_mm")
        try:
            precip_f = float(precip) if precip is not None else None
        except (TypeError, ValueError):
            precip_f = None
        rings = [r for r in (feat.get("rings") or []) if len((r or {}).get("lat") or []) >= 3]
        if not rings:
            continue
        # Anillo principal (mismo criterio que Plotly).
        ring = max(rings, key=lambda r: len(r.get("lat") or []))
        coords = _ring_to_lonlat(ring)
        if len(coords) < 4:
            continue
        nombre = str(feat.get("nombre") or row.get("provincia") or pid)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": pid,
                    "nombre": nombre,
                    "temp_max_c": tmax_f,
                    "precip_24h_mm": precip_f,
                    "color": _color_temp(tmax_f),
                    "activa": pid == pid_sel,
                    "fuente": str(row.get("fuente") or "—"),
                },
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )

    rainviewer = _rainviewer_frame()
    return {
        "ok": bool(features),
        "type": "FeatureCollection",
        "features": features,
        "rainviewer": rainviewer,
        "provincia_id": pid_sel or None,
        "fuente_termico": "Open-Meteo",
        "fuente_radar": "RainViewer" if rainviewer else None,
    }
