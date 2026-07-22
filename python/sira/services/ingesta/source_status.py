"""Estado de fuentes durante la ingesta."""
from __future__ import annotations

import logging
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)


def fmt_error_fuente(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError):
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code == 429:
            return "Límite temporal AEMET (429). Reintento automático en próximos ciclos."
    return str(exc)


def estado_fuente(
    nombre: str,
    fn: Callable[..., Any],
    *args,
    default=None,
    **kwargs,
) -> tuple[Any, dict]:
    try:
        out = fn(*args, **kwargs)
        n = len(out) if isinstance(out, (list, dict)) else 1
        return out, {"ok": True, "registros": n, "error": None}
    except Exception as exc:  # noqa: BLE001
        log.warning("%s: %s", nombre, exc)
        return default, {"ok": False, "registros": 0, "error": str(exc)}
