"""Zonas de aviso AEMET Meteoalerta para el mapa (polígonos oficiales)."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from geo_es import ccaa_de_provincia, provincias

ROOT = Path(__file__).resolve().parent.parent
ZONAS_FILE = ROOT / "data" / "geo" / "aemet_zonas_aviso.json"

# Códigos CCAA INE (2 letras) → código Meteoalerta AEMET (numérico)
CCAA_INE_A_AEMET: dict[str, str] = {
    "AN": "61",
    "AR": "62",
    "AS": "63",
    "IB": "64",
    "CN": "65",
    "CB": "66",
    "CL": "67",
    "CM": "68",
    "CT": "69",
    "EX": "70",
    "GA": "71",
    "MD": "72",
    "MC": "73",
    "NC": "74",
    "PV": "75",
    "RI": "76",
    "VC": "77",
    "CE": "78",
    "ML": "79",
}

NIVEL_COLOR: dict[str, str] = {
    "amarillo": "rgba(255, 235, 59, 0.62)",
    "naranja": "rgba(255, 152, 0, 0.68)",
    "rojo": "rgba(244, 67, 54, 0.72)",
}
NIVEL_ORDEN = {"amarillo": 1, "naranja": 2, "rojo": 3}
SIN_AVISO_FILL = "rgba(180, 186, 195, 0.18)"
SIN_AVISO_LINE = "rgba(90, 98, 110, 0.55)"
AVISO_LINE = "rgba(55, 65, 81, 0.75)"


def _norm(text: str | None) -> str:
    if not text:
        return ""
    txt = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    txt = re.sub(r"[^a-z0-9]+", " ", txt.lower())
    return re.sub(r"\s+", " ", txt).strip()


def _provincia_tokens(provincia_id: str | None) -> set[str]:
    if not provincia_id:
        return set()
    pid = str(provincia_id).zfill(2)
    prov = next((p for p in provincias() if p["id"] == pid), None)
    if not prov:
        return set()
    tokens: set[str] = set()
    nombre = str(prov.get("nombre") or "")
    for parte in nombre.split("/"):
        t = _norm(parte)
        if t:
            tokens.add(t)
    if "," in nombre:
        a, b = [x.strip() for x in nombre.split(",", 1)]
        tokens.add(_norm(f"{b} {a}"))
    tokens.add(_norm(nombre))
    return {t for t in tokens if t}


def _zona_coincide_provincia(zona: dict, provincia_id: str | None) -> bool:
    tokens = _provincia_tokens(provincia_id)
    if not tokens:
        return True
    candidatos = {_norm(zona.get("provincia")), _norm(zona.get("nombre"))}
    for cand in candidatos:
        if not cand:
            continue
        for token in tokens:
            if token in cand or cand in token:
                return True
            for frag in cand.split():
                if frag and (frag in token or token in frag):
                    return True
    return False


@lru_cache(maxsize=1)
def _zonas_raw() -> list[dict]:
    if not ZONAS_FILE.is_file():
        return []
    try:
        data = json.loads(ZONAS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(data.get("features") or [])


def zonas_ccaa(provincia_id: str | None) -> list[dict]:
    """Zonas Meteoalerta visibles para la CCAA de la provincia seleccionada."""
    zonas = _zonas_raw()
    if not provincia_id:
        return zonas
    ccaa_ine = ccaa_de_provincia(str(provincia_id).zfill(2))
    ccaa_aemet = CCAA_INE_A_AEMET.get(ccaa_ine or "")
    if not ccaa_aemet:
        return [z for z in zonas if _zona_coincide_provincia(z, provincia_id)]
    return [z for z in zonas if str(z.get("ccaa_id") or "") == ccaa_aemet]


def _aviso_coincide_zona(aviso: dict, zona: dict) -> bool:
    cod_zona = str(aviso.get("zona") or "").strip()
    if cod_zona and cod_zona == str(zona.get("id") or "").strip():
        return True
    area = _norm(aviso.get("area_desc"))
    nombre = _norm(zona.get("nombre"))
    if area and nombre and (area == nombre or area in nombre or nombre in area):
        return True
    return False


def aviso_maximo_zona(zona: dict, alertas: list[dict]) -> dict | None:
    """Aviso de mayor nivel activo para una zona Meteoalerta."""
    mejor: dict | None = None
    mejor_rank = 0
    for aviso in alertas:
        if not isinstance(aviso, dict):
            continue
        if not _aviso_coincide_zona(aviso, zona):
            continue
        nivel = str(aviso.get("level") or "").lower()
        rank = NIVEL_ORDEN.get(nivel, 0)
        if rank > mejor_rank:
            mejor = aviso
            mejor_rank = rank
    return mejor


def color_nivel(nivel: str | None) -> tuple[str, str]:
    """(fill, line) para una zona según nivel de aviso."""
    key = str(nivel or "").lower()
    if key in NIVEL_COLOR:
        return NIVEL_COLOR[key], AVISO_LINE
    return SIN_AVISO_FILL, SIN_AVISO_LINE
