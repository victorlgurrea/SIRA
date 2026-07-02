"""Coordenadas municipales (nombres bilingües INE)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from geo_es import coords_municipio, coords_observacion, municipio_por_id, provincia_de_municipio  # noqa: E402


def test_castello_de_la_plana_tiene_coords_en_provincia_12():
    muni = municipio_por_id("12040")
    assert muni is not None
    assert muni.get("lat") is not None
    assert muni.get("lon") is not None
    assert provincia_de_municipio("12040") == "12"
    lat, lon = coords_municipio("12040")
    # Castelló de la Plana (~40°N), no Valencia ciudad (~39.47°N)
    assert lat > 39.8
    assert lon > -0.15


def test_coords_observacion_localidad_castello():
    lat, lon, etiqueta = coords_observacion("12040", "12040-0")
    assert lat > 39.8
    assert "Plana" in etiqueta or "plana" in etiqueta.lower()
