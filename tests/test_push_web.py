"""Tests de bootstrap de avisos meteo para push."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from push_web import _split_meteo_bootstrap  # noqa: E402


def _alert(level: str, zona: str, valor: str) -> dict:
    return {
        "level": level,
        "fenomeno": "AT",
        "area_desc": zona,
        "parametro": f"TA;Temperatura máxima;{valor}",
    }


def test_bootstrap_meteo_no_reenvia_inventario_amarillo():
    avisos = [
        _alert("amarillo", "Toledo", "38 C"),
    ]
    seed, nuevos = _split_meteo_bootstrap(avisos, set())
    assert len(seed) == 1
    assert nuevos == []


def test_bootstrap_meteo_envia_naranja_y_rojo_ya_activos():
    avisos = [
        _alert("rojo", "Valencia", "44 C"),
        _alert("naranja", "Toledo", "41 C"),
    ]
    seed, nuevos = _split_meteo_bootstrap(avisos, set())
    assert len(seed) == 2
    assert {a["level"] for a in nuevos} == {"naranja", "rojo"}


def test_bootstrap_meteo_con_estado_prev_envia_solo_nuevos():
    aviso = _alert("rojo", "Valencia", "44 C")
    seed, nuevos = _split_meteo_bootstrap([aviso], {"AT|rojo|valencia|44|c"})
    assert seed == {"AT|rojo|valencia|44|c"}
    assert nuevos == []
