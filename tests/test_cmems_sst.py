"""Tests de cuadrícula SST CMEMS / Open-Meteo (sin red real)."""
from __future__ import annotations

import types

import numpy as np

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

    def isel(self, indexers=None, **kwargs):
        """Soporta isel(time=idx) (colapsa dim) e isel({lat: slice, lon: slice})
        (mantiene dims, para el stride perezoso lat/lon antes de .values)."""
        idx = dict(indexers or {})
        idx.update(kwargs)
        dims = list(self.dims)
        slicer = [slice(None)] * len(dims)
        for name, sel in idx.items():
            slicer[dims.index(name)] = sel
        vals = self._vals[tuple(slicer)]
        lats = self._lats
        lons = self._lons
        for name, sel in idx.items():
            if name in ("latitude", "lat"):
                lats = lats[sel]
            elif name in ("longitude", "lon"):
                lons = lons[sel]
        new_dims = tuple(d for d, sel in zip(dims, slicer) if isinstance(sel, slice))
        out = _FakeDa(vals, lats, lons, self._time)
        out.dims = new_dims
        return out


class _FakeDs(dict):
    def close(self):
        return None


def _region_test(**overrides):
    base = dict(
        key="med",
        dataset_id="test-dataset",
        lat_min=38.5,
        lat_max=40.5,
        lon_min=1.0,
        lon_max=4.0,
        paso_deg=2.0,
        fuente_cmems="Copernicus test SST",
        fraccion_mar=lambda *a, **k: 1.0,
        densificar=lambda c, **k: c,
    )
    base.update(overrides)
    return mod.SstRegionConfig(**base)


def test_descargar_sst_sin_creds_usa_open_meteo(monkeypatch):
    monkeypatch.setattr(mod, "CMEMS_USERNAME", "")
    monkeypatch.setattr(mod, "CMEMS_PASSWORD", "")
    monkeypatch.setattr(mod, "CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK", True)
    monkeypatch.setattr(mod, "REGION_MED", _region_test())

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
    monkeypatch.setattr(
        mod,
        "REGION_MED",
        _region_test(
            lat_min=39.0,
            lat_max=40.0,
            lon_min=0.0,
            lon_max=1.0,
            paso_deg=0.125,
            fuente_cmems="Copernicus Med-Physics SST (ultimo disponible)",
        ),
    )

    lats = np.array([39.0, 39.0625, 39.125, 39.1875])
    lons = np.array([0.0, 0.0625, 0.125, 0.1875])
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


def test_descargar_sst_cant_cmems_mock(monkeypatch):
    monkeypatch.setattr(mod, "CMEMS_USERNAME", "user")
    monkeypatch.setattr(mod, "CMEMS_PASSWORD", "pass")
    monkeypatch.setattr(mod, "CMEMS_SST_VARIABLE", "thetao")
    monkeypatch.setattr(
        mod,
        "REGION_CANT",
        _region_test(
            key="cant",
            lat_min=43.0,
            lat_max=44.0,
            lon_min=-4.0,
            lon_max=-3.0,
            paso_deg=0.5,
            fuente_cmems="Copernicus IBI-Physics SST Cantábrico (ultimo disponible)",
        ),
    )

    lats = np.array([43.0, 43.5, 44.0])
    lons = np.array([-4.0, -3.5, -3.0])
    vals = np.full((1, 3, 3), 15.0, dtype=float)
    time_val = np.datetime64("2026-07-28T12:00")
    fake_ds = _FakeDs(thetao=_FakeDa(vals, lats, lons, time_val))
    fake_cm = types.SimpleNamespace(open_dataset=lambda **kwargs: fake_ds)
    monkeypatch.setitem(__import__("sys").modules, "copernicusmarine", fake_cm)

    out = mod.descargar_sst_cant_cuadricula()
    assert out["region"] == "cant"
    assert out["celdas"]
    assert "Copernicus" in out["fuente"]
