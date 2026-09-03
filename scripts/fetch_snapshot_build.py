"""Descarga el snapshot latest-data durante el build en Render (disco vacío tras deploy)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sira.infrastructure.persistence.snapshot import download_snapshot  # noqa: E402


def main() -> int:
    ok = download_snapshot()
    if ok:
        print("Snapshot listo para el deploy")
        return 0
    # No tumbar el deploy de Render: la API puede arrancar y reingestar.
    print("AVISO: build sin snapshot latest-data (la API arrancará igual)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
