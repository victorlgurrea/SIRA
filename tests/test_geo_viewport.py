"""Viewport del mapa según nivel geográfico."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from geo_es import (  # noqa: E402
    ccaa_de_provincia,
    viewport_ccaa,
    viewport_municipio,
    viewport_para_nivel,
    viewport_provincia,
)


def _span(vp: dict) -> tuple[float, float]:
    return vp["lat_max"] - vp["lat_min"], vp["lon_max"] - vp["lon_min"]


def test_ccaa_de_provincia_valencia():
    assert ccaa_de_provincia("46") == "VC"
    assert ccaa_de_provincia("03") == "VC"


def test_zoom_municipio_mas_cercano_que_provincia():
    muni = viewport_municipio("46250")
    prov = viewport_provincia("46")
    assert _span(muni)[0] < _span(prov)[0]
    assert _span(muni)[1] < _span(prov)[1]


def test_zoom_provincia_mas_cercano_que_ccaa():
    prov = viewport_provincia("46")
    ccaa = viewport_ccaa("46")
    assert _span(prov)[0] <= _span(ccaa)[0]
    assert _span(prov)[1] <= _span(ccaa)[1]


def test_viewport_provincia_alejado_es_mas_amplio():
    cerca = viewport_provincia("46", alejado=False)
    lejos = viewport_provincia("46", alejado=True)
    assert _span(lejos)[0] > _span(cerca)[0]
    assert _span(lejos)[1] > _span(cerca)[1]


def test_viewport_fit_contenedor_ensancha_encuadre_vertical():
    from geo_es import viewport_fit_contenedor

    vp = {
        "lat_centro": 39.5,
        "lon_centro": -0.5,
        "lat_min": 38.0,
        "lat_max": 41.0,
        "lon_min": -1.0,
        "lon_max": 0.0,
        "nivel": "ccaa",
    }
    out = viewport_fit_contenedor(vp, aspect=1.65)
    assert (out["lon_max"] - out["lon_min"]) > (vp["lon_max"] - vp["lon_min"])


def test_viewport_ccaa_alejado_cubre_comunidad_completa():
    import json

    vp = viewport_ccaa("46", alejado=True)
    data = json.loads((ROOT / "data" / "geo" / "ccaa_bordes.json").read_text(encoding="utf-8"))
    vc = next(f for f in data["features"] if f["id"] == "VC")
    lats = [la for r in vc["rings"] for la in r["lat"]]
    lons = [lo for r in vc["rings"] for lo in r["lon"]]
    assert vp["lat_min"] <= min(lats)
    assert vp["lat_max"] >= max(lats)
    assert vp["lon_min"] <= min(lons)
    assert vp["lon_max"] >= max(lons)
    assert _span(viewport_ccaa("46", alejado=True)) > _span(viewport_ccaa("46", alejado=False))


def test_viewport_provincia_centro_pone_estrella_en_medio():
    from geo_es import viewport_provincia_centro

    lat, lon = 39.47, -0.38
    vp = viewport_provincia_centro("46", lat, lon, alejado=True)
    assert abs(vp["lat_centro"] - lat) < 1e-9
    assert abs(vp["lon_centro"] - lon) < 1e-9
    assert vp.get("centrar_obs") is True


def test_viewport_ccaa_centro_pone_localidad_en_medio_y_cubre_ccaa():
    from geo_es import viewport_ccaa_centro
    import math

    lat, lon = 37.39, -5.98  # Sevilla
    vp = viewport_ccaa_centro("41", lat, lon, alejado=True)
    lat_span, lon_span = _span(vp)
    geo_aspect = (lon_span * math.cos(math.radians(lat))) / lat_span
    assert abs(vp["lat_centro"] - lat) < 1e-9
    assert abs(vp["lon_centro"] - lon) < 1e-9
    assert vp.get("nivel") == "ccaa"
    assert vp.get("centrar_obs") is True
    assert geo_aspect >= 2.7


def test_viewport_fit_observacion_reduce_lat_si_lon_recortado():
    from geo_es import viewport_fit_observacion

    vp = {
        "lat_centro": 39.47,
        "lon_centro": -0.38,
        "lat_min": 36.0,
        "lat_max": 43.35,
        "lon_min": -10.0,
        "lon_max": 8.0,
        "nivel": "ccaa",
        "centrar_obs": True,
    }
    out = viewport_fit_observacion(vp, aspect=2.85)
    lat_span = out["lat_max"] - out["lat_min"]
    lon_span = out["lon_max"] - out["lon_min"]
    import math

    geo_aspect = (lon_span * math.cos(math.radians(out["lat_centro"]))) / lat_span
    assert geo_aspect >= 2.7
    assert abs(out["lat_centro"] - 39.47) < 1e-9
    assert abs(out["lon_centro"] - (-0.38)) < 1e-9


def test_viewport_ccaa_centro_mas_amplio_que_provincia():
    from geo_es import viewport_ccaa_centro, viewport_provincia_centro

    lat, lon = 37.39, -5.98
    ccaa = viewport_ccaa_centro("41", lat, lon, alejado=True)
    prov = viewport_provincia_centro("41", lat, lon, alejado=True)
    assert _span(ccaa)[0] > _span(prov)[0]
    assert _span(ccaa)[1] > _span(prov)[1]


def test_viewport_para_nivel():
    muni = viewport_para_nivel("municipio", "46", "46250")
    prov = viewport_para_nivel("provincia", "46", "46250")
    ccaa = viewport_para_nivel("ccaa", "46", "46250")
    assert muni["nivel"] == "municipio"
    assert prov["nivel"] == "provincia"
    assert ccaa["nivel"] == "ccaa"
    assert _span(muni)[0] < _span(prov)[0] < _span(ccaa)[0]
