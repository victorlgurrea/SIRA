"""Web Push (VAPID) para notificaciones en navegador/PWA."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pywebpush import WebPushException, Vapid, webpush

from config import (
    PUSH_STATE_FILE,
    PUSH_SUBSCRIPTIONS_FILE,
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
    VAPID_SUBJECT,
    ZONA,
)
from core import read_dashboard, read_json_file
from geo_es import coords_municipio
from sismos import distancia_km, es_perceptible

log = logging.getLogger(__name__)

_vapid_signer: Vapid | None = None


def _subscription_info(sub: dict) -> dict:
    return {"endpoint": sub["endpoint"], "keys": sub["keys"]}


def _get_vapid_signer() -> Vapid:
    global _vapid_signer
    if _vapid_signer is None:
        _vapid_signer = Vapid.from_pem(VAPID_PRIVATE_KEY.encode("utf-8"))
    return _vapid_signer


def _write_json(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def vapid_enabled() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_SUBJECT)


def vapid_public_key() -> str:
    return VAPID_PUBLIC_KEY


def list_subscriptions() -> list[dict]:
    data = read_json_file(PUSH_SUBSCRIPTIONS_FILE)
    subs = data.get("subscriptions", [])
    return [s for s in subs if isinstance(s, dict) and s.get("endpoint")]


def save_subscriptions(subs: list[dict]) -> None:
    _write_json(PUSH_SUBSCRIPTIONS_FILE, {"subscriptions": subs})


def add_subscription(sub: dict) -> int:
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
    subs = [s for s in list_subscriptions() if s.get("endpoint") != endpoint]
    save_subscriptions(subs)
    return len(subs)


def _state_ids() -> list[str]:
    return read_json_file(PUSH_STATE_FILE).get("ids_push", [])


def _save_state_ids(ids: list[str]) -> None:
    _write_json(PUSH_STATE_FILE, {"ids_push": ids, "updated": datetime.now(timezone.utc).isoformat()})


def _alertables(sismos: list[dict]) -> list[dict]:
    return [s for s in sismos if s.get("score_total", 0) >= ZONA["umbral_score_alerta"]]


def _build_payload(s: dict, dashboard_url: str) -> dict:
    mag = s.get("magnitud", "—")
    lugar = s.get("lugar", "—")
    score = s.get("score_total", "—")
    nivel = s.get("nivel_alerta", "—")
    return {
        "title": f"SIRA · Sismo {nivel}",
        "body": f"M{mag} · score {score} · {lugar}",
        "icon": "/assets/logo_sira_3.png?v=8",
        "badge": "/assets/logo_sira_3.png?v=8",
        "url": dashboard_url,
        "tag": f"sira-{s.get('id')}",
        "renotify": False,
    }


def _sub_prefers_sismo(sub: dict) -> bool:
    alertas = sub.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        return True
    vals = {str(a).lower() for a in alertas}
    return "sismo" in vals or "all" in vals or "todas" in vals


def _sismo_match_subscription(sismo: dict, sub: dict) -> bool:
    if not _sub_prefers_sismo(sub):
        return False
    municipio_id = sub.get("municipio_id")
    if not municipio_id:
        return True
    try:
        lat, lon = coords_municipio(str(municipio_id))
        dist = distancia_km(lat, lon, float(sismo["lat"]), float(sismo["lon"]))
        return es_perceptible(float(sismo.get("magnitud", 0)), float(sismo.get("profundidad") or 0), dist)
    except (TypeError, ValueError, KeyError):
        return False


def send_push(subscription: dict, payload: dict) -> bool:
    if not vapid_enabled():
        return False
    try:
        webpush(
            subscription_info=_subscription_info(subscription),
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_get_vapid_signer(),
            vapid_claims={"sub": VAPID_SUBJECT},
            ttl=3600,
        )
        return True
    except WebPushException as exc:
        log.warning("WebPush fallo: %s", exc)
        return False
    except (ValueError, TypeError, KeyError) as exc:
        log.warning("Push inválido: %s", exc)
        return False


def notify_new_alerts(dashboard_url: str) -> int:
    if not vapid_enabled():
        return 0
    data = read_dashboard()
    crit = _alertables(data.get("sismos", []))
    if not crit:
        _save_state_ids([])
        return 0

    ids = sorted({str(s.get("id")) for s in crit if s.get("id")})
    prev = _state_ids()
    nuevos = [s for s in crit if str(s.get("id")) not in prev]
    if not nuevos:
        return 0

    subs = list_subscriptions()
    if not subs:
        _save_state_ids(ids)
        return 0

    sent = 0
    invalid_endpoints: set[str] = set()
    for s in nuevos:
        payload = _build_payload(s, dashboard_url)
        for sub in subs:
            if not _sismo_match_subscription(s, sub):
                continue
            ok = send_push(sub, payload)
            if ok:
                sent += 1
            else:
                invalid_endpoints.add(sub.get("endpoint", ""))

    if invalid_endpoints:
        subs = [s for s in subs if s.get("endpoint") not in invalid_endpoints]
        save_subscriptions(subs)

    _save_state_ids(ids)
    return sent


def send_test_push(
    dashboard_url: str,
    *,
    title: str | None = None,
    body: str | None = None,
    url: str | None = None,
    tag: str = "sira-test-valencia",
    renotify: bool = True,
    solo_municipio_id: str | None = None,
) -> dict:
    """Envía una notificación de prueba a suscripciones activas (Postman / admin)."""
    if not vapid_enabled():
        return {"ok": False, "error": "Web Push no configurado", "enviados": 0, "suscripciones": 0}

    subs = list_subscriptions()
    if solo_municipio_id:
        subs = [s for s in subs if str(s.get("municipio_id") or "") == str(solo_municipio_id)]
    if not subs:
        return {"ok": False, "error": "No hay suscripciones activas", "enviados": 0, "suscripciones": 0}

    payload = {
        "title": title or "SIRA · Sismo ALTO",
        "body": body or "M4.2 · score 68 · 12 km al E de Valencia (prueba)",
        "icon": "/assets/logo_sira_3.png?v=8",
        "badge": "/assets/logo_sira_3.png?v=8",
        "url": url or dashboard_url,
        "tag": tag,
        "renotify": renotify,
    }

    sent = 0
    invalid_endpoints: set[str] = set()
    for sub in subs:
        ok = send_push(sub, payload)
        if ok:
            sent += 1
        else:
            invalid_endpoints.add(sub.get("endpoint", ""))

    if invalid_endpoints:
        remaining = [s for s in list_subscriptions() if s.get("endpoint") not in invalid_endpoints]
        save_subscriptions(remaining)

    if sent == 0:
        return {
            "ok": False,
            "error": "No se pudo enviar a ninguna suscripción (¿expiradas?)",
            "enviados": 0,
            "suscripciones": len(subs),
            "payload": payload,
        }

    return {
        "ok": True,
        "enviados": sent,
        "suscripciones": len(subs),
        "payload": payload,
    }
