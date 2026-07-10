"""Zonas Meteoalerta AEMET para el mapa."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from geo_aemet_zonas import aviso_maximo_zona, zonas_ccaa  # noqa: E402


def test_zonas_ccaa_valencia_tiene_tres_provincias():
    zonas = zonas_ccaa("46")
    provs = {z.get("provincia") for z in zonas}
    assert any("Val" in (p or "") for p in provs)
    assert any("Alacant" in (p or "") or "Alicante" in (p or "") for p in provs)
    assert any("Castell" in (p or "") for p in provs)
    assert len(zonas) >= 10


def test_zonas_ccaa_andalucia_amplia():
    zonas = zonas_ccaa("41")
    assert len(zonas) >= 30


def test_aviso_maximo_zona_por_codigo():
    zonas = zonas_ccaa("46")
    zona = next(z for z in zonas if z["id"])
    aviso = {
        "level": "naranja",
        "zona": zona["id"],
        "area_desc": zona["nombre"],
        "fenomeno_desc": "temperatura maxima",
        "probabilidad": "40%-70%",
        "parametro": "TA;Temperatura maxima;39 C",
    }
    mejor = aviso_maximo_zona(zona, [aviso])
    assert mejor is not None
    assert mejor["level"] == "naranja"
