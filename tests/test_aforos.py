"""Tests de aforos.py."""
from __future__ import annotations

from sira.infrastructure.sources.hydrology.chj import _utm30n_a_wgs84, nivel_riesgo_aforo


def test_utm30n_a_wgs84_dentro_espana():
    # Coordenadas UTM aproximadas en cuenca Júcar (Valencia)
    lat, lon = _utm30n_a_wgs84(725_000.0, 4_390_000.0)
    assert 36 <= lat <= 44
    assert -10 <= lon <= 4


def test_nivel_riesgo_aforo_sin_datos_con_alerta_meteo():
    nivel, sin_datos = nivel_riesgo_aforo(
        caudal_m3s=None,
        umbrales={},
        datos_recientes=False,
        en_fallo=False,
        alerta_lluvia_tormenta=True,
    )
    assert nivel == "vigilancia"
    assert sin_datos is True


def test_nivel_riesgo_aforo_sin_datos_sin_alerta():
    nivel, sin_datos = nivel_riesgo_aforo(
        caudal_m3s=None,
        umbrales={},
        datos_recientes=False,
        en_fallo=False,
        alerta_lluvia_tormenta=False,
    )
    assert nivel == "normal"
    assert sin_datos is False
