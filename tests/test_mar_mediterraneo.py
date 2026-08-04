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
    assert not punto_en_mar_mediterraneo(42.60, 3.05)  # inland Cerbère


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
    # Marruecos / Argelia, interior claro (tierra).
    assert not punto_en_mar_mediterraneo(34.90, -2.90)
    assert not punto_en_mar_mediterraneo(34.90, -1.80)
    assert not punto_en_mar_mediterraneo(36.55, 2.80)


def test_magreb_mar_real_cerca_costa_no_se_tapa():
    # Mar abierto justo al norte de la costa magrebí (no pegado a la orilla:
    # Natural Earth engorda costa y rechazamos celdas que tocarían tierra).
    assert punto_en_mar_mediterraneo(35.45, -3.93)  # frente a Al Hoceima
    assert punto_en_mar_mediterraneo(35.40, -2.95)  # frente a Nador
    assert punto_en_mar_mediterraneo(35.35, -2.24)  # frente a Saidia
    assert punto_en_mar_mediterraneo(35.35, -1.85)  # frente a Ghazaouet


def test_corcega_tierra_no_es_mar():
    assert not punto_en_mar_mediterraneo(42.15, 9.10)


def test_cerdena_tierra_no_es_mar():
    assert not punto_en_mar_mediterraneo(40.10, 9.10)


def test_mar_entre_corcega_cerdena_si_entra():
    assert punto_en_mar_mediterraneo(41.55, 8.20)


def test_celda_costera_estricto():
    # Celda con esquinas en tierra no debe pasar umbral 0.9.
    assert fraccion_mar_celda(42.48, 3.10, 0.06) < 0.9


def test_no_pinta_tierra_natural_earth_oeste():
    # Puntos que el basemap Plotly (NE) marca como tierra no deben ser mar.
    assert not punto_en_mar_mediterraneo(42.48, 3.10)  # Portbou / Cerbère
    assert not punto_en_mar_mediterraneo(43.30, 5.40)  # Marsella


def test_mediterraneo_centro_oriental_mar():
    # Tirreno, Adriático, Jónico, Egeo, Levante: mar abierto (contorno mundial).
    assert punto_en_mar_mediterraneo(41.50, 12.20)  # Tirreno, frente a Roma
    assert punto_en_mar_mediterraneo(45.30, 12.60)  # Adriático, frente a Venecia
    assert punto_en_mar_mediterraneo(37.90, 21.00)  # Jónico, frente a Grecia
    assert punto_en_mar_mediterraneo(36.20, 25.20)  # Egeo, entre Santorini y Creta
    assert punto_en_mar_mediterraneo(34.50, 33.00)  # sur de Chipre
    assert punto_en_mar_mediterraneo(33.89, 35.20)  # frente a Beirut
    assert punto_en_mar_mediterraneo(31.45, 30.00)  # frente a Alejandría


def test_mediterraneo_centro_oriental_tierra():
    assert not punto_en_mar_mediterraneo(41.90, 12.49)  # Roma
    assert not punto_en_mar_mediterraneo(38.00, 23.73)  # Atenas
    assert not punto_en_mar_mediterraneo(35.17, 33.36)  # Nicosia (Chipre)
    assert not punto_en_mar_mediterraneo(33.85, 36.05)  # valle Bekaa (Líbano)
    assert not punto_en_mar_mediterraneo(31.50, 13.20)  # interior de Libia
