"""Scheduler: ingesta + alertas."""
from __future__ import annotations

import argparse
import logging
import time

from config import SCHEDULER_MIN
from ingesta import ejecutar_ingesta
from notificaciones import evaluar_alertas

log = logging.getLogger(__name__)


def ciclo() -> None:
    ejecutar_ingesta()
    evaluar_alertas()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--una-vez", action="store_true")
    p.add_argument("--intervalo", type=int, default=SCHEDULER_MIN)
    args = p.parse_args()

    if args.una_vez:
        ciclo()
    else:
        log.info("Cada %d min", args.intervalo)
        while True:
            try:
                ciclo()
            except (OSError, ValueError) as exc:
                log.exception("Error en ciclo: %s", exc)
            time.sleep(args.intervalo * 60)
