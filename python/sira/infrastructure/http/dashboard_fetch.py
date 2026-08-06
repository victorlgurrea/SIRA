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


def wake_api(api_base: str, *, attempts: int = 2, timeout: float = 6.0) -> bool:
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
            time.sleep(min(1.0 + i, 3.0))
    return False


def _fetch_dashboard_api(api_base: str) -> dict | None:
    base = (api_base or "").rstrip("/")
    if not base:
        return None
    wake_api(base, attempts=2, timeout=8.0)
    for attempt in range(2):
        try:
            r = requests.get(
                f"{base}/api/dashboard",
                timeout=25,
                headers={"Accept-Encoding": "gzip"},
            )
            if r.status_code in (502, 503, 504) and attempt < 1:
                log.info("API dashboard %s; reintento %s", r.status_code, attempt + 1)
                time.sleep(2)
                continue
            if not r.ok:
                log.warning("API dashboard HTTP %s (%s)", r.status_code, base)
                return None
            data = r.json()
            if isinstance(data, dict) and data.get("generado_en"):
                return data
            return None
        except (requests.RequestException, ValueError) as exc:
            log.warning("API dashboard error (intento %s): %s", attempt + 1, exc)
            if attempt < 1:
                time.sleep(1.5)
    return None


def _restore_snapshot_disk() -> bool:
    try:
        from sira.infrastructure.persistence.snapshot import download_snapshot

        ok = bool(download_snapshot())
        if ok:
            log.info("Snapshot GitHub restaurado en %s", DATA_FILE)
        return ok
    except Exception as exc:  # noqa: BLE001
        log.warning("Snapshot GitHub no disponible: %s", exc)
        return False


def load_dashboard_payload(api_base: str) -> dict:
    """
    Orden óptimo en PRO Free:
      1) disco local
      2) snapshot GitHub (si disco vacío) — no esperar a la API
      3) API (y cachear en disco si responde)
      4) stale en memoria
    """
    global _stale

    local = read_dashboard()
    if local.get("generado_en"):
        _stale = local
    elif _restore_snapshot_disk():
        local = read_dashboard()
        if local.get("generado_en"):
            _stale = local
            log.info("Dashboard desde snapshot GitHub (generado_en=%s)", local.get("generado_en"))

    fresh = _fetch_dashboard_api(api_base)
    if fresh:
        # Preferir API si trae datos (más fresco que snapshot).
        if (not local.get("generado_en")) or (fresh.get("generado_en") >= local.get("generado_en", "")):
            _stale = fresh
            try:
                write_dashboard(fresh)
            except OSError as exc:
                log.warning("No se pudo cachear dashboard en disco: %s", exc)
                return fresh
            cached = read_dashboard()
            return cached if cached.get("generado_en") else fresh

    if local.get("generado_en"):
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
    wake_api(base, attempts=1, timeout=6.0)
    try:
        r = requests.get(f"{base}/api/status", timeout=10)
        if not r.ok:
            return None
        payload = r.json()
        return payload if isinstance(payload, dict) else None
    except (requests.RequestException, ValueError):
        return None
