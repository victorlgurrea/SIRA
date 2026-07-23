"""Dominio sísmico: scores y geometría de alertas."""

from sira.domain.geo import circle_disk_polygon, circle_perimeter, distancia_km, epicentro_en_mar
from sira.domain.seismic.sismos import (
    alerta_local,
    alerta_tsunami_local,
    enriquecer_local,
    radio_tsunami_km,
    riesgo_tsunami,
    score_sismo,
)

__all__ = [
    "alerta_local",
    "alerta_tsunami_local",
    "circle_disk_polygon",
    "circle_perimeter",
    "distancia_km",
    "enriquecer_local",
    "epicentro_en_mar",
    "radio_tsunami_km",
    "riesgo_tsunami",
    "score_sismo",
]
