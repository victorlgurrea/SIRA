"""Tests de cuadrícula SST CMEMS / Open-Meteo (sin red real)."""
from __future__ import annotations

import types

import numpy as np
import pytest

from sira.infrastructure.sources.ocean import cmems_sst as mod


class _FakeDa:
    def __init__(self, values, lats, lons, time_val):
        self.values = values
        self.dims = ("time", "latitude", "longitude")
        self.coords = {
            "time": types.SimpleNamespace(values=time_val),
            "latitude": types.SimpleNamespace(values=lats),
            "longitude": types.SimpleNamespace(values=lons),
        }
        self._lats = lats
        self._lons = lons
        self._time = time_val
        self._vals = values

    def __getitem__(self, key):
        if key == "latitude":
            return types.SimpleNamespace(values=self._lats)
        if key == "longitude":
            return types.SimpleNamespace(values=self._lons)
        if key == "time":
            return types.SimpleNamespace(values=self._time)
        raise KeyError(key)

    def isel(self, **kwargs):
        assert "time" in kwargs
        out = _FakeDa(self._vals[kwargs["time"]], self._lats, self._lons, self._time)
        out.dims = ("latitude", "longitude")
        return out


class _FakeDs(dict):
    def close(self):
        return None


def test_descargar_sst_sin_creds_usa_open_meteo(monkeypatch):
    monkeypatch.setattr(mod, "CMEMS_USERNAME", "")
    monkeypatch.setattr(mod, "CMEMS_PASSWORD", "")
    monkeypatch.setattr(mod, "CMEMS_SST_PASO_DEG", 2.0)
    monkeypatch.setattr(mod, "CMEMS_SST_LAT_MIN", 38.5)
    monkeypatch.setattr(mod, "CMEMS_SST_LAT_MAX", 40.5)
    monkeypatch.setattr(mod, "CMEMS_SST_LON_MIN", 1.0)
    monkeypatch.setattr(mod, "CMEMS_SST_LON_MAX", 4.0)

    def fake_fetch(url, params):
        lats = [float(x) for x in str(params["latitude"]).split(",")]
        lons = [float(x) for x in str(params["longitude"]).split(",")]
        return [
            {
                "latitude": la,
                "longitude": lo,
                "hourly": {
                    "time": ["2026-07-29T10:00", "2026-07-29T11:00"],
                    "sea_surface_temperature": [22.0, 22.5],
                },
            }
            for la, lo in zip(lats, lons)
        ]

    monkeypatch.setattr(mod, "fetch_json", fake_fetch)
    out = mod.descargar_sst_med_cuadricula()
    assert out["celdas"]
    assert "Open-Meteo" in out["fuente"]
    assert all(c["sst_c"] == 22.5 for c in out["celdas"])


def test_descargar_sst_cmems_mock(monkeypatch):
    monkeypatch.setattr(mod, "CMEMS_USERNAME", "user")
    monkeypatch.setattr(mod, "CMEMS_PASSWORD", "pass")
    monkeypatch.setattr(mod, "CMEMS_SST_VARIABLE", "thetao")
    monkeypatch.setattr(mod, "CMEMS_SST_PASO_DEG", 0.125)
    monkeypatch.setattr(mod, "CMEMS_SST_LAT_MIN", 39.0)
    monkeypatch.setattr(mod, "CMEMS_SST_LAT_MAX", 40.0)
    monkeypatch.setattr(mod, "CMEMS_SST_LON_MIN", 0.0)
    monkeypatch.setattr(mod, "CMEMS_SST_LON_MAX", 1.0)

    lats = np.array([39.0, 39.0625, 39.125, 39.1875])
    lons = np.array([0.0, 0.0625, 0.125, 0.1875])
    # thetao ya viene en °C
    vals = np.full((1, 4, 4), 18.0, dtype=float)
    vals[0, 0, 0] = 20.0
    time_val = np.datetime64("2026-07-28T12:00")
    fake_ds = _FakeDs(thetao=_FakeDa(vals, lats, lons, time_val))
    fake_cm = types.SimpleNamespace(open_dataset=lambda **kwargs: fake_ds)
    monkeypatch.setitem(__import__("sys").modules, "copernicusmarine", fake_cm)

    out = mod.descargar_sst_med_cuadricula()
    assert out["fuente"].startswith("Copernicus")
    assert "2026-07-28" in out["fecha"]
    assert out["celdas"]
    assert any(abs(c["sst_c"] - 20.0) < 0.01 for c in out["celdas"])
