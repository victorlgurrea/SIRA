"""Historial municipal: snapshots y gráfico."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest


def test_snapshot_desde_dashboard_crea_fila(db_tmp, monkeypatch):
    from sira.services.historial import snapshots as snap

    monkeypatch.setattr(
        snap,
        "meteo_localidad",
        lambda mid, loc: {"resumen": {"precip_prox_24h_mm": 0}},
    )
    monkeypatch.setattr(snap, "coords_observacion", lambda mid, loc: (39.47, -0.38, "València"))
    dashboard = {
        "sismos": [],
        "incendios": [],
        "embalses": [],
        "aforos": [],
        "termico_ccaa": {},
        "meteo_alertas_cap": [],
    }
    assert snap.snapshot_municipio_desde_dashboard("46250", dashboard) is True
    serie = db_tmp.get_historial_municipio("46250", 30)
    assert len(serie) == 1
    assert serie[0]["fecha"] == date.today().isoformat()
    assert snap.snapshot_municipio_desde_dashboard("46250", dashboard) is False


def test_serie_evolucion_usgs(db_tmp, monkeypatch):
    from sira.services.historial import serie as ser

    monkeypatch.setattr(ser, "coords_observacion", lambda mid, loc: (39.47, -0.38, "València"))
    monkeypatch.setattr(ser, "get_historial_municipio", db_tmp.get_historial_municipio)
    hoy = date.today().isoformat()
    dashboard = {
        "sismos": [{
            "magnitud": 4.5,
            "lat": 39.5,
            "lon": -0.5,
            "profundidad": 10,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "lugar": "test",
        }],
    }
    out = ser.serie_evolucion_municipio("46250", dashboard, dias=7)
    assert len(out) == 7
    assert out[-1]["fecha"] == hoy
    assert out[-1]["score_sismo_max"] > 0
    assert ser.serie_tiene_datos(out) is True


def test_fig_historial_sin_datos():
    from charts.figures import fig_historial

    fig = fig_historial("99999", "46250", "test", theme="dark", dashboard={"sismos": []})
    assert len(fig.data) == 0
    assert fig.layout.annotations


def test_fig_historial_con_serie(db_tmp, monkeypatch):
    from sira.services.historial import serie as ser

    monkeypatch.setattr(ser, "coords_observacion", lambda mid, loc: (39.47, -0.38, "València"))
    monkeypatch.setattr(ser, "get_historial_municipio", db_tmp.get_historial_municipio)
    db_tmp.insert_historial_municipio(
        date.today().isoformat(),
        "46250",
        score_sismo_max=12,
        indice_riesgo_meteo=40,
        indice_impacto_local=25,
    )
    from charts import figures as figmod

    fig = figmod.fig_historial(
        "46250", "46250", "test", theme="dark",
        dashboard={"sismos": []},
    )
    assert len(fig.data) >= 1
    assert fig.layout.xaxis.type == "date"
