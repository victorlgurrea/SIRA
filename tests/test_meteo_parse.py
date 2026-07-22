"""Parseo AEMET horaria municipal."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.sources.meteo.parse import actual_aemet_from_item, aemet_val, parse_aemet, _entrada_por_hora  # noqa: E402

_VALENCIA_SNIPPET = [
    {
        "nombre": "València",
        "prediccion": {
            "dia": [
                {
                    "fecha": "2026-07-01T00:00:00",
                    "precipitacion": [
                        {"value": "0", "periodo": "10"},
                        {"value": "1", "periodo": "11"},
                    ],
                    "probPrecipitacion": [
                        {"value": "15", "periodo": "0814"},
                        {"value": "5", "periodo": "1420"},
                    ],
                    "estadoCielo": [
                        {"value": "11", "periodo": "10", "descripcion": "Despejado"},
                    ],
                    "temperatura": [{"value": "29", "periodo": "10"}],
                    "humedadRelativa": [{"value": "58", "periodo": "10"}],
                    "sensTermica": [{"value": "31", "periodo": "10"}],
                    "vientoAndRachaMax": [
                        {"direccion": ["NE"], "velocidad": ["17"], "periodo": "10"},
                        {"value": "34", "periodo": "10"},
                    ],
                }
            ]
        },
    }
]


def test_parse_aemet_formato_horario_arrays():
    serie = parse_aemet(_VALENCIA_SNIPPET)
    assert len(serie) >= 2
    h10 = next(s for s in serie if s["timestamp"] == "2026-07-01T10:00")
    assert h10["precip_mm"] == 0.0
    assert h10["prob_precip_pct"] == 15
    h11 = next(s for s in serie if s["timestamp"] == "2026-07-01T11:00")
    assert h11["precip_mm"] == 1.0
    assert h11["prob_precip_pct"] == 15


def test_actual_aemet_formato_horario_arrays():
    item = _VALENCIA_SNIPPET[0]
    act = actual_aemet_from_item(item, hora=10)
    assert act["tiempo_texto"] == "Despejado"
    assert act["temp_c"] == 29.0
    assert act["sensacion_c"] == 31.0
    assert act["humedad_pct"] == 58
    assert act["viento_unidad"] == "km/h"
    assert act["viento_vel"] == 17.0


def test_entrada_por_hora_periodo_un_digito():
    arr = [
        {"periodo": "8", "value": "55"},
        {"periodo": "10", "value": "58"},
    ]
    assert aemet_val(_entrada_por_hora(arr, 8).get("value")) == "55"
