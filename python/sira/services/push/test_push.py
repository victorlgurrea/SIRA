"""Helpers de prueba y debug para Web Push."""
from __future__ import annotations

import logging

from sira.config.settings import AEMET_API_KEY, ZONA
from sira.infrastructure.sources.meteo.aemet_alerts import (
    deduplicar_alertas,
    fetch_active_alerts,
    meteo_push_key,
)
from sira.domain.seismic.tsunami_oficial import anexar_boletin_tsunami
from sira.services.overlays.sismo import build_test_sismo, save_test_overlay
from sira.services.push.notify import (
    _aemet_match_subscription,
    _meteo_should_notify,
    _save_state,
    _state,
    _sub_zona_geo,
    send_push,
)
from sira.services.push.payloads import (
    _build_aemet_payload,
    _build_payload,
    _build_tsunami_payload,
    _sub_prefers_meteo,
)
from sira.services.push.subscriptions import (
    _normalize_sub,
    list_subscriptions,
    save_subscriptions,
    vapid_enabled,
)

log = logging.getLogger(__name__)


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


def send_bootstrap_meteo_for_subscription(dashboard_url: str, sub: dict) -> dict:
    """Al suscribirse: envía avisos meteo naranja/rojo ya activos para esa zona.

    Evita el caso en que el servidor ya "sembró" el estado global y el cron no vuelve
    a enviar avisos existentes a nuevas suscripciones.
    """
    sub = _normalize_sub(sub)
    if not _sub_prefers_meteo(sub):
        return {"ok": True, "enviados": 0, "motivo": "suscripción sin meteo"}
    if not vapid_enabled():
        return {"ok": False, "enviados": 0, "error": "Web Push no configurado"}
    if not AEMET_API_KEY:
        return {"ok": True, "enviados": 0, "motivo": "AEMET_API_KEY no configurada"}

    try:
        avisos = deduplicar_alertas(fetch_active_alerts(AEMET_API_KEY or None))
    except Exception as exc:  # noqa: BLE001
        log.warning("AEMET CAP (bootstrap): %s", exc)
        avisos = []

    candidatos = [
        a for a in avisos
        if str(a.get("level") or "").lower() in {"naranja", "rojo"}
        and _meteo_should_notify(a, sub)
    ]
    sent = 0
    errors = 0
    keys_enviados: set[str] = set()
    for a in candidatos:
        key = meteo_push_key(a)
        result = send_push(sub, _build_aemet_payload(a, dashboard_url, renotify=True))
        if result == "ok":
            sent += 1
            if key:
                keys_enviados.add(key)
        elif result == "gone":
            return {"ok": False, "enviados": sent, "error": "Suscripción caducada"}
        else:
            errors += 1

    # Marca estos avisos como ya notificados en el estado global para evitar bucles
    # con el cron /api/cron/meteo.
    if keys_enviados:
        state = _state()
        prev = set(state.get("ids_meteo", []))
        state["ids_meteo"] = sorted(prev | keys_enviados)
        _save_state(state)

    return {
        "ok": sent > 0,
        "enviados": sent,
        "candidatos": len(candidatos),
        "errores_transitorios": errors,
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
    avisos = fetch_active_alerts(AEMET_API_KEY or None)
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
    simular_real: bool = True,
    tsunami: bool = False,
) -> dict:
    """Envía notificación de prueba y opcionalmente un sismo efímero en el mapa."""
    if not vapid_enabled():
        return {"ok": False, "error": "Web Push no configurado", "enviados": 0, "suscripciones": 0}

    overlay_meta = None
    sismo_prueba = None
    if mostrar_en_mapa:
        sismo_prueba = build_test_sismo(
            tag=tag,
            magnitud=magnitud if magnitud is not None else 4.2,
            lat=lat,
            lon=lon,
            profundidad=profundidad if profundidad is not None else 10.0,
            lugar=lugar,
            simular_real=simular_real,
            tsunami=tsunami,
        )
        overlay_meta = save_test_overlay(sismo_prueba, ttl_min=overlay_minutos)

    subs = list_subscriptions()
    if solo_municipio_id:
        target = str(solo_municipio_id).zfill(5)
        subs = [
            s for s in subs
            if str(s.get("municipio_id") or "").zfill(5) == target
        ]

    if simular_real and sismo_prueba:
        dist_km = float(sismo_prueba.get("dist_valencia_km") or 0)
        if sismo_prueba.get("en_mar") and sismo_prueba.get("alerta_tsunami"):
            sismo_prueba = anexar_boletin_tsunami(
                sismo_prueba,
                ZONA["lat_ref"],
                ZONA["lon_ref"],
                None,
            )
            payload = _build_tsunami_payload(
                sismo_prueba,
                url or dashboard_url,
                zona=ZONA["ciudad_ref"],
                dist_km=dist_km,
            )
        else:
            payload = _build_payload(
                sismo_prueba,
                url or dashboard_url,
                zona=ZONA["ciudad_ref"],
                dist_km=dist_km,
            )
        payload["url"] = url or dashboard_url
        payload["renotify"] = renotify
    else:
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
