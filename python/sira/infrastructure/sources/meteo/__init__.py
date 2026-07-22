"""Fuentes meteorológicas (AEMET, Open-Meteo, térmico)."""

from sira.infrastructure.sources.meteo.aemet_alerts import deduplicar_alertas
from sira.infrastructure.sources.meteo.live import meteo_localidad
from sira.infrastructure.sources.meteo.parse import VACIO_METEO, pack_meteo, parse_aemet
from sira.infrastructure.sources.meteo.termico import construir_termico_ccaa

__all__ = [
    "VACIO_METEO",
    "construir_termico_ccaa",
    "deduplicar_alertas",
    "meteo_localidad",
    "pack_meteo",
    "parse_aemet",
]
