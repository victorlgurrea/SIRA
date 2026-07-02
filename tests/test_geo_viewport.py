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


def test_viewport_para_nivel():
    muni = viewport_para_nivel("municipio", "46", "46250")
    prov = viewport_para_nivel("provincia", "46", "46250")
    ccaa = viewport_para_nivel("ccaa", "46", "46250")
    assert muni["nivel"] == "municipio"
    assert prov["nivel"] == "provincia"
    assert ccaa["nivel"] == "ccaa"
    assert _span(muni)[0] < _span(prov)[0] < _span(ccaa)[0]
