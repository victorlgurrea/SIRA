"""Datos geográficos y capas cartográficas."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Raíz del repositorio (…/SIRA); los JSON viven en data/geo/
REPO_ROOT = Path(__file__).resolve().parents[4]
_PYTHON_DIR = REPO_ROOT / "python"


def run_build_script(module: str) -> None:
    """Ejecuta scripts/build/{module}.py (función build)."""
    path = REPO_ROOT / "scripts" / "build" / f"{module}.py"
    py = str(_PYTHON_DIR)
    if py not in sys.path:
        sys.path.insert(0, py)
    spec = importlib.util.spec_from_file_location(f"sira_build_{module}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar script de build: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.build()
