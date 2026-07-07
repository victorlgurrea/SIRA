"""Arranque tolerante para producción: intenta una ingesta inicial sin romper el deploy."""
from __future__ import annotations

import logging
import sys

from ingesta import ejecutar_ingesta


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        ejecutar_ingesta()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Bootstrap ingesta omitida: %s", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
