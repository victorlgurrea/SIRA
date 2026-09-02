"""Filtro temporal de sismos en el mapa."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from charts.map_fig import es_sismo_reciente, es_sismo_hoy


def test_es_sismo_reciente_ultimas_24h(monkeypatch):
    monkeypatch.setattr("charts.map_fig.SISMO_MAPA_HORAS", 24)
    ahora = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("charts.map_fig.datetime", type("DT", (), {
        "now": staticmethod(lambda tz=None: ahora),
    })())

    assert es_sismo_reciente("2026-09-02T10:00:00Z")
    assert es_sismo_reciente("2026-09-01T11:59:00Z") is False
    assert es_sismo_reciente("2026-08-18T12:00:00Z") is False


def test_es_sismo_hoy_solo_dia_utc(monkeypatch):
    ahora = datetime(2026, 9, 2, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("charts.map_fig.datetime", type("DT", (), {
        "now": staticmethod(lambda tz=None: ahora),
    })())
    assert es_sismo_hoy("2026-09-02T00:30:00Z")
    assert es_sismo_hoy("2026-09-01T23:00:00Z") is False
