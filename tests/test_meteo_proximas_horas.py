"""Próximas horas de temperatura en meteo_live."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "dashboard"))

from ui.components import meteo_ahora  # noqa: E402
from sira.infrastructure.sources.meteo.live import _proximas_horas_desde_serie  # noqa: E402


def test_proximas_horas_desde_serie_filtra_pasado():
    madrid = ZoneInfo("Europe/Madrid")
    ahora = datetime.now(madrid).replace(minute=30, second=0, microsecond=0)
    corte = ahora.replace(minute=0) + timedelta(hours=1)
    pasado = (corte - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    futuro = corte.strftime("%Y-%m-%dT%H:%M")
    serie = [
        {"timestamp": pasado, "temp_c": 20.0, "sensacion_c": 21.0},
        {"timestamp": futuro, "temp_c": 25.0, "sensacion_c": 26.0},
    ]
    with patch("sira.infrastructure.sources.meteo.live.datetime") as mock_dt:
        mock_dt.now.return_value = ahora
        mock_dt.fromisoformat = datetime.fromisoformat
        out = _proximas_horas_desde_serie(serie, horas=6)
    assert len(out) == 1
    assert out[0]["temp_c"] == 25.0


def test_meteo_ahora_muestra_cuadricula_open_meteo():
    prox = [
        {"timestamp": "2099-07-14T12:00", "temp_c": 31.0, "sensacion_c": 33.0},
        {"timestamp": "2099-07-14T13:00", "temp_c": 32.0, "sensacion_c": 34.0},
    ]
    node = meteo_ahora(
        {
            "tiempo_icon": "☀️",
            "tiempo_texto": "Despejado",
            "temp_c": 30,
            "sensacion_c": 32,
            "humedad_pct": 55,
            "viento_vel": 2.0,
            "viento_unidad": "m/s",
        },
        prox,
        fuente="Open-Meteo",
    )
    html_txt = str(node)
    assert "Próx. horas — Open-Meteo (temperatura)" in html_txt
    assert "sira-meteo-next-grid" in html_txt
