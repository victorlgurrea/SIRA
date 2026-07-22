"""Persistencia (SQLite)."""

from sira.infrastructure.persistence.sqlite import (
    add_subscription,
    count_subscriptions,
    get_historial_municipio,
    historial_existe,
    ids_ya_notificados,
    init_db,
    insert_historial_municipio,
    list_subscriptions,
    marcar_notificado,
    migrar_desde_json,
    remove_subscription,
    save_push_state,
    save_subscriptions,
)

__all__ = [
    "add_subscription",
    "count_subscriptions",
    "get_historial_municipio",
    "historial_existe",
    "ids_ya_notificados",
    "init_db",
    "insert_historial_municipio",
    "list_subscriptions",
    "marcar_notificado",
    "migrar_desde_json",
    "remove_subscription",
    "save_push_state",
    "save_subscriptions",
]
