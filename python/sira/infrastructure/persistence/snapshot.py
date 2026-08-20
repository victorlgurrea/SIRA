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
_DIRECT_DOWNLOAD_URL = f"https://github.com/{_OWNER_REPO}/releases/download/{_TAG}/{_ASSET_NAME}"
_TIMEOUT = 60


def _headers(token: str | None = None) -> dict[str, str]:
    tok = token or os.getenv("GITHUB_TOKEN", "")
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SIRA-dashboard-snapshot/1.0",
    }
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

def _gunzip_until_json(raw: bytes) -> tuple[bytes, dict] | tuple[None, None]:
    """Descomprime 1–N capas gzip hasta obtener JSON con generado_en."""
    blob = raw
    for _ in range(4):
        try:
            data = json.loads(blob)
            if isinstance(data, dict) and data.get("generado_en"):
                if isinstance(blob, str):
                    blob = blob.encode("utf-8")
                elif not isinstance(blob, (bytes, bytearray)):
                    blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
                return bytes(blob), data
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError, ValueError):
            pass
        if len(blob) >= 2 and blob[:2] == b"\x1f\x8b":
            try:
                blob = gzip.decompress(blob)
                continue
            except Exception:  # noqa: BLE001
                return None, None
        return None, None
    return None, None


def _save_snapshot_bytes(raw: bytes) -> bool:
    decompressed, data = _gunzip_until_json(raw)
    if not decompressed or not data:
        log.warning("Snapshot no es JSON válido tras descomprimir")
        return False
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_bytes(decompressed)
    log.info(
        "Snapshot restaurado: %s (generado_en=%s, %.1f KB)",
        DATA_FILE, data["generado_en"], len(decompressed) / 1024,
    )
    return True


def download_snapshot(token: str | None = None) -> bool:
    """Descarga el snapshot más reciente a DATA_FILE. Retorna True si OK.

    En repos públicos funciona sin token (descarga directa del asset).
    Tolera 1 o 2 capas gzip (regresión del workflow con Accept-Encoding).
    Si la API de GitHub falla (rate limit en Render), usa URL directa del release.
    """
    hdr = _headers(token)
    download_url: str | None = None

    url_rel = f"{_API}/repos/{_OWNER_REPO}/releases/tags/{_TAG}"
    try:
        r = requests.get(url_rel, headers=hdr, timeout=_TIMEOUT)
        if r.status_code == 404:
            log.info("No existe release %s; probando URL directa", _TAG)
        elif r.ok:
            assets = r.json().get("assets", [])
            asset = next((a for a in assets if a["name"] == _ASSET_NAME), None)
            if asset:
                download_url = asset.get("browser_download_url") or asset["url"]
            else:
                log.info("Release sin asset %s; probando URL directa", _ASSET_NAME)
        else:
            log.warning("Error comprobando release: %s; probando URL directa", r.status_code)
    except requests.RequestException as e:
        log.warning("No se pudo comprobar release: %s; probando URL directa", e)

    for url in (download_url, _DIRECT_DOWNLOAD_URL):
        if not url:
            continue
        try:
            dl_hdr = {**hdr, "Accept": "application/octet-stream"}
            r = requests.get(url, headers=dl_hdr, timeout=120, allow_redirects=True)
            r.raise_for_status()
            if _save_snapshot_bytes(r.content):
                return True
        except requests.RequestException as e:
            log.warning("Error descargando snapshot (%s): %s", url[:60], e)

    return False
