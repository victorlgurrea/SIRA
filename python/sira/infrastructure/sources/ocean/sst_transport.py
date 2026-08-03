"""Límite de malla SST para transporte HTTP (PRO / Render)."""
from __future__ import annotations

import logging
import math

from sira.config.settings import CMEMS_SST_MAP_MAX_CELDAS

log = logging.getLogger(__name__)


def limitar_celdas_mapa(celdas: list[dict], max_n: int | None = None) -> list[dict]:
    """Reduce celdas con malla espacial (sin agujeros de muestreo cada N)."""
    limite = CMEMS_SST_MAP_MAX_CELDAS if max_n is None else int(max_n)
    if limite <= 0 or len(celdas) <= limite:
        return celdas

    lats = [float(c["lat"]) for c in celdas if c.get("sst_c") is not None]
    lons = [float(c["lon"]) for c in celdas if c.get("sst_c") is not None]
    if not lats:
        return celdas[:limite]

    lat_span = max(max(lats) - min(lats), 1e-3)
    lon_span = max(max(lons) - min(lons), 1e-3)
    # Paso ~uniforme para ~limite celdas en el bbox.
    paso = math.sqrt((lat_span * lon_span) / float(limite))
    paso = max(paso, 1e-3)

    buckets: dict[tuple[int, int], dict] = {}
    counts: dict[tuple[int, int], int] = {}
    for c in celdas:
        if c.get("sst_c") is None:
            continue
        lat = float(c["lat"])
        lon = float(c["lon"])
        key = (int(round(lat / paso)), int(round(lon / paso)))
        prev = buckets.get(key)
        if prev is None:
            buckets[key] = {
                "lat": lat,
                "lon": lon,
                "sst_c": float(c["sst_c"]),
            }
            counts[key] = 1
        else:
            n = counts[key] + 1
            counts[key] = n
            # Centroide + media SST dentro del bucket.
            prev["lat"] = (prev["lat"] * (n - 1) + lat) / n
            prev["lon"] = (prev["lon"] * (n - 1) + lon) / n
            prev["sst_c"] = (float(prev["sst_c"]) * (n - 1) + float(c["sst_c"])) / n

    out = list(buckets.values())
    if len(out) > limite:
        # Fallback: no crear agujeros regulares; recorta tras otro bin más grueso.
        paso2 = paso * math.sqrt(len(out) / float(limite)) * 1.05
        buckets2: dict[tuple[int, int], dict] = {}
        for c in out:
            key = (int(round(float(c["lat"]) / paso2)), int(round(float(c["lon"]) / paso2)))
            buckets2.setdefault(key, c)
        out = list(buckets2.values())[:limite]

    log.info(
        "SST mapa: limitando celdas %d → %d (max=%d, paso≈%.3f°)",
        len(celdas),
        len(out),
        limite,
        paso,
    )
    return out


def slim_sst_grid_for_transport(grid: dict | None, max_n: int | None = None) -> dict | None:
    """Copia superficial del grid con celdas limitadas (JSON ya ingestado en disco)."""
    if not isinstance(grid, dict):
        return grid
    celdas = grid.get("celdas")
    if not isinstance(celdas, list):
        return grid
    limited = limitar_celdas_mapa(celdas, max_n)
    if limited is celdas or len(limited) == len(celdas):
        return grid
    out = dict(grid)
    out["celdas"] = limited
    resumen = dict(out.get("resumen") or {})
    resumen["n_celdas"] = len(limited)
    resumen["n_celdas_origen"] = len(celdas)
    out["resumen"] = resumen
    lats_u = sorted({round(float(c["lat"]), 4) for c in limited})
    if len(lats_u) >= 2:
        diffs = [lats_u[i + 1] - lats_u[i] for i in range(len(lats_u) - 1) if lats_u[i + 1] > lats_u[i]]
        if diffs:
            out["paso_deg"] = round(sorted(diffs)[len(diffs) // 2], 4)
    return out
