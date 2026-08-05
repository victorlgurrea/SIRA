"""Snapshot: sube/descarga dashboard_data.json.gz a un GitHub Release «latest-data».

Requiere la variable GITHUB_TOKEN (con scope `repo` o `contents:write`).
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
from pathlib import Path

import requests

from sira.config.settings import DATA_FILE

log = logging.getLogger(__name__)

_OWNER_REPO = os.getenv("GITHUB_REPOSITORY", "victorlgurrea/SIRA")
_TAG = "latest-data"
_ASSET_NAME = "dashboard_data.json.gz"
_API = "https://api.github.com"
_TIMEOUT = 60


def _headers(token: str | None = None) -> dict[str, str]:
    tok = token or os.getenv("GITHUB_TOKEN", "")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


# --- Upload ---

def upload_snapshot(token: str | None = None) -> bool:
    """Sube dashboard_data.json comprimido al release «latest-data». Retorna True si OK."""
    tok = token or os.getenv("GITHUB_TOKEN", "")
    if not tok:
        log.warning("GITHUB_TOKEN no configurado; no se sube snapshot")
        return False
    if not DATA_FILE.is_file():
        log.warning("No existe %s; nada que subir", DATA_FILE)
        return False

    data = DATA_FILE.read_bytes()
    compressed = gzip.compress(data, compresslevel=6)
    log.info("Snapshot: %s → %.1f KB comprimido", DATA_FILE.name, len(compressed) / 1024)

    hdr = _headers(tok)

    # 1. Obtener o crear el release
    url_rel = f"{_API}/repos/{_OWNER_REPO}/releases/tags/{_TAG}"
    r = requests.get(url_rel, headers=hdr, timeout=_TIMEOUT)
    if r.status_code == 404:
        r = requests.post(
            f"{_API}/repos/{_OWNER_REPO}/releases",
            headers=hdr,
            json={
                "tag_name": _TAG,
                "name": "Último snapshot de datos",
                "body": "Generado automáticamente por el workflow de ingesta.",
                "prerelease": True,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
    elif not r.ok:
        log.error("Error obteniendo release: %s %s", r.status_code, r.text[:200])
        return False
    release = r.json()
    release_id = release["id"]
    upload_url = release["upload_url"].split("{")[0]

    # 2. Borrar asset anterior si existe
    for asset in release.get("assets", []):
        if asset["name"] == _ASSET_NAME:
            requests.delete(
                f"{_API}/repos/{_OWNER_REPO}/releases/assets/{asset['id']}",
                headers=hdr,
                timeout=_TIMEOUT,
            )

    # 3. Subir
    r = requests.post(
        upload_url,
        headers={**hdr, "Content-Type": "application/gzip"},
        params={"name": _ASSET_NAME},
        data=compressed,
        timeout=120,
    )
    if r.ok:
        log.info("Snapshot subido (%d bytes)", len(compressed))
        return True
    log.error("Error subiendo snapshot: %s %s", r.status_code, r.text[:200])
    return False


# --- Download ---

def download_snapshot(token: str | None = None) -> bool:
    """Descarga el snapshot más reciente a DATA_FILE. Retorna True si OK.

    En repos públicos funciona sin token (descarga directa del asset).
    """
    hdr = _headers(token)

    url_rel = f"{_API}/repos/{_OWNER_REPO}/releases/tags/{_TAG}"
    try:
        r = requests.get(url_rel, headers=hdr, timeout=_TIMEOUT)
    except requests.RequestException as e:
        log.warning("No se pudo comprobar release: %s", e)
        return False
    if r.status_code == 404:
        log.info("No existe release %s; sin snapshot previo", _TAG)
        return False
    if not r.ok:
        log.warning("Error comprobando release: %s", r.status_code)
        return False

    assets = r.json().get("assets", [])
    asset = next((a for a in assets if a["name"] == _ASSET_NAME), None)
    if not asset:
        log.info("Release sin asset %s", _ASSET_NAME)
        return False

    # Intentar descarga directa (browser_download_url funciona en repos públicos)
    download_url = asset.get("browser_download_url") or asset["url"]
    try:
        dl_hdr = {**hdr, "Accept": "application/octet-stream"}
        r = requests.get(download_url, headers=dl_hdr, timeout=120, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("Error descargando snapshot: %s", e)
        return False

    raw = r.content
    try:
        decompressed = gzip.decompress(raw)
    except Exception:
        decompressed = raw

    try:
        data = json.loads(decompressed)
        if not isinstance(data, dict) or not data.get("generado_en"):
            log.warning("Snapshot descargado no tiene generado_en")
            return False
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("Snapshot no es JSON válido: %s", e)
        return False

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_bytes(decompressed)
    log.info(
        "Snapshot restaurado: %s (generado_en=%s, %.1f KB)",
        DATA_FILE, data["generado_en"], len(decompressed) / 1024,
    )
    return True
