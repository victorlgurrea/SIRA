"""Envío de notificaciones Web Push y matching por suscripción."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pywebpush import WebPushException, webpush

from sira.config.settings import AEMET_API_KEY, VAPID_SUBJECT
from sira.infrastructure.sources.meteo.aemet_alerts import (
    alerta_coincide_zona,
    deduplicar_alertas,
    fetch_active_alerts,
    meteo_push_key,
)
from sira.infrastructure.http.client import clear_meteo_live_cache, read_dashboard
from sira.infrastructure.persistence.sqlite import get_push_state, save_push_state
from sira.infrastructure.geo.es import (
    coords_observacion,
    municipio_por_id,
    provincia_nombre_de_municipio,
    provincias,
)
from sira.infrastructure.sources.fire.firms import alerta_incendio_local
from sira.domain.seismic.sismos import alerta_local, alerta_tsunami_local
from sira.services.push.payloads import (
    _build_aemet_payload,
    _build_incendio_payload,
    _build_payload,
    _build_tsunami_payload,
    _sub_prefers_incendio,
    _sub_prefers_meteo,
    _sub_prefers_sismo,
    _sub_prefers_tsunami,
)
from sira.services.push.subscriptions import (
    _get_vapid_signer,
    _normalize_sub,
    _subscription_info,
    list_subscriptions,
    save_subscriptions,
    vapid_enabled,
)

log = logging.getLogger(__name__)


def _state() -> dict:
    data = get_push_state()
    return {
        "ids_sismo": sorted(set(data.get("ids_sismo", []))),
        "ids_meteo": sorted(set(data.get("ids_meteo", []))),
        "ids_incendio": sorted(set(data.get("ids_incendio", []))),
        "ids_tsunami": sorted(set(data.get("ids_tsunami", []))),
    }


def _save_state(state: dict) -> None:
    save_push_state({
        "ids_sismo": sorted({str(x) for x in state.get("ids_sismo", [])}),
        "ids_meteo": sorted({str(x) for x in state.get("ids_meteo", [])}),
        "ids_incendio": sorted({str(x) for x in state.get("ids_incendio", [])}),
        "ids_tsunami": sorted({str(x) for x in state.get("ids_tsunami", [])}),
        "updated": datetime.now(timezone.utc).isoformat(),
    })


def _sismo_match_subscription(sismo: dict, sub: dict) -> dict | None:
    """Alerta si el sismo es perceptible desde la zona de la suscripción."""
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


def _tsunami_match_subscription(sismo: dict, sub: dict) -> dict | None:
    """Alerta si el aviso tsunami USGS alcanza la zona de la suscripción."""
    if not _sub_prefers_tsunami(sub):
        return None
    lat, lon, zona = coords_observacion(sub.get("municipio_id"), sub.get("localidad_id"))
    try:
        info = alerta_tsunami_local(sismo, lat, lon, sub.get("municipio_id"))
        if not info:
            return None
        return {**info, "zona": zona}
    except (TypeError, ValueError, KeyError):
        return None


def _incendio_match_subscription(incendio: dict, sub: dict) -> dict | None:
    """Alerta si un foco activo afecta la zona de la suscripción."""
    if not _sub_prefers_incendio(sub):
        return None
    lat, lon, zona = coords_observacion(sub.get("municipio_id"), sub.get("localidad_id"))
    try:
        info = alerta_incendio_local(incendio, lat, lon)
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


def _split_meteo_bootstrap(avisos: list[dict], prev_meteo: set[str]) -> tuple[set[str], list[dict]]:
    """Primer ciclo: evita spam inicial, pero deja pasar avisos naranja/rojo ya activos."""
    if prev_meteo:
        return prev_meteo, [a for a in avisos if meteo_push_key(a) not in prev_meteo]

    nuevos = [a for a in avisos if str(a.get("level") or "").lower() in {"naranja", "rojo"}]
    seed = {meteo_push_key(a) for a in avisos if meteo_push_key(a)}
    return seed, nuevos


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
    todos = [
        s for s in data.get("sismos", [])
        if s.get("id")
        and not str(s["id"]).startswith("sim")
        and not s.get("es_prueba")
    ]
    incendios = data.get("incendios", [])

    state = _state()
    prev_sismo = set(state["ids_sismo"])
    prev_tsunami = set(state["ids_tsunami"])
    prev_incendio = set(state["ids_incendio"])
    prev_meteo = set(state["ids_meteo"])

    def _es_tsunami(s: dict) -> bool:
        if not s.get("id"):
            return False
        en_mar = s.get("en_mar")
        if en_mar is None:
            from sira.infrastructure.parsers.fuentes import epicentro_en_mar as _en_mar

            en_mar = _en_mar(
                float(s["lat"]),
                float(s["lon"]),
                lugar=s.get("lugar"),
                profundidad_km=float(s.get("profundidad") or 0),
                usgs_tsunami=s.get("usgs_tsunami"),
            )
        if not en_mar:
            return False
        if s.get("alerta_tsunami"):
            return True
        from sira.domain.seismic.sismos import riesgo_tsunami as _riesgo

        return _riesgo(
            float(s.get("magnitud") or 0),
            float(s.get("profundidad") or 0),
            True,
            s.get("usgs_tsunami"),
        )

    sismos_tsunami = [s for s in todos if _es_tsunami(s)]

    # Semilla inicial por tipo: no notificar el inventario ya presente al desplegar.
    if todos and not state["ids_sismo"]:
        prev_sismo = {str(s["id"]) for s in todos if s.get("id")}
    if sismos_tsunami and not state["ids_tsunami"]:
        prev_tsunami = {str(s["id"]) for s in sismos_tsunami if s.get("id")}
    if incendios and not state["ids_incendio"]:
        prev_incendio = {str(i["id"]) for i in incendios if i.get("id")}

    subs = list_subscriptions()
    sent = 0
    invalid_endpoints: set[str] = set()
    procesados_sismo: set[str] = set()
    procesados_tsunami: set[str] = set()
    procesados_incendio: set[str] = set()
    procesados_meteo: set[str] = set()

    nuevos = [s for s in todos if s.get("id") and str(s["id"]) not in prev_sismo]
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

    nuevos_tsunami = [
        s for s in sismos_tsunami
        if s.get("id") and str(s["id"]) not in prev_tsunami
    ]
    for s in nuevos_tsunami:
        sid = str(s["id"])
        for sub in subs:
            info = _tsunami_match_subscription(s, sub)
            if not info:
                continue
            payload = _build_tsunami_payload(
                info, dashboard_url, zona=info["zona"], dist_km=float(info["dist_local_km"])
            )
            result = send_push(sub, payload)
            if result == "ok":
                sent += 1
            elif result == "gone":
                invalid_endpoints.add(sub.get("endpoint", ""))
        procesados_tsunami.add(sid)

    nuevos_incendio = [
        i for i in incendios
        if i.get("id") and str(i["id"]) not in prev_incendio
    ]
    for inc in nuevos_incendio:
        iid = str(inc["id"])
        for sub in subs:
            info = _incendio_match_subscription(inc, sub)
            if not info:
                continue
            payload = _build_incendio_payload(
                info, dashboard_url, zona=info["zona"], dist_km=float(info["dist_local_km"])
            )
            result = send_push(sub, payload)
            if result == "ok":
                sent += 1
            elif result == "gone":
                invalid_endpoints.add(sub.get("endpoint", ""))
        procesados_incendio.add(iid)

    if AEMET_API_KEY:
        try:
            avisos = deduplicar_alertas(fetch_active_alerts(AEMET_API_KEY or None))
        except Exception as exc:  # noqa: BLE001
            log.warning("AEMET CAP: %s", exc)
            avisos = []
        prev_meteo, nuevos_meteo = _split_meteo_bootstrap(avisos, prev_meteo)
        for a in nuevos_meteo:
            key = meteo_push_key(a)
            if not key:
                continue
            for sub in subs:
                if not _meteo_should_notify(a, sub):
                    continue
                result = send_push(sub, _build_aemet_payload(a, dashboard_url))
                if result == "ok":
                    sent += 1
                elif result == "gone":
                    invalid_endpoints.add(sub.get("endpoint", ""))
            procesados_meteo.add(key)
        if procesados_meteo:
            clear_meteo_live_cache()

    if invalid_endpoints:
        subs = [s for s in subs if s.get("endpoint") not in invalid_endpoints]
        save_subscriptions(subs)

    state["ids_sismo"] = sorted(prev_sismo | procesados_sismo)
    state["ids_tsunami"] = sorted(prev_tsunami | procesados_tsunami)
    state["ids_incendio"] = sorted(prev_incendio | procesados_incendio)
    state["ids_meteo"] = sorted(prev_meteo | procesados_meteo)
    _save_state(state)
    return sent


def notify_new_meteo_alerts(dashboard_url: str) -> int:
    """Notifica solo avisos AEMET (CAP) de meteo (sin sismos/incendios/tsunami)."""
    if not vapid_enabled():
        return 0
    if not AEMET_API_KEY:
        return 0

    subs = list_subscriptions()
    state = _state()
    prev_meteo = set(state["ids_meteo"])

    try:
        avisos = deduplicar_alertas(fetch_active_alerts(AEMET_API_KEY or None))
    except Exception as exc:  # noqa: BLE001
        log.warning("AEMET CAP (meteo-only): %s", exc)
        avisos = []

    prev_meteo, nuevos_meteo = _split_meteo_bootstrap(avisos, prev_meteo)
    sent = 0
    invalid_endpoints: set[str] = set()
    procesados_meteo: set[str] = set()

    for a in nuevos_meteo:
        key = meteo_push_key(a)
        if not key:
            continue
        for sub in subs:
            if not _meteo_should_notify(a, sub):
                continue
            result = send_push(sub, _build_aemet_payload(a, dashboard_url))
            if result == "ok":
                sent += 1
            elif result == "gone":
                invalid_endpoints.add(sub.get("endpoint", ""))
        procesados_meteo.add(key)

    if procesados_meteo:
        clear_meteo_live_cache()

    if invalid_endpoints:
        subs = [s for s in subs if s.get("endpoint") not in invalid_endpoints]
        save_subscriptions(subs)

    state["ids_meteo"] = sorted(prev_meteo | procesados_meteo)
    _save_state(state)
    return sent
