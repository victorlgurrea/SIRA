"""Tests de cuadrícula SST CMEMS / Open-Meteo (sin red real)."""
from __future__ import annotations

import os
import types

import numpy as np
import xarray as xr

from sira.infrastructure.sources.ocean import cmems_sst as mod


def _fake_subset(var, vals, lats, lons, time_val):
    """Simula copernicusmarine.subset(): escribe un netCDF real en
    output_directory y devuelve un objeto con .output_directory/.filename,
    igual que ResponseSubset. Así el test ejerce también xr.open_dataset()."""

    def _subset(**kwargs):
        output_directory = kwargs["output_directory"]
        os.makedirs(output_directory, exist_ok=True)
        ds = xr.Dataset(
            {var: (("time", "latitude", "longitude"), vals)},
            coords={"time": [time_val], "latitude": lats, "longitude": lons},
        )
        filename = "fake.nc"
        ds.to_netcdf(os.path.join(output_directory, filename), engine="h5netcdf")
        ds.close()
        return types.SimpleNamespace(output_directory=output_directory, filename=filename)

    return _subset


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
    fake_cm = types.SimpleNamespace(
        subset=_fake_subset("thetao", vals, lats, lons, time_val)
    )
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
    fake_cm = types.SimpleNamespace(
        subset=_fake_subset("thetao", vals, lats, lons, time_val)
    )
    monkeypatch.setitem(__import__("sys").modules, "copernicusmarine", fake_cm)

    out = mod.descargar_sst_cant_cuadricula()
    assert out["region"] == "cant"
    assert out["celdas"]
    assert "Copernicus" in out["fuente"]
