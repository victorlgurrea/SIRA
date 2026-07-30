"""Máscara mar Mediterráneo occidental."""
from sira.infrastructure.geo.mar_mediterraneo import (
    fraccion_mar_celda,
    punto_en_mar_mediterraneo,
)


def test_valencia_ciudad_no_es_mar():
    assert not punto_en_mar_mediterraneo(39.47, -0.38)


def test_frente_valencia_es_mar():
    assert punto_en_mar_mediterraneo(39.35, 0.05)


def test_fraccion_mar_en_costa():
    assert fraccion_mar_celda(39.35, 0.05, 0.12) >= 0.35


def test_estrecho_gibraltar_es_mar():
    # Punto en mar junto a la costa andaluza (debe entrar en SST).
    assert punto_en_mar_mediterraneo(36.08, -5.35)


def test_tanger_no_es_mar():
    # Punto en tierra marroquí (no debe pintarse).
    assert not punto_en_mar_mediterraneo(35.76, -5.83)
