"""Launcher scheduler — ver sira.services.ingesta.runner."""
from sira.services.ingesta.runner import main, run_ciclo, run_scheduler

__all__ = ["main", "run_ciclo", "run_scheduler"]

if __name__ == "__main__":
    import sys

    raise SystemExit(main(["--scheduler", *sys.argv[1:]]))
