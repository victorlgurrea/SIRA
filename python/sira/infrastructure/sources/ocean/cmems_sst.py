"""Cuadrícula SST Mediterráneo (Copernicus Marine CMEMS L4)."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import numpy as np

from sira.config.settings import (
    CMEMS_PASSWORD,
    CMEMS_SST_DATASET_ID,
    CMEMS_SST_LAT_MAX,
    CMEMS_SST_LAT_MIN,
    CMEMS_SST_LON_MAX,
    CMEMS_SST_LON_MIN,
    CMEMS_SST_PASO_DEG,
    CMEMS_USERNAME,
)

log = logging.getLogger(__name__)

_NATIVE_DEG = 0.0625
_KELVIN_FLOOR = 200.0


def _creds_ok() -> bool:
    return bool(CMEMS_USERNAME and CMEMS_PASSWORD)


def _to_celsius(val: float) -> float:
    if val >= _KELVIN_FLOOR:
        return val - 273.15
    return val


def _coord_name(da, candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in da.dims or name in getattr(da, "coords", {}):
            return name
    raise ValueError(f"Coordenada no encontrada ({', '.join(candidates)})")


def descargar_sst_med_cuadricula() -> dict:
    """
    Descarga SST foundation L4 del Mediterráneo y remuestrea a una malla gruesa.

    Requiere cuenta gratuita CMEMS y variables:
    COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD.
    """
    if not _creds_ok():
        raise RuntimeError(
            "Sin credenciales CMEMS "
            "(COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD). "
            "Registro: https://data.marine.copernicus.eu/register"
        )

    try:
        import copernicusmarine
    except ImportError as exc:
        raise RuntimeError(
            "Falta el paquete copernicusmarine. Instala: pip install 'copernicusmarine'"
        ) from exc

    ahora = datetime.now(timezone.utc)
    inicio = ahora - timedelta(days=4)
    paso = max(_NATIVE_DEG, float(CMEMS_SST_PASO_DEG))
    stride = max(1, int(round(paso / _NATIVE_DEG)))

    log.info(
        "CMEMS SST: dataset=%s bbox=[%.2f,%.2f]×[%.2f,%.2f] paso≈%.3f°",
        CMEMS_SST_DATASET_ID,
        CMEMS_SST_LAT_MIN,
        CMEMS_SST_LAT_MAX,
        CMEMS_SST_LON_MIN,
        CMEMS_SST_LON_MAX,
        paso,
    )

    ds = copernicusmarine.open_dataset(
        dataset_id=CMEMS_SST_DATASET_ID,
        variables=["analysed_sst"],
        minimum_longitude=CMEMS_SST_LON_MIN,
        maximum_longitude=CMEMS_SST_LON_MAX,
        minimum_latitude=CMEMS_SST_LAT_MIN,
        maximum_latitude=CMEMS_SST_LAT_MAX,
        start_datetime=inicio.strftime("%Y-%m-%dT00:00:00"),
        end_datetime=ahora.strftime("%Y-%m-%dT23:59:59"),
        username=CMEMS_USERNAME,
        password=CMEMS_PASSWORD,
        disable_progress_bar=True,
    )

    if "analysed_sst" not in ds:
        raise RuntimeError("Dataset CMEMS sin variable analysed_sst")

    da = ds["analysed_sst"]
    if "time" in da.dims:
        da = da.isel(time=-1)
        fecha_raw = da.coords["time"].values
        try:
            fecha = np.datetime_as_string(fecha_raw, unit="D")
        except Exception:  # noqa: BLE001
            fecha = str(fecha_raw)[:10]
    else:
        fecha = ahora.date().isoformat()

    lat_name = _coord_name(da, ("latitude", "lat"))
    lon_name = _coord_name(da, ("longitude", "lon"))
    lats = np.asarray(da[lat_name].values, dtype=float)[::stride]
    lons = np.asarray(da[lon_name].values, dtype=float)[::stride]
    grid = np.asarray(da.values, dtype=float)[::stride, ::stride]

    celdas: list[dict] = []
    for i, lat in enumerate(lats):
        row = grid[i] if i < grid.shape[0] else None
        if row is None:
            continue
        for j, lon in enumerate(lons):
            if j >= len(row):
                break
            raw = float(row[j])
            if not math.isfinite(raw):
                continue
            sst_c = round(_to_celsius(raw), 2)
            celdas.append({
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "sst_c": sst_c,
            })

    try:
        ds.close()
    except Exception:  # noqa: BLE001
        pass

    if not celdas:
        raise RuntimeError("CMEMS SST: sin celdas válidas en el bbox solicitado")

    sst_vals = [c["sst_c"] for c in celdas]
    log.info("CMEMS SST: %d celdas · fecha=%s · rango %.1f–%.1f °C", len(celdas), fecha, min(sst_vals), max(sst_vals))
    return {
        "fuente": "Copernicus Marine SST MED L4",
        "dataset_id": CMEMS_SST_DATASET_ID,
        "fecha": fecha,
        "paso_deg": round(stride * _NATIVE_DEG, 4),
        "bbox": {
            "lat_min": CMEMS_SST_LAT_MIN,
            "lat_max": CMEMS_SST_LAT_MAX,
            "lon_min": CMEMS_SST_LON_MIN,
            "lon_max": CMEMS_SST_LON_MAX,
        },
        "resumen": {
            "n_celdas": len(celdas),
            "sst_min_c": round(min(sst_vals), 2),
            "sst_max_c": round(max(sst_vals), 2),
            "sst_media_c": round(sum(sst_vals) / len(sst_vals), 2),
        },
        "celdas": celdas,
    }
