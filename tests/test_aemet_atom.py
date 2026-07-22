"""Fallback Atom AEMET para avisos CAP."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.sources.meteo.aemet_alerts import _tar_url_desde_atom  # noqa: E402


def test_tar_url_desde_atom_primera_entrada():
    atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Estado completo</title>
    <link href="https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/cap/Z_CAP_C_LEMM_20260716094925_AFAE.tar.gz"/>
  </entry>
  <entry>
    <title>Aviso individual</title>
    <link href="https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/cap/Z_CAP_C_LEMM_xxx.xml"/>
  </entry>
</feed>
"""
    url = _tar_url_desde_atom(atom)
    assert url is not None
    assert url.endswith("AFAE.tar.gz")


def test_tar_url_desde_atom_sin_tar():
    atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><link href="https://www.aemet.es/foo.xml"/></entry>
</feed>
"""
    assert _tar_url_desde_atom(atom) is None
