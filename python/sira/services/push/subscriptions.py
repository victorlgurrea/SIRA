"""Suscripciones Web Push y helpers VAPID."""
from __future__ import annotations

from pywebpush import Vapid

from sira.config.settings import (
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
    VAPID_SUBJECT,
)
from sira.infrastructure.persistence.sqlite import (
    list_subscriptions as db_list_subscriptions,
    remove_subscription as db_remove_subscription,
    save_subscriptions as db_save_subscriptions,
)

_vapid_signer: Vapid | None = None


def _subscription_info(sub: dict) -> dict:
    return {"endpoint": sub["endpoint"], "keys": sub["keys"]}


def _get_vapid_signer() -> Vapid:
    global _vapid_signer
    if _vapid_signer is None:
        _vapid_signer = Vapid.from_pem(VAPID_PRIVATE_KEY.encode("utf-8"))
    return _vapid_signer


def vapid_enabled() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_SUBJECT)


def vapid_public_key() -> str:
    return VAPID_PUBLIC_KEY


def _normalize_sub(sub: dict) -> dict:
    """Normaliza suscripciones legacy (solo sismo, sin municipio)."""
    out = dict(sub)
    alertas = out.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        out["alertas"] = ["sismo", "meteo", "incendio", "tsunami"]
    else:
        vals = {str(a).lower() for a in alertas}
        if vals <= {"sismo"}:
            out["alertas"] = ["sismo", "meteo", "incendio", "tsunami"]
        elif vals <= {"sismo", "meteo"}:
            out["alertas"] = ["sismo", "meteo", "incendio", "tsunami"]
    if out.get("municipio_id"):
        out["municipio_id"] = str(out["municipio_id"]).zfill(5)
    if out.get("provincia_id"):
        out["provincia_id"] = str(out["provincia_id"]).zfill(2)
    return out


def list_subscriptions() -> list[dict]:
    raw = db_list_subscriptions()
    subs = [_normalize_sub(s) for s in raw]
    if any(_needs_normalize(s) for s in raw):
        db_save_subscriptions(subs)
    return subs


def _needs_normalize(sub: dict) -> bool:
    alertas = sub.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        return True
    vals = {str(a).lower() for a in alertas}
    return vals <= {"sismo"} or vals <= {"sismo", "meteo"}


def save_subscriptions(subs: list[dict]) -> None:
    db_save_subscriptions([_normalize_sub(s) for s in subs])


def add_subscription(sub: dict) -> int:
    sub = _normalize_sub(sub)
    endpoint = sub.get("endpoint")
    if not endpoint:
        return len(list_subscriptions())
    subs = list_subscriptions()
    for i, current in enumerate(subs):
        if current.get("endpoint") == endpoint:
            subs[i] = sub
            save_subscriptions(subs)
            return len(subs)
    subs.append(sub)
    save_subscriptions(subs)
    return len(subs)


def remove_subscription(endpoint: str) -> int:
    return db_remove_subscription(endpoint)
