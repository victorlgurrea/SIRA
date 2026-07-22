"""Tests de resumen térmico por provincia/CCAA."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import sira.infrastructure.sources.meteo.termico as mt

_MADRID = ZoneInfo("Europe/Madrid")


def test_pico_termico_24h_filtra_ventana_y_devuelve_hora_pico():
    now = datetime(2026, 7, 21, 10, 15, tzinfo=_MADRID)
    meteo = {
        "serie_horaria": [
            {"timestamp": "2026-07-21T09:00:00+02:00", "temp_c": 28, "sensacion_c": 29},
            {"timestamp": "2026-07-21T12:00:00+02:00", "temp_c": 31.2, "sensacion_c": 33.0},
            {"timestamp": "2026-07-22T09:00:00+02:00", "temp_c": 35.4, "sensacion_c": 37.1},
            {"timestamp": "2026-07-22T11:00:00+02:00", "temp_c": 39.0, "sensacion_c": 40.0},
        ]
    }

    out = mt.pico_termico_24h(meteo, now=now)

    assert out["temp_max_c"] == 35.4
    assert out["sensacion_max_c"] == 37.1
    assert out["hora_pico"] == "2026-07-22T09:00:00+02:00"


def test_construir_termico_ccaa_agrega_provincias_y_maximos(monkeypatch):
    monkeypatch.setattr(
        mt,
        "provincias",
        lambda: [
            {"id": "03", "nombre": "Alicante"},
            {"id": "46", "nombre": "Valencia"},
            {"id": "28", "nombre": "Madrid"},
        ],
    )
    monkeypatch.setattr(
        mt,
        "municipios",
        lambda pid: {
            "03": [{"id": "03001", "nombre": "Adsubia"}],
            "46": [{"id": "46001", "nombre": "València"}],
            "28": [{"id": "28001", "nombre": "Madrid"}],
        }.get(pid, []),
    )

    def fake_fetch(mid: str, _nombre: str | None) -> dict:
        temps = {
            "03001": 34.0,
            "46001": 37.5,
            "28001": 39.2,
        }
        return {
            "fuente": "AEMET",
            "serie_horaria": [
                {"timestamp": "2026-07-21T12:00:00+02:00", "temp_c": temps[mid], "sensacion_c": temps[mid] + 1.5},
            ],
        }

    out = mt.construir_termico_ccaa(fake_fetch, now=datetime(2026, 7, 21, 10, 0, tzinfo=_MADRID))

    assert [p["provincia_id"] for p in out["provincias"]] == ["28", "03", "46"]
    vc = next(x for x in out["ccaa"] if x["ccaa_id"] == "VC")
    md = next(x for x in out["ccaa"] if x["ccaa_id"] == "MD")
    assert vc["provincias"] == ["03", "46"]
    assert vc["temp_max_c"] == 37.5
    assert md["temp_max_c"] == 39.2
