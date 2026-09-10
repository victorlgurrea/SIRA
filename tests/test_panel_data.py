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


def test_meteo_para_geo_no_cachea_vacio(monkeypatch):
    from sira.services.mapa import panel_data as pd

    monkeypatch.setattr(pd, "_METEO_CACHE", {})
    monkeypatch.setattr(pd, "AEMET_MUNICIPIO", "46250")
    monkeypatch.setattr(
        pd,
        "meteo_localidad",
        lambda *a, **k: {"fuente": "—", "serie_horaria": [], "resumen": {}},
    )
    monkeypatch.setattr(
        pd.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(pd.requests.RequestException("down")),
    )
    out = pd.meteo_para_geo("46250", "Valencia", dashboard={"meteorologia": {"resumen": {"precip_prox_24h_mm": 1.0}}})
    assert out.get("resumen", {}).get("temp_c") is None
    assert pd._METEO_CACHE == {}


def test_meteo_para_geo_completa_desde_live(monkeypatch):
    from sira.services.mapa import panel_data as pd

    monkeypatch.setattr(pd, "_METEO_CACHE", {})
    monkeypatch.setattr(pd, "AEMET_MUNICIPIO", "46250")
    monkeypatch.setattr(
        pd,
        "meteo_localidad",
        lambda *a, **k: {
            "fuente": "AEMET",
            "serie_horaria": [{"timestamp": "2026-09-10T18:00", "temp_c": 24.0}],
            "proximas_horas": [{"timestamp": "2026-09-10T19:00", "temp_c": 23.0}],
            "resumen": {
                "temp_c": 24.0,
                "viento_vel": 12.0,
                "viento_unidad": "km/h",
                "precip_prox_24h_mm": 0.0,
            },
        },
    )
    out = pd.meteo_para_geo(
        "46250",
        "Valencia",
        dashboard={"meteorologia": {"fuente": "AEMET", "resumen": {"precip_prox_24h_mm": 2.5}, "serie_horaria": [{"timestamp": "x", "precip_mm": 0}]}},
    )
    assert out["resumen"]["temp_c"] == 24.0
    assert out["resumen"]["precip_prox_24h_mm"] == 2.5
    assert out["resumen"]["viento_vel"] == 12.0


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
