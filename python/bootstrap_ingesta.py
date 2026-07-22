"""Launcher bootstrap Render — ver sira.services.ingesta.runner."""
from sira.services.ingesta.runner import main, run_bootstrap

__all__ = ["main", "run_bootstrap"]

if __name__ == "__main__":
    raise SystemExit(main(["--bootstrap"]))
