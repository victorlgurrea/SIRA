"""Límite de malla SST para transporte HTTP (PRO / Render)."""
from __future__ import annotations

import logging
import math

from sira.config.settings import CMEMS_SST_MAP_MAX_CELDAS

log = logging.getLogger(__name__)


def _bucketizar(validos: list[dict], paso: float) -> list[dict]:
    buckets: dict[tuple[int, int], dict] = {}
    counts: dict[tuple[int, int], int] = {}
    for c in validos:
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
    return list(buckets.values())


def limitar_celdas_mapa(celdas: list[dict], max_n: int | None = None) -> list[dict]:
    """Reduce celdas con malla espacial (sin agujeros de muestreo cada N)."""
    limite = CMEMS_SST_MAP_MAX_CELDAS if max_n is None else int(max_n)
    if limite <= 0 or len(celdas) <= limite:
        return celdas

    validos = [c for c in celdas if c.get("sst_c") is not None]
    if not validos:
        return celdas[:limite]

    lats = [float(c["lat"]) for c in validos]
    lons = [float(c["lon"]) for c in validos]
    lat_span = max(max(lats) - min(lats), 1e-3)
    lon_span = max(max(lons) - min(lons), 1e-3)
    # Paso ~uniforme para ~limite celdas en el bbox rectangular de las celdas.
    # OJO: esta primera estimación asume densidad uniforme en todo el
    # rectángulo lat/lon; para mares alargados/estrechos dentro de un
    # rectángulo mucho mayor (p. ej. el Mediterráneo completo, que ocupa una
    # fracción pequeña de su propio bbox Europa–Magreb–Levante) sale
    # demasiado gruesa y colapsa muchas más celdas de las previstas. Por eso
    # se reescala iterativamente contra el recuento real de buckets.
    paso = math.sqrt((lat_span * lon_span) / float(limite))
    paso = max(paso, 1e-4)

    out = _bucketizar(validos, paso)
    for _ in range(10):
        n = len(out)
        if n == 0:
            paso *= 0.5
        elif n > limite:
            paso *= math.sqrt(n / float(limite)) * 1.02
        elif n < limite * 0.92:
            # Undershoot (mar con forma irregular, p. ej. una franja estrecha
            # dentro de un bbox mucho mayor): afinar en vez de dejar huecos
            # enormes en el mapa. Converge en 1-2 iteraciones en la práctica.
            paso *= math.sqrt(n / float(limite))
        else:
            break
        paso = max(paso, 1e-4)
        out = _bucketizar(validos, paso)

    if len(out) > limite:
        out = out[:limite]

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
