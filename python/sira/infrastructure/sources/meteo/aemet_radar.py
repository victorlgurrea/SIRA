"""Radar de precipitación AEMET (reflectividad) vía OpenData.

Producto principal: composición nacional (`red/radar/nacional`) — GIF con
manchas dBZ como el visor público de AEMET. Si OpenData no tiene el mosaico
(404 temporal), el dashboard cae a RainViewer (tiles radar) en el cliente.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from sira.config.settings import AEMET_API_KEY
from sira.infrastructure.http.client import fetch_aemet_bytes

log = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "bytes": None,
    "content_type": "image/gif",
    "error": None,
}
_TTL_OK_SEC = 180.0
_TTL_ERR_SEC = 60.0


def aemet_radar_configurado() -> bool:
    return bool((AEMET_API_KEY or "").strip())


def radar_nacional_bytes(*, force: bool = False) -> tuple[bytes | None, str, str | None]:
    """Devuelve (contenido, content_type, error). Cache corta para no saturar AEMET."""
    now = time.monotonic()
    cached = _CACHE.get("bytes")
    err = _CACHE.get("error")
    age = now - float(_CACHE.get("ts") or 0)
    ttl = _TTL_OK_SEC if cached else _TTL_ERR_SEC
    if not force and age < ttl and (cached is not None or err):
        return cached, str(_CACHE.get("content_type") or "image/gif"), err  # type: ignore[return-value]

    if not aemet_radar_configurado():
        _CACHE.update({"ts": now, "bytes": None, "error": "AEMET_API_KEY no configurada"})
        return None, "image/gif", "AEMET_API_KEY no configurada"

    try:
        data = fetch_aemet_bytes("red/radar/nacional", AEMET_API_KEY, timeout=45)
    except (requests.RequestException, ValueError, OSError) as exc:
        msg = str(exc) or type(exc).__name__
        # OpenData a veces responde JSON 404 "Error al obtener los datos"
        # envuelto en HTTPError o ValueError.
        log.warning("AEMET radar nacional no disponible: %s", msg)
        _CACHE.update({"ts": now, "bytes": None, "error": msg})
        return None, "image/gif", msg
    except Exception as exc:  # noqa: BLE001
        log.exception("AEMET radar nacional falló")
        _CACHE.update({"ts": now, "bytes": None, "error": str(exc)})
        return None, "image/gif", str(exc)

    if not data or len(data) < 100:
        _CACHE.update({"ts": now, "bytes": None, "error": "imagen vacía"})
        return None, "image/gif", "imagen vacía"

    # Si OpenData devolvió JSON de error en "datos", no es una imagen.
    if data[:1] in (b"{", b"[") or data[:8].startswith(b"<!DOC"):
        _CACHE.update({"ts": now, "bytes": None, "error": "OpenData sin imagen de radar"})
        return None, "image/gif", "OpenData sin imagen de radar"

    ctype = "image/gif"
    if data[:8].startswith(b"\x89PNG"):
        ctype = "image/png"
    elif data[:2] == b"\xff\xd8":
        ctype = "image/jpeg"
    elif not data[:3].startswith(b"GIF"):
        _CACHE.update({"ts": now, "bytes": None, "error": "formato de radar no reconocido"})
        return None, "image/gif", "formato de radar no reconocido"
    _CACHE.update({"ts": now, "bytes": data, "content_type": ctype, "error": None})
    return data, ctype, None


def radar_nacional_estado() -> dict[str, Any]:
    data, ctype, err = radar_nacional_bytes()
    return {
        "ok": data is not None,
        "content_type": ctype,
        "bytes": len(data) if data else 0,
        "detail": err,
        "fuente": "AEMET OpenData · composición nacional (reflectividad)",
    }
