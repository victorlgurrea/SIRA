"""Cuadrícula SST por región (Copernicus Marine CMEMS + fallback Open-Meteo)."""
from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial

import numpy as np

from sira.config.settings import (
    CMEMS_PASSWORD,
    CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK,
    CMEMS_SST_ATL_LAT_MAX,
    CMEMS_SST_ATL_LAT_MIN,
    CMEMS_SST_ATL_LON_MAX,
    CMEMS_SST_ATL_LON_MIN,
    CMEMS_SST_ATL_MAP_MAX_CELDAS,
    CMEMS_SST_ATL_PASO_DEG,
    CMEMS_SST_CANT_LAT_MAX,
    CMEMS_SST_CANT_LAT_MIN,
    CMEMS_SST_CANT_LON_MAX,
    CMEMS_SST_CANT_LON_MIN,
    CMEMS_SST_CANT_PASO_DEG,
    CMEMS_SST_DATASET_ID,
    CMEMS_SST_IBI_DATASET_ID,
    CMEMS_SST_LAT_MAX,
    CMEMS_SST_LAT_MIN,
    CMEMS_SST_LON_MAX,
    CMEMS_SST_LON_MIN,
    CMEMS_SST_PASO_DEG,
    CMEMS_SST_MAP_MAX_CELDAS,
    CMEMS_SST_VARIABLE,
    CMEMS_USERNAME,
    OPEN_METEO_MARINE_URL,
)
from sira.infrastructure.geo import mar_costa_atlantica as mar_atl
from sira.infrastructure.geo import mar_mediterraneo as mar_med
from sira.infrastructure.http.client import fetch_json
from sira.infrastructure.sources.ocean.sst_transport import limitar_celdas_mapa

log = logging.getLogger(__name__)

_KELVIN_FLOOR = 200.0
_OM_BATCH = 60


@dataclass(frozen=True)
class SstRegionConfig:
    key: str
    dataset_id: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    paso_deg: float
    fuente_cmems: str
    fraccion_mar: Callable[[float, float, float], float]
    densificar: Callable[..., list[dict]]
    map_max_celdas: int | None = None
    umbral_mar: float = 0.85


REGION_MED = SstRegionConfig(
    key="med",
    dataset_id=CMEMS_SST_DATASET_ID,
    lat_min=CMEMS_SST_LAT_MIN,
    lat_max=CMEMS_SST_LAT_MAX,
    lon_min=CMEMS_SST_LON_MIN,
    lon_max=CMEMS_SST_LON_MAX,
    paso_deg=CMEMS_SST_PASO_DEG,
    fuente_cmems="Copernicus Med-Physics SST (ultimo disponible)",
    fraccion_mar=mar_med.fraccion_mar_celda,
    densificar=mar_med.densificar_celdas_mar,
)

_VECINOS_CARDINAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
_densificar_cant = partial(
    mar_atl.densificar_celdas_mar,
    vecinos=_VECINOS_CARDINAL,
    max_pasadas=3,
)
_densificar_atl = partial(
    mar_atl.densificar_celdas_mar,
    vecinos=_VECINOS_CARDINAL,
    max_pasadas=6,
)

REGION_CANT = SstRegionConfig(
    key="cant",
    dataset_id=CMEMS_SST_IBI_DATASET_ID,
    lat_min=CMEMS_SST_CANT_LAT_MIN,
    lat_max=CMEMS_SST_CANT_LAT_MAX,
    lon_min=CMEMS_SST_CANT_LON_MIN,
    lon_max=CMEMS_SST_CANT_LON_MAX,
    paso_deg=CMEMS_SST_CANT_PASO_DEG,
    fuente_cmems="Copernicus IBI-Physics SST Cantábrico (ultimo disponible)",
    fraccion_mar=mar_atl.fraccion_mar_celda,
    densificar=_densificar_cant,
)

REGION_ATL = SstRegionConfig(
    key="atl",
    dataset_id=CMEMS_SST_IBI_DATASET_ID,
    lat_min=CMEMS_SST_ATL_LAT_MIN,
    lat_max=CMEMS_SST_ATL_LAT_MAX,
    lon_min=CMEMS_SST_ATL_LON_MIN,
    lon_max=CMEMS_SST_ATL_LON_MAX,
    paso_deg=CMEMS_SST_ATL_PASO_DEG,
    fuente_cmems="Copernicus IBI-Physics SST Atlántico (ultimo disponible)",
    fraccion_mar=mar_atl.fraccion_mar_celda,
    densificar=_densificar_atl,
    map_max_celdas=CMEMS_SST_ATL_MAP_MAX_CELDAS,
    umbral_mar=0.82,
)


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


def _idx_ultimo_disponible(times, ahora: datetime) -> int:
    if len(times) == 0:
        return -1
    try:
        ts = times.astype("datetime64[ns]")
        now_ns = np.datetime64(ahora.replace(tzinfo=None), "ns")
        valid = np.where(ts <= now_ns)[0]
        if len(valid):
            return int(valid[-1])
    except Exception:  # noqa: BLE001
        pass
    return len(times) - 1


def _pack(
    celdas: list[dict],
    *,
    region: SstRegionConfig,
    fuente: str,
    fecha: str,
    paso: float,
) -> dict:
    if not celdas:
        raise RuntimeError(f"{fuente}: sin celdas válidas en el bbox solicitado")
    limite = region.map_max_celdas if region.map_max_celdas and region.map_max_celdas > 0 else CMEMS_SST_MAP_MAX_CELDAS
    celdas = limitar_celdas_mapa(celdas, max_n=limite)
    sst_vals = [c["sst_c"] for c in celdas]
    return {
        "region": region.key,
        "fuente": fuente,
        "dataset_id": region.dataset_id,
        "fecha": fecha,
        "paso_deg": round(paso, 4),
        "bbox": {
            "lat_min": region.lat_min,
            "lat_max": region.lat_max,
            "lon_min": region.lon_min,
            "lon_max": region.lon_max,
        },
        "resumen": {
            "n_celdas": len(celdas),
            "sst_min_c": round(min(sst_vals), 2),
            "sst_max_c": round(max(sst_vals), 2),
            "sst_media_c": round(sum(sst_vals) / len(sst_vals), 2),
        },
        "celdas": celdas,
    }


def _desde_cmems(region: SstRegionConfig) -> dict:
    import copernicusmarine

    ahora = datetime.now(timezone.utc)
    inicio = ahora - timedelta(days=2)
    paso = max(0.042, float(region.paso_deg))

    log.info(
        "CMEMS SST %s: dataset=%s var=%s bbox=[%.2f,%.2f]×[%.2f,%.2f] paso≈%.3f°",
        region.key,
        region.dataset_id,
        CMEMS_SST_VARIABLE,
        region.lat_min,
        region.lat_max,
        region.lon_min,
        region.lon_max,
        paso,
    )

    open_kwargs = dict(
        dataset_id=region.dataset_id,
        variables=[CMEMS_SST_VARIABLE],
        minimum_longitude=region.lon_min,
        maximum_longitude=region.lon_max,
        minimum_latitude=region.lat_min,
        maximum_latitude=region.lat_max,
        start_datetime=inicio.strftime("%Y-%m-%dT00:00:00"),
        end_datetime=ahora.strftime("%Y-%m-%dT23:59:59"),
        username=CMEMS_USERNAME.strip(),
        password=CMEMS_PASSWORD.strip(),
    )
    try:
        ds = copernicusmarine.open_dataset(**open_kwargs, disable_progress_bar=True)
    except TypeError:
        ds = copernicusmarine.open_dataset(**open_kwargs)

    if CMEMS_SST_VARIABLE not in ds:
        raise RuntimeError(f"Dataset CMEMS sin variable {CMEMS_SST_VARIABLE}")

    da = ds[CMEMS_SST_VARIABLE]
    for depth_name in ("depth", "elevation"):
        if depth_name in da.dims:
            da = da.isel({depth_name: 0})
            break

    if "time" in da.dims:
        times = da["time"].values
        try:
            idx = _idx_ultimo_disponible(times, ahora)
        except Exception:  # noqa: BLE001
            idx = -1
        da = da.isel(time=idx)
        fecha_raw = da.coords["time"].values
        try:
            fecha = np.datetime_as_string(fecha_raw, unit="m").replace("T", " ")
        except Exception:  # noqa: BLE001
            fecha = str(fecha_raw)[:16]
    else:
        fecha = ahora.strftime("%Y-%m-%d %H:%M")

    lat_name = _coord_name(da, ("latitude", "lat"))
    lon_name = _coord_name(da, ("longitude", "lon"))
    lats_all = np.asarray(da[lat_name].values, dtype=float)
    lons_all = np.asarray(da[lon_name].values, dtype=float)
    dlat = float(np.nanmedian(np.abs(np.diff(lats_all)))) if len(lats_all) > 1 else 0.042
    dlon = float(np.nanmedian(np.abs(np.diff(lons_all)))) if len(lons_all) > 1 else 0.042
    native = max(dlat, dlon, 0.01)
    stride = max(1, int(round(paso / native)))
    lats = lats_all[::stride]
    lons = lons_all[::stride]
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
            lat_c = round(float(lat), 4)
            lon_c = round(float(lon), 4)
            half = max(paso * 0.48, 0.06)
            if region.fraccion_mar(lat_c, lon_c, half) < region.umbral_mar:
                continue
            celdas.append({
                "lat": lat_c,
                "lon": lon_c,
                "sst_c": round(_to_celsius(raw), 2),
            })

    try:
        ds.close()
    except Exception:  # noqa: BLE001
        pass

    paso_out = stride * native
    out = _pack(
        region.densificar(celdas, paso=paso_out, umbral_mar=region.umbral_mar),
        region=region,
        fuente=region.fuente_cmems,
        fecha=fecha,
        paso=paso_out,
    )
    log.info(
        "CMEMS SST %s: %d celdas · fecha=%s · %.1f–%.1f °C",
        region.key,
        out["resumen"]["n_celdas"], fecha, out["resumen"]["sst_min_c"], out["resumen"]["sst_max_c"],
    )
    return out


def _malla_puntos(region: SstRegionConfig, paso: float) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    lat = float(region.lat_min)
    while lat <= float(region.lat_max) + 1e-9:
        lon = float(region.lon_min)
        while lon <= float(region.lon_max) + 1e-9:
            pts.append((round(lat, 4), round(lon, 4)))
            lon += paso
        lat += paso
    return pts


def _sst_actual_serie(temps: list, times: list) -> tuple[float | None, str | None]:
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    mejor: tuple[float | None, str | None] = (None, None)
    for ts, val in zip(times, temps):
        if val is None:
            continue
        t_txt = str(ts)
        if t_txt <= ahora:
            mejor = (float(val), t_txt[:16])
        elif mejor[0] is None:
            mejor = (float(val), t_txt[:16])
            break
    if mejor[0] is not None:
        return mejor
    for ts, val in zip(reversed(times), reversed(temps)):
        if val is not None:
            return float(val), str(ts)[:16]
    return None, None


def _desde_open_meteo(region: SstRegionConfig) -> dict:
    paso = max(0.08, float(region.paso_deg))
    puntos = _malla_puntos(region, paso)
    celdas: list[dict] = []
    fecha_ref: str | None = None
    half = max(paso * 0.48, 0.06)
    umbral_mar = 0.85

    for i in range(0, len(puntos), _OM_BATCH):
        if i > 0:
            time.sleep(0.9)
        batch = puntos[i : i + _OM_BATCH]
        data = None
        for attempt in range(3):
            try:
                data = fetch_json(OPEN_METEO_MARINE_URL, {
                    "latitude": ",".join(str(p[0]) for p in batch),
                    "longitude": ",".join(str(p[1]) for p in batch),
                    "hourly": "sea_surface_temperature",
                    "forecast_days": 1,
                    "timezone": "UTC",
                    "cell_selection": "sea",
                })
                break
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if "429" in msg or "too many requests" in msg:
                    sleep_s = 3.0 * (attempt + 1)
                    log.warning(
                        "Open-Meteo 429 %s lote %s (reintento %s/3): esperando %.1fs",
                        region.key, i // _OM_BATCH, attempt + 1, sleep_s,
                    )
                    time.sleep(sleep_s)
                    continue
                log.warning("Open-Meteo SST %s lote %s: %s", region.key, i // _OM_BATCH, exc)
                break
        if data is None:
            continue
        items = data if isinstance(data, list) else [data]
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            hourly = item.get("hourly") or {}
            temps = hourly.get("sea_surface_temperature") or []
            times = hourly.get("time") or []
            sst, ts = _sst_actual_serie(temps, times)
            if sst is None:
                continue
            if ts and (fecha_ref is None or ts > fecha_ref):
                fecha_ref = ts
            lat = round(float(item.get("latitude", batch[idx][0])), 4)
            lon = round(float(item.get("longitude", batch[idx][1])), 4)
            if region.fraccion_mar(lat, lon, half) < umbral_mar:
                continue
            celdas.append({
                "lat": lat,
                "lon": lon,
                "sst_c": round(sst, 2),
            })

    fecha = (fecha_ref or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"))[:16]
    out = _pack(
        region.densificar(celdas, paso=paso, umbral_mar=umbral_mar),
        region=region,
        fuente=f"Open-Meteo marine SST {region.key} (ultimo disponible)",
        fecha=fecha,
        paso=paso,
    )
    log.info(
        "Open-Meteo SST %s: %d celdas · %s · %.1f–%.1f °C",
        region.key,
        out["resumen"]["n_celdas"], fecha, out["resumen"]["sst_min_c"], out["resumen"]["sst_max_c"],
    )
    return out


def _descargar_sst_cuadricula(region: SstRegionConfig) -> dict:
    if _creds_ok():
        try:
            return _desde_cmems(region)
        except ImportError as exc:
            log.warning("CMEMS no disponible (%s)", exc)
            if not CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK:
                raise RuntimeError(
                    "CMEMS no disponible; activa CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK=1 "
                    "solo si aceptas gastar el cupo Open-Meteo de los KPIs"
                ) from exc
        except Exception as exc:  # noqa: BLE001
            log.warning("CMEMS %s falló (%s)", region.key, exc)
            if not CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK:
                raise RuntimeError(
                    f"CMEMS {region.key} falló ({exc}); fallback Open-Meteo malla desactivado "
                    "(protege cupo KPIs). Usa CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK=1 para forzar."
                ) from exc
    elif not CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK:
        raise RuntimeError(
            "Sin credenciales CMEMS; fallback Open-Meteo malla desactivado "
            "(protege cupo KPIs). Configura COPERNICUSMARINE_SERVICE_* "
            "o CMEMS_SST_ALLOW_OPEN_METEO_FALLBACK=1"
        )
    else:
        log.info("Sin credenciales CMEMS; SST %s vía Open-Meteo (ultimo disponible)", region.key)
    return _desde_open_meteo(region)


def descargar_sst_med_cuadricula() -> dict:
    """Cuadrícula SST del Mediterráneo para monitorización."""
    return _descargar_sst_cuadricula(REGION_MED)


def descargar_sst_cant_cuadricula() -> dict:
    """Cuadrícula SST del Cantábrico (IBI-Physics)."""
    return _descargar_sst_cuadricula(REGION_CANT)


def descargar_sst_atl_cuadricula() -> dict:
    """Cuadrícula SST del Atlántico gallego (IBI-Physics)."""
    return _descargar_sst_cuadricula(REGION_ATL)
