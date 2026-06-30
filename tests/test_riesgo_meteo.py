"""Tests de riesgo_meteo.py."""
from __future__ import annotations

import pytest

from riesgo_meteo import _indice_alerta, calcular_riesgo_meteo


def test_indice_alerta_pesos_nivel():
    assert _indice_alerta({"level": "verde", "probabilidad": "100%"}) == 10
    assert _indice_alerta({"level": "amarillo", "probabilidad": "100%"}) == 38
    assert _indice_alerta({"level": "naranja", "probabilidad": "100%"}) == 68
    assert _indice_alerta({"level": "rojo", "probabilidad": "100%"}) == 100


def test_indice_alerta_probabilidad_media():
    idx = _indice_alerta({"level": "rojo", "probabilidad": "40%-70%"})
    assert idx == pytest.approx(55, abs=2)


def test_calcular_riesgo_meteo_cap_y_precip():
    alertas = [{
        "level": "naranja",
        "probabilidad": "40%-70%",
        "fenomeno": "PR",
        "fenomeno_desc": "Lluvia",
        "area_desc": "Valencia",
    }]
    meteo = {
        "fuente": "AEMET",
        "serie_horaria": [
            {"timestamp": "2099-01-01T10:00", "precip_mm": 5, "prob_precip_pct": 85},
            {"timestamp": "2099-01-01T11:00", "precip_mm": 8, "prob_precip_pct": 90},
        ],
        "resumen": {},
    }
    riesgo = calcular_riesgo_meteo(alertas, meteo, horas=2)
    assert riesgo["indice_global"] >= 35
    assert riesgo["elementos"]
