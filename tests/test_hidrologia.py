"""Tests de hidrologia.py."""
from __future__ import annotations

from sira.infrastructure.sources.hydrology.reservoirs import nivel_riesgo_embalse


def test_nivel_riesgo_embalse_umbrales():
    assert nivel_riesgo_embalse(84) == "normal"
    assert nivel_riesgo_embalse(85) == "vigilancia"
    assert nivel_riesgo_embalse(95) == "alerta"
    assert nivel_riesgo_embalse(98) == "critico"
    assert nivel_riesgo_embalse(100) == "critico"
