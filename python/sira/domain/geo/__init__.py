"""Utilidades geográficas de dominio (distancias, mar/tierra)."""

from sira.domain.geo.distance import circle_disk_polygon, circle_perimeter, distancia_km
from sira.domain.geo.mar import epicentro_en_mar, usgs_tsunami_flag

__all__ = [
    "circle_disk_polygon",
    "circle_perimeter",
    "distancia_km",
    "epicentro_en_mar",
    "usgs_tsunami_flag",
]
