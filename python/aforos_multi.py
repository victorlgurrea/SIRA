"""Aforos multi-cuenca — agrega datos de CHJ, Ebro y Segura."""
from __future__ import annotations

import logging
from typing import Callable

from aforos import descargar_aforos as descargar_aforos_chj
from aforos_ebro import descargar_aforos as descargar_aforos_ebro
from aforos_segura import descargar_aforos as descargar_aforos_segura

log = logging.getLogger(__name__)

AforosFetcher = Callable[[list[dict] | None], list[dict]]

_CUENCAS: dict[str, AforosFetcher] = {
    "CHJ": descargar_aforos_chj,
    "CHE": descargar_aforos_ebro,
    "CHS": descargar_aforos_segura,
}


def registrar_cuenca(nombre: str, fetcher: AforosFetcher) -> None:
    _CUENCAS[nombre] = fetcher


def descargar_aforos(alertas_meteo: list[dict] | None = None) -> list[dict]:
    """Obtiene aforos de todas las cuencas registradas."""
    resultado: list[dict] = []
    for nombre, fetcher in _CUENCAS.items():
        try:
            aforos = fetcher(alertas_meteo)
            for af in aforos:
                af.setdefault("cuenca", nombre)
            resultado.extend(aforos)
        except Exception:
            log.warning("Error obteniendo aforos de %s", nombre, exc_info=True)
    return resultado
