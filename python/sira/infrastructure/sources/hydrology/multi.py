"""Aforos multi-cuenca — agrega datos de CHJ, Ebro y Segura."""
from __future__ import annotations

import logging
from typing import Callable

from sira.infrastructure.sources.hydrology.chj import descargar_aforos as descargar_aforos_chj
from sira.infrastructure.sources.hydrology.ebro import descargar_aforos as descargar_aforos_ebro
from sira.infrastructure.sources.hydrology.segura import descargar_aforos as descargar_aforos_segura

log = logging.getLogger(__name__)

AforosFetcher = Callable[[list[dict] | None], list[dict]]

_CUENCAS: dict[str, tuple[str, AforosFetcher]] = {
    "CHJ": ("saih_chj", descargar_aforos_chj),
    "CHE": ("saih_che", descargar_aforos_ebro),
    "CHS": ("saih_chs", descargar_aforos_segura),
}


def registrar_cuenca(nombre: str, clave_estado: str, fetcher: AforosFetcher) -> None:
    _CUENCAS[nombre] = (clave_estado, fetcher)


def descargar_aforos(alertas_meteo: list[dict] | None = None) -> list[dict]:
    """Obtiene aforos de todas las cuencas registradas."""
    resultado: list[dict] = []
    for nombre, (_clave, fetcher) in _CUENCAS.items():
        try:
            aforos = fetcher(alertas_meteo)
            for af in aforos:
                af.setdefault("cuenca", nombre)
            resultado.extend(aforos)
        except Exception:
            log.warning("Error obteniendo aforos de %s", nombre, exc_info=True)
    return resultado


def descargar_aforos_con_estado(
    alertas_meteo: list[dict] | None,
    estado_fuente: Callable,
) -> tuple[list[dict], dict[str, dict]]:
    """Igual que descargar_aforos pero registra estado por cuenca (ingesta)."""
    resultado: list[dict] = []
    estados: dict[str, dict] = {}
    etiquetas = {"CHJ": "SAIH CHJ", "CHE": "SAIH Ebro", "CHS": "SAIH Segura"}
    for nombre, (clave, fetcher) in _CUENCAS.items():
        rows, estados[clave] = estado_fuente(
            etiquetas.get(nombre, nombre), fetcher, alertas_meteo, default=[],
        )
        for af in rows:
            af.setdefault("cuenca", nombre)
        resultado.extend(rows)
    return resultado, estados
