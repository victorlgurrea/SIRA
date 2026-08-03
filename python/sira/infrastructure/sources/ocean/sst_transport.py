"""Límite de malla SST para transporte HTTP (PRO / Render)."""
from __future__ import annotations

import logging
import math

from sira.config.settings import CMEMS_SST_MAP_MAX_CELDAS

log = logging.getLogger(__name__)


def limitar_celdas_mapa(celdas: list[dict], max_n: int | None = None) -> list[dict]:
    """Submuestrea la malla para que el JSON del dashboard quepa en PRO."""
    limite = CMEMS_SST_MAP_MAX_CELDAS if max_n is None else int(max_n)
    if limite <= 0 or len(celdas) <= limite:
        return celdas
    step = math.ceil(len(celdas) / limite)
    out = celdas[::step][:limite]
    log.info(
        "SST mapa: limitando celdas %d → %d (max=%d, step=%d)",
        len(celdas),
        len(out),
        limite,
        step,
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
    return out
