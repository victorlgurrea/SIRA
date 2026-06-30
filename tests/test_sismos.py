"""Tests de sismos.py."""
from __future__ import annotations

import pytest

from config import SISMO_PERCEPCION
from sismos import (
    distancia_km,
    distancia_perceptible_km,
    radio_tsunami_km,
    riesgo_tsunami,
    score_sismo,
)


@pytest.fixture(autouse=True)
def _params_percepcion_documentados(monkeypatch):
    """Parámetros de la tabla de validación (EXP_MAG=0.34, EXP_BASE=0.30)."""
    p = {
        "mag_min": 2.5,
        "factor": 1.0,
        "exp_mag": 0.34,
        "exp_base": 0.30,
        "prof_km": 70.0,
        "max_km": 450.0,
    }
    monkeypatch.setattr("sismos.SISMO_PERCEPCION", p)
    monkeypatch.setattr("config.SISMO_PERCEPCION", p)


@pytest.mark.parametrize(
    "mag,prof,expected_km",
    [
        (2.5, 10, 14.1),
        (4.0, 10, 45.7),
        (5.0, 10, 100.0),
    ],
)
def test_distancia_perceptible_tabla(mag, prof, expected_km):
    r = distancia_perceptible_km(mag, prof)
    assert r == pytest.approx(expected_km, abs=1.5)


def test_distancia_perceptible_bajo_mag_min():
    assert distancia_perceptible_km(2.0, 10) == 0.0


def test_distancia_perceptible_profunda_ampliada():
    r_shallow = distancia_perceptible_km(5.0, 10)
    r_deep = distancia_perceptible_km(5.0, 200)
    assert r_deep > r_shallow


def test_distancia_perceptible_tope_max_km():
    r = distancia_perceptible_km(8.0, 5)
    assert r <= 450.0


def test_distancia_km_simetrica():
    d = distancia_km(39.47, -0.38, 40.0, -1.0)
    assert d > 0
    assert distancia_km(0, 0, 0, 1) == distancia_km(0, 1, 0, 0)


def test_score_boumerdes_2003():
    # M6.8 · 10 km · ~650 km · submarino → nivel alto
    out = score_sismo(6.8, 10, 650, True)
    assert out["score_total"] >= 55
    assert out["nivel_alerta"] in ("ALTO", "CRÍTICO")


def test_score_lorca_2011():
    # M5.1 · muy superficial · ~50 km · no submarino
    out = score_sismo(5.1, 1, 50, False)
    assert out["score_total"] >= 35
    assert out["nivel_alerta"] in ("MODERADO", "ALTO", "CRÍTICO")


def test_score_turquia_2023():
    # M7.8 · 10 km · lejos · submarino costero
    out = score_sismo(7.8, 10, 2500, True)
    assert out["nivel_alerta"] in ("ALTO", "CRÍTICO")
    assert out["score_total"] >= 55


def test_riesgo_tsunami_mar_mag_alta():
    assert riesgo_tsunami(7.0, 20, True, 0) is True


def test_riesgo_tsunami_tierra():
    assert riesgo_tsunami(7.0, 20, False, 1) is False


def test_riesgo_tsunami_usgs_flag():
    assert riesgo_tsunami(5.0, 100, True, 1) is True


def test_radio_tsunami_km_minimo():
    r = radio_tsunami_km(6.5, 10, en_mar=True)
    assert r >= 80.0


def test_radio_tsunami_km_tierra():
    assert radio_tsunami_km(8.0, 10, en_mar=False) == 0.0
