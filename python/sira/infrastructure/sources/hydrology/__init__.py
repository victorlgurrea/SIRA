"""Fuentes hidrológicas multi-cuenca (SAIH) y embalses."""

from sira.infrastructure.sources.hydrology.chj import (
    aforos_para_mapa,
    descargar_aforos as descargar_aforos_chj,
    resumen_aforos,
)
from sira.infrastructure.sources.hydrology.ebro import descargar_aforos as descargar_aforos_ebro
from sira.infrastructure.sources.hydrology.multi import descargar_aforos as descargar_aforos_multi
from sira.infrastructure.sources.hydrology.reservoirs import (
    descargar_embalses,
    embalses_para_mapa,
    resumen_embalses,
)
from sira.infrastructure.sources.hydrology.segura import descargar_aforos as descargar_aforos_segura

__all__ = [
    "aforos_para_mapa",
    "descargar_aforos_chj",
    "descargar_aforos_ebro",
    "descargar_aforos_multi",
    "descargar_aforos_segura",
    "descargar_embalses",
    "embalses_para_mapa",
    "resumen_aforos",
    "resumen_embalses",
]
