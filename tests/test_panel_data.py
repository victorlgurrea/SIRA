"""Tests del servicio de datos del panel geográfico."""
from __future__ import annotations

from sira.services.mapa.panel_data import alertas_meteo_fuente, alertas_meteo_locales, datos_mapa


def test_alertas_meteo_fuente_merge():
    d = {
        "meteo_alertas_test": [{"fenomeno": "AT", "level": "amarillo"}],
        "meteo_alertas_live": [{"fenomeno": "PR", "level": "naranja"}],
    }
    out = alertas_meteo_fuente(d)
    assert len(out) == 2


def test_datos_mapa_enriquece_sismos(monkeypatch):
    monkeypatch.setattr(
        "sira.services.mapa.panel_data.coords_observacion",
        lambda *a, **k: (39.47, -0.38, "Valencia"),
    )
    monkeypatch.setattr(
        "sira.services.mapa.panel_data.embalses_para_mapa",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "sira.services.mapa.panel_data.aforos_para_mapa",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "sira.services.mapa.panel_data.alertas_para_dia",
        lambda x: x,
    )
    d = {
        "sismos": [{
            "id": "x", "magnitud": 3.5, "lugar": "cerca",
            "timestamp": "2026-01-01T12:00:00+00:00",
            "lat": 39.5, "lon": -0.4, "profundidad": 8,
        }],
        "incendios": [],
        "embalses": [],
        "aforos": [],
        "meteo_alertas_live": [],
        "meteo": {"resumen": {}},
    }
    ctx = datos_mapa({"municipio_id": "46250", "provincia_id": "46", "localidad": "València"}, d)
    assert ctx["lat_obs"] == 39.47
    assert len(ctx["sismos_mapa"]) == 1
    assert "dist_local_km" in ctx["sismos_mapa"][0]
    assert "score_local" in ctx["sismos_mapa"][0]


def test_alertas_meteo_locales_filtra(monkeypatch):
    monkeypatch.setattr(
        "sira.services.mapa.panel_data.alerta_coincide_zona",
        lambda a, **k: a.get("fenomeno") == "AT",
    )
    monkeypatch.setattr(
        "sira.services.mapa.panel_data.deduplicar_alertas",
        lambda xs: xs,
    )
    out = alertas_meteo_locales(
        {"provincia_id": "46", "municipio_id": "46250"},
        [{"fenomeno": "AT"}, {"fenomeno": "PR"}],
    )
    assert len(out) == 1
    assert out[0]["fenomeno"] == "AT"
