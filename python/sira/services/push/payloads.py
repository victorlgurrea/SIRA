"""Constructores de payload Web Push y preferencias de alerta."""
from __future__ import annotations

from sira.infrastructure.sources.meteo.aemet_alerts import (
    fmt_alerta_detalle,
    meteo_push_key,
    texto_push_meteo,
)
from sira.domain.seismic.tsunami_oficial import texto_push_tsunami


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


def _build_tsunami_payload(s: dict, dashboard_url: str, *, zona: str, dist_km: float) -> dict:
    lugar = s.get("lugar", "—")
    return {
        "title": "SIRA · Alerta tsunami",
        "body": texto_push_tsunami(s, zona=zona, dist_km=dist_km) + f" · {lugar}",
        "icon": "/assets/logo-sira_4.png?v=8",
        "badge": "/assets/logo-sira_4.png?v=8",
        "url": dashboard_url,
        "tag": f"sira-tsunami-{s.get('id')}",
        "renotify": False,
    }


def _build_incendio_payload(inc: dict, dashboard_url: str, *, zona: str, dist_km: float) -> dict:
    radio = inc.get("radio_km", "—")
    frp = inc.get("frp_mw", "—")
    return {
        "title": "SIRA · Incendio activo cerca",
        "body": f"Foco a {dist_km:.0f} km de {zona} · radio ~{radio} km · FRP {frp} MW",
        "icon": "/assets/logo-sira_4.png?v=8",
        "badge": "/assets/logo-sira_4.png?v=8",
        "url": dashboard_url,
        "tag": f"sira-incendio-{inc.get('id')}",
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


def _sub_prefers_incendio(sub: dict) -> bool:
    alertas = sub.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        return True
    vals = {str(a).lower() for a in alertas}
    return any(k in vals for k in ("incendio", "fuego", "all", "todas"))


def _sub_prefers_tsunami(sub: dict) -> bool:
    alertas = sub.get("alertas")
    if not isinstance(alertas, list) or not alertas:
        return True
    vals = {str(a).lower() for a in alertas}
    return any(k in vals for k in ("tsunami", "mar", "all", "todas"))


def _build_aemet_payload(alerta: dict, dashboard_url: str, *, renotify: bool | None = None) -> dict:
    title, body = texto_push_meteo(alerta)
    fenomeno_code = str(alerta.get("fenomeno") or "xx").lower()
    return {
        "title": title,
        "body": body,
        "icon": "/assets/logo-sira_4.png?v=8",
        "badge": "/assets/logo-sira_4.png?v=8",
        "url": dashboard_url,
        "tag": f"sira-aemet-{fenomeno_code}-{meteo_push_key(alerta)}",
        "renotify": alerta.get("is_test", False) if renotify is None else renotify,
    }
