"""Migra push_subscriptions.json, push_estado.json y alertas_estado.json a SQLite."""
from __future__ import annotations

import logging
import sys

from db import migrar_desde_json

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    stats = migrar_desde_json()
    print("Migración completada:", stats)
    if not any(stats.values()):
        print("No había datos JSON que migrar (o SQLite ya contenía datos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
