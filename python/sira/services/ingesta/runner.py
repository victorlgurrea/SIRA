"""CLI de ingesta: ejecución única, scheduler y bootstrap de deploy."""
from __future__ import annotations

import argparse
import logging
import sys
import time

from sira.config.settings import SCHEDULER_MIN
from sira.services.ingesta.orchestrator import ejecutar_ingesta
from sira.services.notifications.channels import evaluar_alertas

log = logging.getLogger(__name__)


def run_ingesta_once() -> None:
    """Ejecuta una ingesta completa."""
    ejecutar_ingesta()


def run_ciclo() -> None:
    """Ingesta + evaluación de alertas email/Telegram."""
    ejecutar_ingesta()
    evaluar_alertas()


def run_scheduler(*, once: bool = False, interval_min: int | None = None) -> None:
    """Bucle ingesta + alertas."""
    interval = max(1, int(interval_min if interval_min is not None else SCHEDULER_MIN))
    if once:
        run_ciclo()
        return
    log.info("Scheduler SIRA: cada %d min", interval)
    while True:
        try:
            run_ciclo()
        except (OSError, ValueError) as exc:
            log.exception("Error en ciclo: %s", exc)
        time.sleep(interval * 60)


def run_bootstrap() -> int:
    """Ingesta inicial tolerante a fallos (deploy Render)."""
    try:
        ejecutar_ingesta()
    except Exception as exc:  # noqa: BLE001
        log.warning("Bootstrap ingesta omitida: %s", exc)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sira.services.ingesta",
        description="Ingesta SIRA: una vez, scheduler o bootstrap de deploy.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--scheduler",
        action="store_true",
        help="Bucle ingesta + alertas email/Telegram",
    )
    mode.add_argument(
        "--bootstrap",
        action="store_true",
        help="Ingesta inicial tolerante (no falla el deploy)",
    )
    parser.add_argument(
        "--una-vez",
        action="store_true",
        help="Con --scheduler: un solo ciclo y salir",
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=None,
        metavar="MIN",
        help=f"Con --scheduler: intervalo en minutos (default {SCHEDULER_MIN})",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if args.bootstrap:
        return run_bootstrap()
    if args.scheduler:
        run_scheduler(once=args.una_vez, interval_min=args.intervalo)
        return 0
    run_ingesta_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
