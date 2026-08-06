"""Carga resiliente del dashboard (PRO: API dormida, 503 intermitentes, disco efímero)."""
from __future__ import annotations

import logging
import time

import requests

from sira.config.settings import DATA_FILE
from sira.infrastructure.http.client import read_dashboard, write_dashboard

log = logging.getLogger(__name__)

# Último payload bueno en memoria del proceso (stale si la API falla un rato).
_stale: dict | None = None


def wake_api(api_base: str, *, attempts: int = 3, timeout: float = 8.0) -> bool:
    """Despierta sira-api en Render Free (pocos intentos; no bloquear la UI)."""
    base = (api_base or "").rstrip("/")
    if not base:
        return False
    for i in range(max(1, attempts)):
        try:
            r = requests.get(f"{base}/api/health", timeout=timeout)
            if r.status_code < 500:
                return True
        except requests.RequestException as exc:
            log.debug("wake_api intento %s: %s", i + 1, exc)
        if i + 1 < attempts:
            time.sleep(min(1.5 + i, 4.0))
    return False


def _fetch_dashboard_api(api_base: str) -> dict | None:
    base = (api_base or "").rstrip("/")
    if not base:
        return None
    wake_api(base, attempts=3, timeout=10.0)
    for attempt in range(3):
        try:
            r = requests.get(
                f"{base}/api/dashboard",
                timeout=35,
                headers={"Accept-Encoding": "gzip"},
            )
            if r.status_code in (502, 503, 504) and attempt < 2:
                log.info("API dashboard %s; reintento %s", r.status_code, attempt + 1)
                time.sleep(2 + attempt * 2)
                continue
            if not r.ok:
                log.warning("API dashboard HTTP %s", r.status_code)
                return None
            data = r.json()
            if isinstance(data, dict) and data.get("generado_en"):
                return data
            return None
        except (requests.RequestException, ValueError) as exc:
            log.warning("API dashboard error (intento %s): %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 + attempt)
    return None


def _restore_snapshot_disk() -> bool:
    try:
        from sira.infrastructure.persistence.snapshot import download_snapshot

        return bool(download_snapshot())
    except Exception as exc:  # noqa: BLE001
        log.warning("Snapshot GitHub no disponible: %s", exc)
        return False


def load_dashboard_payload(api_base: str) -> dict:
    """
    Orden: API (con reintentos) → disco local → snapshot GitHub → stale en memoria.
    Si la API responde, persiste en DATA_FILE para el resto del ciclo de vida del contenedor.
    """
    global _stale

    fresh = _fetch_dashboard_api(api_base)
    if fresh:
        _stale = fresh
        try:
            write_dashboard(fresh)
        except OSError as exc:
            log.warning("No se pudo cachear dashboard en disco: %s", exc)
            return fresh
        cached = read_dashboard()
        return cached if cached.get("generado_en") else fresh

    local = read_dashboard()
    if local.get("generado_en"):
        _stale = local
        return local

    if _restore_snapshot_disk():
        local = read_dashboard()
        if local.get("generado_en"):
            _stale = local
            log.info("Dashboard desde snapshot GitHub (generado_en=%s)", local.get("generado_en"))
            return local

    if _stale and _stale.get("generado_en"):
        log.warning("Usando datos en memoria (API no disponible)")
        return _stale

    return local if isinstance(local, dict) else {}


def ensure_dashboard_on_disk() -> dict:
    """Disco local o snapshot GitHub, sin bloquear en /api/dashboard."""
    local = read_dashboard()
    if local.get("generado_en"):
        return local
    if _restore_snapshot_disk():
        local = read_dashboard()
        if local.get("generado_en"):
            return local
    return local if isinstance(local, dict) else {}


def fetch_status_api(api_base: str) -> dict | None:
    """GET /api/status con despertar breve y reintentos (fail-fast para /status)."""
    base = (api_base or "").rstrip("/")
    if not base:
        return None
    wake_api(base, attempts=2, timeout=8.0)
    for attempt in range(2):
        try:
            r = requests.get(f"{base}/api/status", timeout=12)
            if r.status_code in (502, 503, 504) and attempt < 1:
                time.sleep(2)
                continue
            if not r.ok:
                return None
            payload = r.json()
            return payload if isinstance(payload, dict) else None
        except (requests.RequestException, ValueError):
            if attempt < 1:
                time.sleep(1.5)
    return None
