"""Cuadrícula SST Mediterráneo (Copernicus Marine CMEMS L4 + fallback Open-Meteo)."""
from __future__ import annotations

import logging
import math
import time
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
    CMEMS_SST_VARIABLE,
    CMEMS_USERNAME,
    OPEN_METEO_MARINE_URL,
)
from sira.infrastructure.geo.mar_mediterraneo import fraccion_mar_celda, punto_en_mar_mediterraneo
from sira.infrastructure.http.client import fetch_json

log = logging.getLogger(__name__)

_NATIVE_DEG = 0.0625
_KELVIN_FLOOR = 200.0
_OM_BATCH = 60


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
    """Último timestep disponible <= ahora; si no, el último del dataset."""
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


def _rellenar_huecos_mar(
    celdas: list[dict],
    *,
    paso: float,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
) -> list[dict]:
    """Rellena huecos de mar con interpolación local simple."""
    if not celdas:
        return celdas
    idx = {
        (round(float(c["lat"]), 4), round(float(c["lon"]), 4)): float(c["sst_c"])
        for c in celdas
        if c.get("sst_c") is not None
    }
    out = list(celdas)
    step = round(float(paso), 4)
    half = max(step * 0.5, 0.06)

    lat = round(float(lat_min), 4)
    while lat <= round(float(lat_max), 4) + 1e-9:
        lon = round(float(lon_min), 4)
        while lon <= round(float(lon_max), 4) + 1e-9:
            key = (round(lat, 4), round(lon, 4))
            if key not in idx and punto_en_mar_mediterraneo(key[0], key[1]):
                if fraccion_mar_celda(key[0], key[1], half) >= 0.55:
                    vecinos: list[tuple[float, float]] = []
                    for radius in (1, 2, 3):
                        for di in range(-radius, radius + 1):
                            for dj in range(-radius, radius + 1):
                                if di == 0 and dj == 0:
                                    continue
                                nk = (round(lat + di * step, 4), round(lon + dj * step, 4))
                                if nk in idx:
                                    dist = max(abs(di), abs(dj))
                                    vecinos.append((idx[nk], 1.0 / dist))
                        if len(vecinos) >= 2:
                            break
                    if vecinos:
                        num = sum(val * w for val, w in vecinos)
                        den = sum(w for _, w in vecinos)
                        temp = round(num / den, 2)
                        idx[key] = temp
                        out.append({"lat": key[0], "lon": key[1], "sst_c": temp})
            lon = round(lon + step, 4)
        lat = round(lat + step, 4)
    return out


def _pack(celdas: list[dict], *, fuente: str, dataset_id: str, fecha: str, paso: float) -> dict:
    if not celdas:
        raise RuntimeError(f"{fuente}: sin celdas válidas en el bbox solicitado")
    sst_vals = [c["sst_c"] for c in celdas]
    return {
        "fuente": fuente,
        "dataset_id": dataset_id,
        "fecha": fecha,
        "paso_deg": round(paso, 4),
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


def _desde_cmems() -> dict:
    import copernicusmarine

    ahora = datetime.now(timezone.utc)
    # Ventana corta: análisis/previsión horaria actual (Med-Physics).
    inicio = ahora - timedelta(days=2)
    paso = max(0.042, float(CMEMS_SST_PASO_DEG))

    log.info(
        "CMEMS SST actual: dataset=%s var=%s bbox=[%.2f,%.2f]×[%.2f,%.2f] paso≈%.3f°",
        CMEMS_SST_DATASET_ID,
        CMEMS_SST_VARIABLE,
        CMEMS_SST_LAT_MIN,
        CMEMS_SST_LAT_MAX,
        CMEMS_SST_LON_MIN,
        CMEMS_SST_LON_MAX,
        paso,
    )

    open_kwargs = dict(
        dataset_id=CMEMS_SST_DATASET_ID,
        variables=[CMEMS_SST_VARIABLE],
        minimum_longitude=CMEMS_SST_LON_MIN,
        maximum_longitude=CMEMS_SST_LON_MAX,
        minimum_latitude=CMEMS_SST_LAT_MIN,
        maximum_latitude=CMEMS_SST_LAT_MAX,
        start_datetime=inicio.strftime("%Y-%m-%dT00:00:00"),
        end_datetime=ahora.strftime("%Y-%m-%dT23:59:59"),
        username=CMEMS_USERNAME.strip(),
        password=CMEMS_PASSWORD.strip(),
    )
    # Compatibilidad entre versiones de copernicusmarine.
    try:
        ds = copernicusmarine.open_dataset(**open_kwargs, disable_progress_bar=True)
    except TypeError:
        ds = copernicusmarine.open_dataset(**open_kwargs)

    if CMEMS_SST_VARIABLE not in ds:
        raise RuntimeError(f"Dataset CMEMS sin variable {CMEMS_SST_VARIABLE}")

    da = ds[CMEMS_SST_VARIABLE]
    # Productos 3D: quedarnos en superficie (primer nivel de profundidad).
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
    # Estimar resolución nativa y remuestrear al paso configurado.
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
            # Filtro “solo mar” con máscara más pequeña para no comerse costa.
            half = max(paso * 0.48, 0.06)
            half_mask = max(0.02, half * 0.35)
            if fraccion_mar_celda(lat_c, lon_c, half_mask) < 0.8:
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

    out = _pack(
        _rellenar_huecos_mar(
            celdas,
            paso=stride * native,
            lat_min=float(np.min(lats)),
            lat_max=float(np.max(lats)),
            lon_min=float(np.min(lons)),
            lon_max=float(np.max(lons)),
        ),
        fuente="Copernicus Med-Physics SST (ultimo disponible)",
        dataset_id=CMEMS_SST_DATASET_ID,
        fecha=fecha,
        paso=stride * native,
    )
    log.info(
        "CMEMS SST: %d celdas · fecha=%s · %.1f–%.1f °C",
        out["resumen"]["n_celdas"], fecha, out["resumen"]["sst_min_c"], out["resumen"]["sst_max_c"],
    )
    return out


def _malla_puntos(paso: float) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    lat = float(CMEMS_SST_LAT_MIN)
    while lat <= float(CMEMS_SST_LAT_MAX) + 1e-9:
        lon = float(CMEMS_SST_LON_MIN)
        while lon <= float(CMEMS_SST_LON_MAX) + 1e-9:
            pts.append((round(lat, 4), round(lon, 4)))
            lon += paso
        lat += paso
    return pts


def _sst_actual_serie(temps: list, times: list) -> tuple[float | None, str | None]:
    """Última temperatura no nula (hora actual / más reciente)."""
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


def _desde_open_meteo() -> dict:
    """SST horaria actual por malla (Open-Meteo marine). Sin cuenta CMEMS."""
    paso = max(0.08, float(CMEMS_SST_PASO_DEG))
    puntos = _malla_puntos(paso)
    celdas: list[dict] = []
    fecha_ref: str | None = None
    half = paso * 0.5
    half_mask = max(0.02, half * 0.35)
    umbral_mar = 0.8

    data = None
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
                # Backoff específico para rate-limit.
                if "429" in msg or "too many requests" in msg:
                    sleep_s = 3.0 * (attempt + 1)
                    log.warning("Open-Meteo 429 lote %s (reintento %s/3): esperando %.1fs", i // _OM_BATCH, attempt + 1, sleep_s)
                    time.sleep(sleep_s)
                    continue
                log.warning("Open-Meteo SST lote %s: %s", i // _OM_BATCH, exc)
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
            if fraccion_mar_celda(lat, lon, half_mask) < umbral_mar:
                continue
            celdas.append({
                "lat": lat,
                "lon": lon,
                "sst_c": round(sst, 2),
            })

    fecha = (fecha_ref or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"))[:16]
    out = _pack(
        celdas,
        fuente="Open-Meteo marine SST (ultimo disponible)",
        dataset_id="open-meteo-marine",
        fecha=fecha,
        paso=paso,
    )
    log.info(
        "Open-Meteo SST: %d celdas · %s · %.1f–%.1f °C",
        out["resumen"]["n_celdas"], fecha, out["resumen"]["sst_min_c"], out["resumen"]["sst_max_c"],
    )
    return out


def descargar_sst_med_cuadricula() -> dict:
    """
    Cuadrícula SST del Mediterráneo para monitorización.

    Prioridad: CMEMS L4 (si hay credenciales y paquete). Fallback: Open-Meteo marine.
    Se usa el último dato disponible dentro de la ventana reciente.
    """
    if _creds_ok():
        try:
            return _desde_cmems()
        except ImportError as exc:
            log.warning("CMEMS no disponible (%s); fallback Open-Meteo", exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("CMEMS falló (%s); fallback Open-Meteo", exc)
    else:
        log.info("Sin credenciales CMEMS; SST Med vía Open-Meteo (ultimo disponible)")
    return _desde_open_meteo()
