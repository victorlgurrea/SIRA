"""Tests máscara mar Cantábrico / Atlántico."""
from __future__ import annotations

import pytest

from sira.infrastructure.geo import mar_costa_atlantica as mar_atl
from sira.infrastructure.geo.mar_costa_atlantica import (
    build_tierra_atlantico,
    punto_en_mar_costa_atlantica,
    punto_en_mar_costa_atlantica_mapa,
)


def _limpiar_caches_mar() -> None:
    mar_atl.anillos_tierra_atlantico.cache_clear()
    mar_atl._anillos_indexados.cache_clear()
    mar_atl._anillos_ign.cache_clear()
    mar_atl._punto_en_mar_costa_atlantica_cached.cache_clear()
    mar_atl._punto_en_mar_costa_atlantica_mapa_cached.cache_clear()


@pytest.fixture(autouse=True)
def _reset_caches_mar():
    _limpiar_caches_mar()
    yield
    _limpiar_caches_mar()


def test_gibraltar_mar_abierto(monkeypatch):
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.ensure_tierra_atlantico",
        lambda: None,
    )
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.anillos_tierra_atlantico",
        lambda: [],
    )
    assert punto_en_mar_costa_atlantica(36.05, -5.20)


def test_portugal_mar_abierto(monkeypatch):
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.ensure_tierra_atlantico",
        lambda: None,
    )
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.anillos_tierra_atlantico",
        lambda: [],
    )
    assert punto_en_mar_costa_atlantica(38.70, -9.50)


def test_mapa_holgura_evita_pintar_sobre_costa_portugal():
    """Celdas casi costa pasan la máscara base pero no la de mapa (spill marcador)."""
    assert punto_en_mar_costa_atlantica(40.25, -8.99)
    assert not punto_en_mar_costa_atlantica_mapa(40.25, -8.99)
    assert punto_en_mar_costa_atlantica_mapa(40.25, -9.30)


def test_santander_mar_abierto(monkeypatch):
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.ensure_tierra_atlantico",
        lambda: None,
    )
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.anillos_tierra_atlantico",
        lambda: [],
    )
    assert punto_en_mar_costa_atlantica(43.60, -4.20)


def test_interior_asturias_no_es_mar(monkeypatch):
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.ensure_tierra_atlantico",
        lambda: None,
    )
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.anillos_tierra_atlantico",
        lambda: [],
    )
    assert not punto_en_mar_costa_atlantica(43.36, -5.85)


def test_build_tierra_atlantico_genera_json(tmp_path, monkeypatch):
    dest = tmp_path / "mundo_tierra_atlantico.json"
    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.TIERRA_FILE",
        dest,
    )

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "objects": {
                    "land": {
                        "geometries": [
                            {
                                "type": "Polygon",
                                "arcs": [[0]],
                            }
                        ],
                    }
                },
                "arcs": [[[-9.0, 43.0], [-8.0, 43.0], [-8.0, 44.0], [-9.0, 43.0]]],
            }

    monkeypatch.setattr(
        "sira.infrastructure.geo.mar_costa_atlantica.requests.get",
        lambda *a, **k: _Resp(),
    )
    out = build_tierra_atlantico()
    assert out == dest
    assert dest.is_file()
