"""Launcher ingesta — ver sira.services.ingesta.runner."""
from sira.services.ingesta.orchestrator import (
    descargar_meteo,
    descargar_oceanografia,
    descargar_sismos,
    ejecutar_ingesta,
)
from sira.services.ingesta.runner import main, run_ingesta_once

__all__ = [
    "descargar_meteo",
    "descargar_oceanografia",
    "descargar_sismos",
    "ejecutar_ingesta",
    "main",
    "run_ingesta_once",
]

if __name__ == "__main__":
    raise SystemExit(main())
