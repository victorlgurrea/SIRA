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
# Fenómenos que pueden colorear polígonos marítimos (shapefile costeras).
FENOMENOS_ZONA_COSTERA = frozenset({"CO", "RI", "GA"})
# En tierra no pintar avisos exclusivos de mar (oleaje, rissaga…).
FENOMENOS_EXCLUIDOS_TIERRA = frozenset({"CO", "RI"})
SIN_AVISO_FILL = "rgba(180, 186, 195, 0.18)"
# Opaco: tapa el color de avisos terrestres que se cuela bajo polígonos marítimos.
SIN_AVISO_COSTA_FILL = "rgba(238, 241, 245, 0.98)"
SIN_AVISO_LINE = "rgba(90, 98, 110, 0.55)"
SIN_AVISO_COSTA_LINE = "rgba(120, 140, 160, 0.55)"
AVISO_LINE = "rgba(55, 65, 81, 0.75)"


def es_zona_costera(zona: dict) -> bool:
    if zona.get("costera"):
        return True
    return str(zona.get("id") or "").strip().upper().endswith("C")


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


def zonas_ccaa_pintado(provincia_id: str | None) -> list[dict]:
    """Zonas ordenadas: tierra primero, mar encima (enmascara sangrado de avisos terrestres)."""
    return sorted(zonas_ccaa(provincia_id), key=es_zona_costera)


def _area_zona_key(text: str | None) -> str:
    """Normaliza areaDesc CAP: «Litoral sur de Valencia-Valencia/Valencia» → zona base."""
    area = _norm(text)
    if "-" in area:
        area = area.split("-", 1)[0].strip()
    return area


def _aviso_coincide_zona(aviso: dict, zona: dict) -> bool:
    cod_zona = str(aviso.get("zona") or "").strip()
    zona_id = str(zona.get("id") or "").strip()
    if cod_zona and zona_id and cod_zona == zona_id:
        return True
    area = _area_zona_key(aviso.get("area_desc"))
    nombre = _norm(zona.get("nombre"))
    if not area or not nombre:
        return False
    if es_zona_costera(zona):
        # Polígono marítimo: solo nombre exacto (no heredar avisos de zona litoral terrestre).
        return area == nombre
    if nombre.startswith("costa "):
        return area == nombre
    return area == nombre or area in nombre or nombre in area


def fenomeno_aplica_zona(fenomeno: str | None, zona: dict) -> bool:
    """True si el fenómeno CAP puede colorear este polígono (tierra vs mar)."""
    fen = str(fenomeno or "").upper().strip()
    if not fen:
        return False
    if es_zona_costera(zona):
        return fen in FENOMENOS_ZONA_COSTERA
    return fen not in FENOMENOS_EXCLUIDOS_TIERRA


def aviso_maximo_zona(zona: dict, alertas: list[dict]) -> dict | None:
    """Aviso de mayor nivel activo para una zona Meteoalerta."""
    mejor: dict | None = None
    mejor_rank = 0
    for aviso in alertas:
        if not isinstance(aviso, dict):
            continue
        if not _aviso_coincide_zona(aviso, zona):
            continue
        if not fenomeno_aplica_zona(aviso.get("fenomeno"), zona):
            continue
        nivel = str(aviso.get("level") or "").lower()
        rank = NIVEL_ORDEN.get(nivel, 0)
        if rank > mejor_rank:
            mejor = aviso
            mejor_rank = rank
    return mejor


def color_nivel(nivel: str | None, *, costera: bool = False) -> tuple[str, str]:
    """(fill, line) para una zona según nivel de aviso."""
    key = str(nivel or "").lower()
    if key in NIVEL_COLOR:
        return NIVEL_COLOR[key], AVISO_LINE
    if costera:
        return SIN_AVISO_COSTA_FILL, SIN_AVISO_COSTA_LINE
    return SIN_AVISO_FILL, SIN_AVISO_LINE
