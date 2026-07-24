"""Tests de persistencia SQLite."""
from __future__ import annotations

import pytest


def test_push_subscriptions_roundtrip(db_tmp):
    sub = {
        "endpoint": "https://example.com/push/1",
        "keys": {"p256dh": "a", "auth": "b"},
        "municipio_id": "46250",
        "alertas": ["sismo"],
    }
    assert db_tmp.add_subscription(sub) == 1
    subs = db_tmp.list_subscriptions()
    assert len(subs) == 1
    assert subs[0]["endpoint"] == sub["endpoint"]
    assert db_tmp.remove_subscription(sub["endpoint"]) == 0


def test_alertas_notificados(db_tmp):
    db_tmp.marcar_notificado(["a", "b"])
    assert db_tmp.ids_ya_notificados() == ["a", "b"]
    db_tmp.marcar_notificado(["c"])
    assert db_tmp.ids_ya_notificados() == ["c"]
