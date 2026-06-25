"""Web Push (VAPID) para notificaciones en navegador/PWA."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pywebpush import WebPushException, Vapid, webpush

from config import (
    AEMET_API_KEY,
    PUSH_STATE_FILE,
    PUSH_SUBSCRIPTIONS_FILE,
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
    VAPID_SUBJECT,
)
from aemet_alerts import alerta_coincide_zona, fetch_active_alerts, fmt_alerta_detalle
from core import read_dashboard, read_json_file
from geo_es import coords_observacion, municipio_por_id, provincia_nombre_de_municipio, provincias
from sismos import alerta_local
from test_overlay import build_test_sismo, save_test_overlay

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


def _normalize_sub(sub: dict) -> dict:
    """Normaliza suscripciones legacy (solo sismo, sin municipio)."""
    out = dict(sub)
    alertas = out.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        out["alertas"] = ["sismo", "meteo"]
    else:
        vals = {str(a).lower() for a in alertas}
        if vals <= {"sismo"}:
            out["alertas"] = ["sismo", "meteo"]
    if out.get("municipio_id"):
        out["municipio_id"] = str(out["municipio_id"]).zfill(5)
    if out.get("provincia_id"):
        out["provincia_id"] = str(out["provincia_id"]).zfill(2)
    return out


def list_subscriptions() -> list[dict]:
    data = read_json_file(PUSH_SUBSCRIPTIONS_FILE)
    raw = data.get("subscriptions", [])
    subs = [_normalize_sub(s) for s in raw if isinstance(s, dict) and s.get("endpoint")]
    if any(_needs_normalize(s) for s in raw if isinstance(s, dict)):
        _write_json(PUSH_SUBSCRIPTIONS_FILE, {"subscriptions": subs})
    return subs


def _needs_normalize(sub: dict) -> bool:
    alertas = sub.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        return True
    vals = {str(a).lower() for a in alertas}
    return vals <= {"sismo"}


def save_subscriptions(subs: list[dict]) -> None:
    _write_json(PUSH_SUBSCRIPTIONS_FILE, {"subscriptions": [_normalize_sub(s) for s in subs]})


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
    subs = [s for s in list_subscriptions() if s.get("endpoint") != endpoint]
    save_subscriptions(subs)
    return len(subs)


def _state() -> dict:
    data = read_json_file(PUSH_STATE_FILE)
    ids_sismo = [str(x) for x in data.get("ids_sismo", data.get("ids_push", []))]
    ids_meteo = [str(x) for x in data.get("ids_meteo", [])]
    return {
        "ids_sismo": sorted(set(ids_sismo)),
        "ids_meteo": sorted(set(ids_meteo)),
    }


def _save_state(state: dict) -> None:
    _write_json(
        PUSH_STATE_FILE,
        {
            "ids_sismo": sorted({str(x) for x in state.get("ids_sismo", [])}),
            "ids_meteo": sorted({str(x) for x in state.get("ids_meteo", [])}),
            "updated": datetime.now(timezone.utc).isoformat(),
        },
    )


def _fmt_parametro_push(parametro: str) -> str:
    return fmt_alerta_detalle({"parametro": parametro})


def _build_payload(s: dict, dashboard_url: str, *, zona: str, dist_km: float) -> dict:
    mag = s.get("magnitud", "—")
    lugar = s.get("lugar", "—")
    score = s.get("score_local", s.get("score_total", "—"))
    nivel = s.get("nivel_local", s.get("nivel_alerta", "—"))
    return {
        "title": f"SIRA · Sismo {nivel}",
        "body": f"M{mag} · score {score} · a {dist_km} km de {zona} · {lugar}",
        "icon": "/assets/logo-sira_4.png?v=8",
        "badge": "/assets/logo-sira_4.png?v=8",
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


def _sub_prefers_meteo(sub: dict) -> bool:
    alertas = sub.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        return True
    vals = {str(a).lower() for a in alertas}
    return any(k in vals for k in ("meteo", "aemet", "all", "todas"))


def _sismo_match_subscription(sismo: dict, sub: dict) -> dict | None:
    """Alerta si el sismo es perceptible y crítico desde la zona de la suscripción."""
    if not _sub_prefers_sismo(sub):
        return None
    lat, lon, zona = coords_observacion(sub.get("municipio_id"), sub.get("localidad_id"))
    try:
        info = alerta_local(sismo, lat, lon)
        if not info:
            return None
        return {**info, "zona": zona}
    except (TypeError, ValueError, KeyError):
        return None


def _sub_zona_geo(sub: dict) -> dict:
    """Provincia/municipio de la suscripción (mismo criterio que el dashboard)."""
    mid = sub.get("municipio_id") or None
    provincia_id = sub.get("provincia_id") or None
    municipio_nom = (municipio_por_id(mid) or {}).get("nombre") if mid else None
    provincia_nom = provincia_nombre_de_municipio(mid)
    if not provincia_nom and provincia_id:
        provincia_nom = next(
            (p.get("nombre") for p in provincias() if str(p.get("id")) == str(provincia_id).zfill(2)),
            None,
        )
    return {
        "provincia_id": provincia_id,
        "municipio_id": mid,
        "provincia": provincia_nom,
        "municipio": municipio_nom,
    }


def _meteo_should_notify(alerta: dict, sub: dict) -> bool:
    """¿Enviar aviso meteo a esta suscripción según zona afectada?"""
    sub = _normalize_sub(sub)
    if not _sub_prefers_meteo(sub):
        return False
    return alerta_coincide_zona(alerta, **_sub_zona_geo(sub))


def _aemet_match_subscription(alerta: dict, sub: dict) -> bool:
    return _meteo_should_notify(alerta, sub)


def _build_aemet_payload(alerta: dict, dashboard_url: str, *, renotify: bool | None = None) -> dict:
    level = str(alerta.get("level", "amarillo")).lower()
    nivel = {"amarillo": "MODERADO", "naranja": "ALTO", "rojo": "CRÍTICO"}.get(level, level.upper())
    fenomeno = alerta.get("fenomeno_desc") or "fenómeno meteorológico"
    parametro = alerta.get("parametro") or ""
    detalle = _fmt_parametro_push(parametro)
    zona = alerta.get("area_desc") or "tu zona"
    fenomeno_code = str(alerta.get("fenomeno") or "xx").lower()
    return {
        "title": f"SIRA · {fenomeno} {nivel}",
        "body": f"AEMET {level.upper()} · {zona}" + (f" · {detalle}" if detalle else ""),
        "icon": "/assets/logo-sira_4.png?v=8",
        "badge": "/assets/logo-sira_4.png?v=8",
        "url": dashboard_url,
        "tag": f"sira-aemet-{fenomeno_code}-{alerta.get('id')}",
        "renotify": alerta.get("is_test", False) if renotify is None else renotify,
    }


def send_test_meteo_push(dashboard_url: str, alerta: dict) -> dict:
    """Envía aviso meteo de prueba solo a suscriptores en la zona afectada."""
    all_subs = list_subscriptions()
    payload = _build_aemet_payload(alerta, dashboard_url, renotify=True)
    sent = 0
    errors = 0
    invalid_endpoints: set[str] = set()
    diagnostico = []

    for sub in all_subs:
        geo = _sub_zona_geo(_normalize_sub(sub))
        eligible = _meteo_should_notify(alerta, sub)
        diagnostico.append(
            {
                **geo,
                "prefiere_meteo": _sub_prefers_meteo(_normalize_sub(sub)),
                "coincide": eligible,
                "alerta_zona": alerta.get("zona"),
                "alerta_area": alerta.get("area_desc"),
            }
        )
        if not eligible:
            continue
        result = send_push(sub, payload)
        if result == "ok":
            sent += 1
        elif result == "gone":
            invalid_endpoints.add(sub.get("endpoint", ""))
        else:
            errors += 1

    if not all_subs:
        return {
            "ok": False,
            "error": "No hay suscripciones activas",
            "enviados": 0,
            "suscripciones": 0,
            "diagnostico": diagnostico,
        }

    if invalid_endpoints:
        save_subscriptions([s for s in list_subscriptions() if s.get("endpoint") not in invalid_endpoints])
    return {
        "ok": sent > 0,
        "enviados": sent,
        "suscripciones": len(all_subs),
        "payload": payload,
        "diagnostico": diagnostico,
        "errores_transitorios": errors,
        "error": None if sent > 0 else "No se pudo enviar a ninguna suscripción (revisa diagnostico)",
    }


def debug_push_state() -> dict:
    return {
        "suscripciones": list_subscriptions(),
        "estado_push": _state(),
        "vapid_ok": vapid_enabled(),
    }


def debug_aemet_matches(*, provincia_id: str | None = None, municipio_id: str | None = None, localidad_id: str | None = None) -> dict:
    subs = [
        {
            "endpoint": "debug",
            "keys": {},
            "provincia_id": provincia_id,
            "municipio_id": municipio_id,
            "localidad_id": localidad_id,
            "alertas": ["meteo"],
        }
    ]
    avisos = fetch_active_alerts(AEMET_API_KEY) if AEMET_API_KEY else []
    evaluados = []
    for alerta in avisos:
        evaluados.append(
            {
                **alerta,
                "match_debug": _aemet_match_subscription(alerta, subs[0]),
            }
        )
    return {
        "aemet_api_configurada": bool(AEMET_API_KEY),
        "filtros": {
            "provincia_id": provincia_id,
            "municipio_id": municipio_id,
            "localidad_id": localidad_id,
        },
        "avisos_activos": evaluados,
    }


def _push_gone(exc: WebPushException) -> bool:
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) in (404, 410):
        return True
    return "410" in str(exc) or "404" in str(exc) or "gone" in str(exc).lower()


def send_push(subscription: dict, payload: dict) -> str:
    """ok | gone (suscripción caducada) | error (fallo transitorio)."""
    if not vapid_enabled():
        return "error"
    try:
        webpush(
            subscription_info=_subscription_info(subscription),
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_get_vapid_signer(),
            vapid_claims={"sub": VAPID_SUBJECT},
            ttl=3600,
        )
        return "ok"
    except WebPushException as exc:
        log.warning("WebPush fallo: %s", exc)
        return "gone" if _push_gone(exc) else "error"
    except (ValueError, TypeError, KeyError) as exc:
        log.warning("Push inválido: %s", exc)
        return "gone"


def notify_new_alerts(dashboard_url: str) -> int:
    if not vapid_enabled():
        return 0
    data = read_dashboard()
    todos = data.get("sismos", [])

    state = _state()
    prev_sismo = set(state["ids_sismo"])
    if todos and not prev_sismo:
        state["ids_sismo"] = sorted({str(s["id"]) for s in todos if s.get("id")})
        _save_state(state)
        return 0

    nuevos = [s for s in todos if s.get("id") and str(s["id"]) not in prev_sismo] if todos else []

    subs = list_subscriptions()
    sent = 0
    invalid_endpoints: set[str] = set()
    procesados_sismo: set[str] = set()

    for s in nuevos:
        sid = str(s["id"])
        for sub in subs:
            info = _sismo_match_subscription(s, sub)
            if not info:
                continue
            payload = _build_payload(info, dashboard_url, zona=info["zona"], dist_km=info["dist_local_km"])
            result = send_push(sub, payload)
            if result == "ok":
                sent += 1
            elif result == "gone":
                invalid_endpoints.add(sub.get("endpoint", ""))
        procesados_sismo.add(sid)

    # Avisos meteorológicos AEMET en CAP (opcional según API key)
    procesados_meteo: set[str] = set()
    prev_meteo = set(state["ids_meteo"])
    if AEMET_API_KEY:
        try:
            avisos = fetch_active_alerts(AEMET_API_KEY)
        except Exception as exc:  # noqa: BLE001
            log.warning("AEMET CAP: %s", exc)
            avisos = []
        if avisos and not prev_meteo:
            state["ids_meteo"] = sorted({str(a.get("id")) for a in avisos if a.get("id")})
            _save_state(state)
            return sent
        nuevos_meteo = [a for a in avisos if str(a.get("id")) not in prev_meteo]
        for a in nuevos_meteo:
            aid = str(a.get("id"))
            if not aid:
                continue
            for sub in subs:
                if not _meteo_should_notify(a, sub):
                    continue
                result = send_push(sub, _build_aemet_payload(a, dashboard_url))
                if result == "ok":
                    sent += 1
                elif result == "gone":
                    invalid_endpoints.add(sub.get("endpoint", ""))
            procesados_meteo.add(aid)

    if invalid_endpoints:
        subs = [s for s in subs if s.get("endpoint") not in invalid_endpoints]
        save_subscriptions(subs)

    state["ids_sismo"] = sorted(prev_sismo | procesados_sismo)
    state["ids_meteo"] = sorted(prev_meteo | procesados_meteo)
    _save_state(state)
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
    mostrar_en_mapa: bool = True,
    magnitud: float | None = None,
    lat: float | None = None,
    lon: float | None = None,
    profundidad: float | None = None,
    lugar: str | None = None,
    overlay_minutos: int = 30,
) -> dict:
    """Envía notificación de prueba y opcionalmente un sismo efímero en el mapa."""
    if not vapid_enabled():
        return {"ok": False, "error": "Web Push no configurado", "enviados": 0, "suscripciones": 0}

    overlay_meta = None
    if mostrar_en_mapa:
        sismo_prueba = build_test_sismo(
            tag=tag,
            magnitud=magnitud if magnitud is not None else 4.2,
            lat=lat,
            lon=lon,
            profundidad=profundidad if profundidad is not None else 10.0,
            lugar=lugar,
        )
        overlay_meta = save_test_overlay(sismo_prueba, ttl_min=overlay_minutos)

    subs = list_subscriptions()
    if solo_municipio_id:
        target = str(solo_municipio_id).zfill(5)
        subs = [
            s for s in subs
            if not s.get("municipio_id") or str(s["municipio_id"]).zfill(5) == target
        ]

    payload = {
        "title": title or "SIRA · Sismo ALTO",
        "body": body or "M4.2 · score 68 · 12 km al E de Valencia (prueba)",
        "icon": "/assets/logo-sira_4.png?v=8",
        "badge": "/assets/logo-sira_4.png?v=8",
        "url": url or dashboard_url,
        "tag": tag,
        "renotify": renotify,
    }

    if not subs:
        if overlay_meta:
            return {
                "ok": True,
                "enviados": 0,
                "suscripciones": 0,
                "payload": payload,
                "mapa_prueba": overlay_meta,
                "aviso": "Sin suscripciones push; solo mapa de prueba",
            }
        return {"ok": False, "error": "No hay suscripciones activas", "enviados": 0, "suscripciones": 0}

    sent = 0
    invalid_endpoints: set[str] = set()
    for sub in subs:
        result = send_push(sub, payload)
        if result == "ok":
            sent += 1
        elif result == "gone":
            invalid_endpoints.add(sub.get("endpoint", ""))

    if invalid_endpoints:
        remaining = [s for s in list_subscriptions() if s.get("endpoint") not in invalid_endpoints]
        save_subscriptions(remaining)

    base = {
        "enviados": sent,
        "suscripciones": len(subs),
        "payload": payload,
        "mapa_prueba": overlay_meta,
    }
    if sent == 0 and not overlay_meta:
        return {"ok": False, "error": "No se pudo enviar a ninguna suscripción (¿expiradas?)", **base}
    if sent == 0:
        return {"ok": True, "aviso": "Push fallido; mapa de prueba activo", **base}
    return {"ok": True, **base}
