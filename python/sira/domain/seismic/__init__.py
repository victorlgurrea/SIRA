"""Dominio sísmico: distancias, scores y geometría de alertas."""

from sira.domain.seismic.sismos import (
    alerta_local,
    alerta_tsunami_local,
    circle_disk_polygon,
    circle_perimeter,
    distancia_km,
    enriquecer_local,
    epicentro_en_mar,
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
