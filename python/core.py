"""HTTP seguro, AEMET y persistencia JSON."""
from __future__ import annotations

import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from config import AEMET_API_KEY, ALLOWED_HOSTS, DATA_DIR, DATA_FILE, HTTP_TIMEOUT

log = logging.getLogger(__name__)
AEMET_BASE = "https://opendata.aemet.es/opendata/api"
HORA_ESPAÑA = ZoneInfo("Europe/Madrid")


def fmt_ingesta_local(value: str | None) -> str:
    """Fecha y hora local (España) para mostrar última ingesta: dd/mm/aaaa — HH:MM."""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(HORA_ESPAÑA).strftime("%d/%m/%Y — %H:%M")
    except (ValueError, TypeError):
        return str(value)


def fmt_hora_espana(value: str | None) -> str:
    """Alias de compatibilidad."""
    return fmt_ingesta_local(value)


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"URL no permitida: {url}")


def _get_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict | list:
    _check_url(url)
    r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=False)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, (dict, list)):
        raise ValueError("Respuesta JSON inválida")
    return data


def fetch_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict | list:
    return _get_json(url, params=params, headers=headers)


def fetch_text(url: str, params: dict | None = None, headers: dict | None = None) -> str:
    _check_url(url)
    r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=False)
    r.raise_for_status()
    return r.text


def fetch_aemet(path: str, api_key: str) -> dict | list:
    meta = _get_json(f"{AEMET_BASE}/{path.lstrip('/')}", headers={"api_key": api_key})
    datos = meta.get("datos") if isinstance(meta, dict) else None
    if not datos:
        raise ValueError("AEMET sin URL de datos")
    return _get_json(datos)


def fetch_aemet_bytes(path: str, api_key: str, *, timeout: int | None = None) -> bytes:
    """Devuelve el contenido binario del recurso AEMET (ej. CAP tar.gz)."""
    meta = _get_json(f"{AEMET_BASE}/{path.lstrip('/')}", headers={"api_key": api_key})
    datos = meta.get("datos") if isinstance(meta, dict) else None
    if not datos:
        raise ValueError("AEMET sin URL de datos")
    _check_url(datos)
    r = requests.get(datos, timeout=timeout or HTTP_TIMEOUT, allow_redirects=False)
    r.raise_for_status()
    return r.content


def fetch_bytes(url: str, *, timeout: int | None = None) -> bytes:
    """Descarga binaria de un host permitido (p. ej. tar.gz CAP de www.aemet.es)."""
    _check_url(url)
    r = requests.get(url, timeout=timeout or HTTP_TIMEOUT, allow_redirects=False)
    r.raise_for_status()
    return r.content


def post_json(url: str, body: dict) -> dict:
    _check_url(url)
    r = requests.post(url, json=body, timeout=HTTP_TIMEOUT, allow_redirects=False)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("Respuesta JSON inválida")
    return data


def _safe_data_path(path: Path) -> Path:
    resolved = path.resolve()
    root = DATA_DIR.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Ruta fuera de data/processed: {path}")
    return resolved


def read_json_file(path: Path) -> dict:
    path = _safe_data_path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("JSON ilegible (%s): %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


_meteo_live_cache: dict = {"at": 0.0, "alerts": [], "ttl_sec": 90.0}
METEO_LIVE_CACHE_SEC = 90
METEO_LIVE_BACKOFF_429_SEC = 600


def clear_meteo_live_cache() -> None:
    _meteo_live_cache["at"] = 0.0
    _meteo_live_cache["alerts"] = []
    _meteo_live_cache["ttl_sec"] = float(METEO_LIVE_CACHE_SEC)


def _is_http_429(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status == 429
    return False


def _live_meteo_alerts() -> list[dict]:
    """Avisos AEMET activos (CAP), con caché breve para no saturar la API."""
    now = time.monotonic()
    ttl_sec = float(_meteo_live_cache.get("ttl_sec", METEO_LIVE_CACHE_SEC))
    if now - float(_meteo_live_cache.get("at", 0)) < ttl_sec:
        return list(_meteo_live_cache.get("alerts", []))
    try:
        from aemet_alerts import fetch_vigentes_alerts

        alerts = fetch_vigentes_alerts(AEMET_API_KEY or None)
        _meteo_live_cache["ttl_sec"] = float(METEO_LIVE_CACHE_SEC)
    except Exception as exc:  # noqa: BLE001
        if _is_http_429(exc):
            # Evita saturar AEMET cuando aplica rate limit.
            _meteo_live_cache["ttl_sec"] = float(METEO_LIVE_BACKOFF_429_SEC)
            log.warning("AEMET CAP 429: backoff %ss", METEO_LIVE_BACKOFF_429_SEC)
        else:
            _meteo_live_cache["ttl_sec"] = float(METEO_LIVE_CACHE_SEC)
            log.warning("AEMET CAP en read_dashboard: %s", exc)
        alerts = list(_meteo_live_cache.get("alerts", []))
    _meteo_live_cache["at"] = now
    _meteo_live_cache["alerts"] = alerts
    return alerts


def read_dashboard() -> dict:
    data = read_json_file(DATA_FILE)
    if not data:
        return data
    from test_overlay import read_test_overlays
    from test_meteo_alerts import read_active_test_alerts

    overlay_list = read_test_overlays()
    out = dict(data)
    if overlay_list:
        overlay_ids = {str(o.get("id")) for o in overlay_list if o.get("id")}
        sismos = [s for s in data.get("sismos", []) if str(s.get("id") or "") not in overlay_ids]
        out["sismos"] = [*overlay_list, *sismos]
        if any(o.get("es_prueba") for o in overlay_list):
            out["sismo_prueba_activo"] = True
        out["sismos_prueba_activos"] = len(overlay_list)

    meteo_tests = read_active_test_alerts()
    if meteo_tests:
        out["meteo_alertas_test"] = meteo_tests
    meteo_live = _live_meteo_alerts()
    if meteo_live:
        out["meteo_alertas_live"] = meteo_live
    elif data.get("meteo_alertas_cap"):
        out["meteo_alertas_live"] = list(data.get("meteo_alertas_cap") or [])
    return out


def write_dashboard(payload: dict) -> Path:
    path = _safe_data_path(DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        Path(tmp).replace(path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
