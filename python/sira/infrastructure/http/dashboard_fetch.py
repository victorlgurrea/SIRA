"""Carga resiliente del dashboard (PRO: API dormida, 503 intermitentes, disco efímero)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from sira.config.settings import DATA_FILE, INGESTA_INTERVAL_MIN
from sira.infrastructure.http.client import read_dashboard, write_dashboard

log = logging.getLogger(__name__)

# Último payload bueno en memoria del proceso (stale si la API falla un rato).
_stale: dict | None = None
_last_snapshot_attempt: float = 0.0
_SNAPSHOT_RETRY_SEC = 30 * 60.0


def _payload_score(data: dict | None) -> int:
    """Puntuación simple: preferir payloads con contenido real (no solo generado_en)."""
    if not isinstance(data, dict) or not data.get("generado_en"):
        return 0
    oce = data.get("oceanografia") if isinstance(data.get("oceanografia"), dict) else {}
    oce_n = sum(
        len(v.get("serie_horaria") or [])
        for v in oce.values()
        if isinstance(v, dict)
    )
    return (
        len(data.get("sismos") or [])
        + len(data.get("incendios") or [])
        + len(data.get("embalses") or [])
        + len((data.get("sst_med_grid") or {}).get("celdas") or [])
        + len((data.get("sst_cant_grid") or {}).get("celdas") or [])
        + len((data.get("sst_atl_grid") or {}).get("celdas") or [])
        + min(oce_n, 500)
    )


def _parse_generado_en(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _local_is_stale(local: dict | None) -> bool:
    """True si no hay datos o superan el intervalo de ingesta configurado."""
    if not isinstance(local, dict) or not local.get("generado_en") or _payload_score(local) <= 0:
        return True
    gen = _parse_generado_en(local.get("generado_en"))
    if not gen:
        return True
    max_age_sec = max(float(INGESTA_INTERVAL_MIN), 60) * 60.0
    return (datetime.now(timezone.utc) - gen).total_seconds() > max_age_sec


def invalidate_dashboard_cache() -> None:
    """Tras restore-snapshot: forzar recarga en el proceso."""
    global _stale, _last_snapshot_attempt
    _stale = None
    _last_snapshot_attempt = 0.0


def _maybe_refresh_snapshot(local: dict | None, *, force: bool = False) -> dict:
    """Descarga snapshot GitHub si el JSON local falta o está desactualizado."""
    global _last_snapshot_attempt

    stale = _local_is_stale(local)
    if not stale and not force:
        return local if isinstance(local, dict) else {}

    now = time.monotonic()
    if (
        not force
        and not stale
        and (now - _last_snapshot_attempt) < _SNAPSHOT_RETRY_SEC
        and isinstance(local, dict)
        and local.get("generado_en")
    ):
        return local
    _last_snapshot_attempt = now

    if not _restore_snapshot_disk():
        return local if isinstance(local, dict) else {}

    refreshed = read_dashboard()
    if not isinstance(refreshed, dict) or not refreshed.get("generado_en"):
        return local if isinstance(local, dict) else {}

    local_gen = str((local or {}).get("generado_en") or "")
    new_gen = str(refreshed.get("generado_en") or "")
    if new_gen > local_gen or _payload_score(refreshed) > _payload_score(local):
        log.info("Snapshot más reciente: %s → %s", local_gen or "—", new_gen)
        return refreshed
    return local if isinstance(local, dict) else refreshed


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
            if isinstance(data, dict) and data.get("generado_en") and _payload_score(data) > 0:
                return data
            if isinstance(data, dict) and data.get("generado_en"):
                log.warning("API dashboard con generado_en pero sin contenido (%s)", base)
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


def bootstrap_dashboard_data(api_base: str) -> dict:
    """Arranque síncrono: snapshot GitHub → disco (antes del primer request Dash)."""
    global _stale
    local = read_dashboard()
    if _restore_snapshot_disk():
        refreshed = read_dashboard()
        if isinstance(refreshed, dict) and refreshed.get("generado_en"):
            local_gen = str(local.get("generado_en") or "")
            new_gen = str(refreshed.get("generado_en") or "")
            if not local_gen or new_gen >= local_gen:
                local = refreshed
    else:
        local = _maybe_refresh_snapshot(local)
    if local.get("generado_en") and _payload_score(local) > 0:
        _stale = local
        log.info(
            "Bootstrap: disco local generado_en=%s score=%d",
            local.get("generado_en"),
            _payload_score(local),
        )
        return local
    log.warning("Bootstrap: sin datos locales ni snapshot (%s)", DATA_FILE)
    return local if isinstance(local, dict) else {}


def _pick_fresher(a: dict | None, b: dict | None) -> dict:
    """Elige el payload con generado_en más reciente (y score > 0)."""
    cand = []
    for d in (a, b):
        if isinstance(d, dict) and d.get("generado_en") and _payload_score(d) > 0:
            cand.append(d)
    if not cand:
        return a if isinstance(a, dict) else (b if isinstance(b, dict) else {})
    if len(cand) == 1:
        return cand[0]
    return max(cand, key=lambda d: str(d.get("generado_en") or ""))


def load_dashboard_payload(api_base: str) -> dict:
    """
    Prefiere el payload más reciente entre snapshot GitHub y API.
    Así, tras una ingesta, el mapa no se queda en un snapshot viejo si la API ya avanzó.
    """
    global _stale

    local = _maybe_refresh_snapshot(read_dashboard())
    fresh = _fetch_dashboard_api(api_base)
    chosen = _pick_fresher(local, fresh)

    if chosen.get("generado_en") and _payload_score(chosen) > 0:
        # Si ganó la API y es más nueva que el disco, cachear para siguientes lecturas.
        local_gen = str((local or {}).get("generado_en") or "")
        if fresh is chosen and str(fresh.get("generado_en") or "") > local_gen:
            try:
                write_dashboard(fresh)
            except OSError as exc:
                log.warning("No se pudo cachear dashboard en disco: %s", exc)
        _stale = chosen
        return chosen

    if _stale and _stale.get("generado_en"):
        log.warning("Usando datos en memoria (sin snapshot ni API)")
        return _stale

    return local if isinstance(local, dict) else {}


def ensure_dashboard_on_disk() -> dict:
    """Disco local o snapshot GitHub, sin bloquear en /api/dashboard."""
    local = _maybe_refresh_snapshot(read_dashboard(), force=_local_is_stale(read_dashboard()))
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
