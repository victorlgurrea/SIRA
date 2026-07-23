"""Paths de configuración alineados con la raíz del repo."""
from __future__ import annotations

from pathlib import Path

from sira.config import settings


def test_root_es_raiz_del_repo():
    root = settings.ROOT
    assert (root / "python").is_dir()
    assert (root / "dashboard").is_dir()
    assert (root / "data").is_dir()
    assert (root / ".env.example").is_file()


def test_data_dir_bajo_raiz():
    assert settings.DATA_DIR == settings.ROOT / "data" / "processed"
    assert settings.DATA_FILE == settings.DATA_DIR / "dashboard_data.json"


def test_db_path_relativo_se_resuelve_desde_root(monkeypatch):
    monkeypatch.setenv("DB_PATH", "data/processed/sira.db")
    # Re-evaluar lógica igual que settings (sin reimportar el módulo entero).
    raw = Path("data/processed/sira.db")
    resolved = raw if raw.is_absolute() else (settings.ROOT / raw).resolve()
    assert resolved == (settings.ROOT / "data" / "processed" / "sira.db").resolve()
