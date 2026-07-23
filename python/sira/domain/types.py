"""Tipos estructurados de dominio (payloads de riesgo y sismos)."""
from __future__ import annotations

from typing import NotRequired, TypedDict


class EjeRiesgo(TypedDict):
    id: str
    nombre: str
    pct: int
    peso_pct: int
    contrib: int
    motivo: NotRequired[str]


class RiesgoLocal(TypedDict):
    indice: int
    nivel: str
    ejes: list[EjeRiesgo]
    concurrencia: bool
    horas_meteo: int
    texto: str
    riesgo_meteo: NotRequired[dict]


class SismoEnriquecido(TypedDict, total=False):
    id: str
    magnitud: float
    lugar: str
    timestamp: str
    lat: float
    lon: float
    profundidad: float
    dist_local_km: float
    en_mar: bool
    alerta_tsunami: bool
    radio_tsunami_km: float
    radio_perceptible_km: float
    score_local: int
    nivel_local: str
    perceptible_local: bool
    area_desc: str
