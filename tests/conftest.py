"""Configuración pytest — añade python/ al path."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for subdir in ("python", "dashboard"):
    p = str(ROOT / subdir)
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture()
def db_tmp(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    import sira.config.settings as config
    import sira.infrastructure.persistence.sqlite as db_mod

    monkeypatch.setattr(config, "DB_PATH", db_file)
    importlib.reload(db_mod)
    db_mod.init_db()
    return db_mod
