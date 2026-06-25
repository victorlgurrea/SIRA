"""HTTP seguro, AEMET y persistencia JSON."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import ALLOWED_HOSTS, DATA_DIR, DATA_FILE, HTTP_TIMEOUT

log = logging.getLogger(__name__)
AEMET_BASE = "https://opendata.aemet.es/opendata/api"


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


def fetch_aemet(path: str, api_key: str) -> dict | list:
    meta = _get_json(f"{AEMET_BASE}/{path.lstrip('/')}", headers={"api_key": api_key})
    datos = meta.get("datos") if isinstance(meta, dict) else None
    if not datos:
        raise ValueError("AEMET sin URL de datos")
    return _get_json(datos)


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


def read_dashboard() -> dict:
    data = read_json_file(DATA_FILE)
    if not data:
        return data
    from test_overlay import read_test_overlay

    overlay = read_test_overlay()
    if not overlay:
        return data
    sismos = [s for s in data.get("sismos", []) if s.get("id") != overlay.get("id")]
    return {**data, "sismos": [overlay, *sismos], "sismo_prueba_activo": True}


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
