"""Selección del payload dashboard más reciente."""
from __future__ import annotations

from sira.infrastructure.http import dashboard_fetch as df
from sira.infrastructure.http.dashboard_fetch import _pick_fresher


def test_pick_fresher_elige_generado_en_mas_nuevo():
    old = {
        "generado_en": "2026-09-02T10:40:00+00:00",
        "sismos": [{"id": 1}],
        "sst_med_grid": {"celdas": [{"lat": 1, "lon": 1, "sst_c": 20}]},
    }
    new = {
        "generado_en": "2026-09-03T05:57:00+00:00",
        "sismos": [{"id": 1}, {"id": 2}],
        "sst_med_grid": {"celdas": [{"lat": 1, "lon": 1, "sst_c": 20}]},
        "sst_atl_grid": {"celdas": [{"lat": 2, "lon": 2, "sst_c": 18}]},
    }
    assert _pick_fresher(old, new) is new
    assert _pick_fresher(new, old) is new


def test_load_usa_api_si_status_es_mas_nuevo(monkeypatch):
    old = {
        "generado_en": "2026-09-02T10:40:00+00:00",
        "sismos": [{"id": 1}],
        "sst_med_grid": {"celdas": [{"lat": 1, "lon": 1, "sst_c": 20}]},
    }
    new = {
        "generado_en": "2026-09-03T05:57:00+00:00",
        "sismos": [{"id": 1}, {"id": 2}],
        "sst_med_grid": {"celdas": [{"lat": 1, "lon": 1, "sst_c": 20}]},
        "sst_atl_grid": {"celdas": [{"lat": 2, "lon": 2, "sst_c": 18}]},
    }
    written = {}

    monkeypatch.setattr(df, "_maybe_refresh_snapshot", lambda _d: old)
    monkeypatch.setattr(df, "read_dashboard", lambda: old)
    monkeypatch.setattr(df, "fetch_status_api", lambda _u: {"generado_en": new["generado_en"]})
    monkeypatch.setattr(df, "_fetch_dashboard_api", lambda _u: new)
    monkeypatch.setattr(df, "write_dashboard", lambda d: written.update(d))

    out = df.load_dashboard_payload("https://example.invalid")
    assert out["generado_en"] == new["generado_en"]
    assert written.get("generado_en") == new["generado_en"]


def test_load_no_pide_dashboard_si_disco_al_dia(monkeypatch):
    data = {
        "generado_en": "2026-09-03T05:57:00+00:00",
        "sismos": [{"id": 1}],
        "sst_med_grid": {"celdas": [{"lat": 1, "lon": 1, "sst_c": 20}]},
    }
    called = {"dashboard": 0}

    monkeypatch.setattr(df, "_maybe_refresh_snapshot", lambda _d: data)
    monkeypatch.setattr(df, "read_dashboard", lambda: data)
    monkeypatch.setattr(df, "fetch_status_api", lambda _u: {"generado_en": data["generado_en"]})

    def _fail(_u):
        called["dashboard"] += 1
        raise AssertionError("no debe pedir /api/dashboard")

    monkeypatch.setattr(df, "_fetch_dashboard_api", _fail)
    out = df.load_dashboard_payload("https://example.invalid")
    assert out is data
    assert called["dashboard"] == 0
