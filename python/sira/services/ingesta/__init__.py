"""Pipeline de ingesta hacia dashboard_data.json."""

from sira.services.ingesta.orchestrator import ejecutar_ingesta
from sira.services.ingesta.runner import (
    main as cli_main,
    run_bootstrap,
    run_ciclo,
    run_ingesta_once,
    run_scheduler,
)

__all__ = [
    "cli_main",
    "ejecutar_ingesta",
    "run_bootstrap",
    "run_ciclo",
    "run_ingesta_once",
    "run_scheduler",
]
