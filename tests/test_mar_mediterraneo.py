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


def test_argel_tierra_no_es_mar():
    assert not punto_en_mar_mediterraneo(36.70, 3.05)


def test_marsella_tierra_no_es_mar():
    assert not punto_en_mar_mediterraneo(43.30, 5.40)


def test_frontera_francia_espana_no_es_mar():
    # Interior cerca frontera (no costa).
    assert not punto_en_mar_mediterraneo(42.44, 2.20)
    assert not punto_en_mar_mediterraneo(42.44, 2.60)
    # Celdas que salían sobre tierra en Portbou / Cerbère.
    assert not punto_en_mar_mediterraneo(42.48, 3.10)
    assert not punto_en_mar_mediterraneo(42.52, 3.20)


def test_cantabrico_no_entra_como_mediterraneo():
    assert not punto_en_mar_mediterraneo(43.43, -3.80)


def test_golfo_leon_si_entra():
    assert punto_en_mar_mediterraneo(42.15, 3.60)


def test_cap_creus_mar_si_entra():
    # Punta Cap de Creus (mar, no tierra francesa).
    assert punto_en_mar_mediterraneo(42.32, 3.32)


def test_alboran_si_entra():
    assert punto_en_mar_mediterraneo(36.20, -3.50)


def test_magreb_tierra_no_es_mar():
    # Marruecos / Argelia cerca costa (tierra).
    assert not punto_en_mar_mediterraneo(35.50, -2.90)
    assert not punto_en_mar_mediterraneo(35.40, -1.80)
    assert not punto_en_mar_mediterraneo(36.55, 2.80)


def test_corcega_tierra_no_es_mar():
    assert not punto_en_mar_mediterraneo(42.15, 9.10)


def test_cerdena_tierra_no_es_mar():
    assert not punto_en_mar_mediterraneo(40.10, 9.10)


def test_mar_entre_corcega_cerdena_si_entra():
    assert punto_en_mar_mediterraneo(41.55, 8.20)


def test_celda_costera_estricto():
    # Celda con esquinas en tierra no debe pasar umbral 0.8.
    assert fraccion_mar_celda(42.48, 3.10, 0.06) < 0.8
