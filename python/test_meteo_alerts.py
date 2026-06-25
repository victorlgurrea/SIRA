"""Alertas meteo de prueba (overlay lógico para dashboard/push)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from aemet_alerts import alerta_firma
from config import TEST_METEO_ALERTS_FILE
from core import read_json_file


def _write(payload: dict) -> None:
    TEST_METEO_ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEST_METEO_ALERTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_test_alert(alert: dict, ttl_min: int = 30) -> dict:
    data = read_json_file(TEST_METEO_ALERTS_FILE)
    existing = data.get("alerts", []) if isinstance(data.get("alerts"), list) else []
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=max(1, ttl_min))).isoformat()
    entry = {**alert, "expires": expires_at, "is_test": True}
    firma_new = alerta_firma(entry)
    out = [
        a for a in existing
        if alerta_firma(a) != firma_new and str(a.get("id")) != str(entry.get("id"))
    ]
    out.insert(0, entry)
    _write({"alerts": out})
    return entry


def read_active_test_alerts() -> list[dict]:
    data = read_json_file(TEST_METEO_ALERTS_FILE)
    alerts = data.get("alerts", []) if isinstance(data.get("alerts"), list) else []
    now = datetime.now(timezone.utc)
    active: list[dict] = []
    for a in alerts:
        try:
            exp = datetime.fromisoformat(str(a.get("expires", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if exp > now:
            active.append(a)
    if len(active) != len(alerts):
        _write({"alerts": active})
    return active
