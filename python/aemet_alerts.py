"""Avisos AEMET Meteoalerta (CAP) para notificaciones locales."""
from __future__ import annotations

import tarfile
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from io import BytesIO

from config import AEMET_ALERT_PHENOMENA, AEMET_PUSH_MIN_LEVEL, HTTP_TIMEOUT
from core import fetch_aemet_bytes

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
SEV_TO_COLOR = {
    "minor": "verde",
    "moderate": "amarillo",
    "severe": "naranja",
    "extreme": "rojo",
}
LEVEL_ORDER = {"verde": 0, "amarillo": 1, "naranja": 2, "rojo": 3}
PHENO_LABEL = {
    "AT": "temperatura máxima",
    "BT": "temperatura mínima",
    "VI": "viento",
    "TO": "tormenta",
    "PR": "lluvia",
    "CO": "fenómeno costero",
    "NE": "nevadas",
    "VS": "polvo en suspensión",
    "NI": "niebla",
    "DH": "deshielo",
    "GA": "galerna",
    "RI": "rissaga",
    "AL": "aludes",
}
PHENO_ICON = {
    "AT": "🌡️",
    "BT": "🥶",
    "VI": "💨",
    "TO": "⛈️",
    "PR": "🌧️",
    "CO": "🌊",
    "NE": "❄️",
    "VS": "🌫️",
    "NI": "🌁",
    "DH": "💧",
    "GA": "🌬️",
    "RI": "🌊",
    "AL": "🏔️",
}


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _norm_area(value: str | None) -> str:
    if not value:
        return ""
    txt = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(txt.strip().lower().split())


def _nombre_tokens(nombre: str | None) -> list[str]:
    if not nombre:
        return []
    return [t for p in str(nombre).split("/") if (t := _norm_area(p.strip()))]


def alerta_coincide_zona(
    alerta: dict,
    *,
    provincia_id: str | None = None,
    municipio_id: str | None = None,
    provincia: str | None = None,
    municipio: str | None = None,
) -> bool:
    """True si el aviso aplica a la zona seleccionada (mismo criterio que push)."""
    mid = str(municipio_id or "").zfill(5) if municipio_id else ""
    zona = str(alerta.get("zona") or "")
    if alerta.get("is_test") and zona.startswith("test-"):
        test_mid = zona[5:].zfill(5)
        return bool(mid and mid == test_mid)

    area = _norm_area(alerta.get("area_desc"))
    if not area:
        return not (provincia_id or municipio_id or provincia or municipio)

    for token in _nombre_tokens(provincia):
        if token in area:
            return True

    if provincia_id:
        from geo_es import provincias

        pname = next(
            (p.get("nombre") for p in provincias() if str(p.get("id")) == str(provincia_id).zfill(2)),
            "",
        )
        for token in _nombre_tokens(pname):
            if token in area:
                return True

    for token in _nombre_tokens(municipio):
        if token in area:
            return True

    if mid:
        from geo_es import municipio_por_id

        muni = municipio_por_id(mid)
        if muni:
            token = _norm_area(muni.get("nombre"))
            if token and token in area:
                return True

    return False


def fmt_alerta_detalle(alerta: dict) -> str:
    parametro = (alerta.get("parametro") or "").strip()
    if parametro and ";" in parametro:
        parts = [p.strip() for p in parametro.split(";") if p.strip()]
        if len(parts) >= 3:
            return f"{parts[1]}: {parts[2]}"
        if len(parts) == 2:
            return f"{parts[0]}: {parts[1]}"
        if parts:
            return parts[0]
    if parametro:
        return parametro
    return (alerta.get("description") or "Sin detalle").strip()


def alerta_firma(alerta: dict) -> tuple[str, str, str, str]:
    """Clave de contenido visible: fenómeno, nivel, zona y valor (ºC, km/h…)."""
    return (
        str(alerta.get("fenomeno") or "").upper().strip(),
        str(alerta.get("level") or "amarillo").lower().strip(),
        _norm_area(alerta.get("area_desc")),
        _norm(fmt_alerta_detalle(alerta)),
    )


def deduplicar_alertas(alertas: list[dict]) -> list[dict]:
    """Un aviso por combinación única de fenómeno, nivel, zona y magnitud."""
    prioridad = {"rojo": 3, "naranja": 2, "amarillo": 1}
    ordenadas = sorted(
        alertas,
        key=lambda a: (
            -prioridad.get(str(a.get("level", "")).lower(), 0),
            str(a.get("fenomeno", "")),
        ),
    )
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict] = []
    for a in ordenadas:
        key = alerta_firma(a)
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pick_info(root: ET.Element) -> ET.Element | None:
    infos = root.findall("cap:info", CAP_NS)
    if not infos:
        return None
    for info in infos:
        lang = (info.findtext("cap:language", default="", namespaces=CAP_NS) or "").lower()
        if lang.startswith("es"):
            return info
    return infos[0]


def _event_code(info: ET.Element, name: str) -> str | None:
    for ec in info.findall("cap:eventCode", CAP_NS):
        vn = ec.findtext("cap:valueName", default="", namespaces=CAP_NS)
        vv = ec.findtext("cap:value", default="", namespaces=CAP_NS)
        if _norm(vn) == _norm(name):
            return vv
    return None


def _extract_aemet(info: ET.Element, area: ET.Element) -> dict:
    level = _event_code(info, "AEMET-Meteoalerta nivel") or ""
    pheno_raw = _event_code(info, "AEMET-Meteoalerta fenomeno") or ""
    param_raw = _event_code(info, "AEMET-Meteoalerta parametro") or ""
    prob_raw = _event_code(info, "AEMET-Meteoalerta probabilidad") or ""
    zona = _event_code(area, "AEMET-Meteoalerta zona") or ""
    pheno = pheno_raw.split(";", 1)[0].strip().upper()
    return {
        "nivel": level.strip().lower(),
        "fenomeno": pheno,
        "fenomeno_desc": PHENO_LABEL.get(pheno, (pheno_raw.split(";", 1)[-1] if ";" in pheno_raw else pheno)),
        "parametro": param_raw,
        "probabilidad": prob_raw,
        "zona": zona,
    }


def _severity_to_level(severity: str | None, fallback: str) -> str:
    if fallback in LEVEL_ORDER:
        return fallback
    return SEV_TO_COLOR.get((severity or "").strip().lower(), "verde")


def _valid_level(level: str) -> bool:
    return LEVEL_ORDER.get(level, 0) >= LEVEL_ORDER.get(AEMET_PUSH_MIN_LEVEL, 2)


def _is_active(onset: str | None, expires: str | None) -> bool:
    now = datetime.now(timezone.utc)
    d_on = _parse_iso(onset)
    d_ex = _parse_iso(expires)
    if d_on and now < d_on:
        return False
    if d_ex and now >= d_ex:
        return False
    return True


def _iter_cap_members(tar_bytes: bytes):
    with tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:gz") as tg:
        for m in tg.getmembers():
            if not m.isfile() or not m.name.lower().endswith(".xml"):
                continue
            f = tg.extractfile(m)
            if not f:
                continue
            yield f.read()


def fetch_active_alerts(aemet_api_key: str) -> list[dict]:
    """Devuelve avisos CAP activos y filtrados por fenómeno/nivel configurados."""
    raw = fetch_aemet_bytes("avisos_cap/ultimoelaborado/area/esp", aemet_api_key, timeout=max(45, HTTP_TIMEOUT))
    out: list[dict] = []
    for xml_bytes in _iter_cap_members(raw):
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            continue
        msg_type = (root.findtext("cap:msgType", default="", namespaces=CAP_NS) or "").lower()
        if msg_type == "cancel":
            continue
        info = _pick_info(root)
        if info is None:
            continue
        onset = info.findtext("cap:onset", default="", namespaces=CAP_NS)
        expires = info.findtext("cap:expires", default="", namespaces=CAP_NS)
        if not _is_active(onset, expires):
            continue
        severity = info.findtext("cap:severity", default="", namespaces=CAP_NS)
        headline = info.findtext("cap:headline", default="", namespaces=CAP_NS) or ""
        description = info.findtext("cap:description", default="", namespaces=CAP_NS) or ""
        urgency = info.findtext("cap:urgency", default="", namespaces=CAP_NS) or ""
        certainty = info.findtext("cap:certainty", default="", namespaces=CAP_NS) or ""
        identifier = root.findtext("cap:identifier", default="", namespaces=CAP_NS) or ""

        for area in info.findall("cap:area", CAP_NS):
            area_desc = area.findtext("cap:areaDesc", default="", namespaces=CAP_NS) or ""
            aemet = _extract_aemet(info, area)
            level = _severity_to_level(severity, aemet["nivel"])
            if not _valid_level(level):
                continue
            if aemet["fenomeno"] and AEMET_ALERT_PHENOMENA and aemet["fenomeno"] not in AEMET_ALERT_PHENOMENA:
                continue
            out.append(
                {
                    "id": f"aemet:{identifier}:{aemet['zona']}:{aemet['fenomeno'] or 'XX'}",
                    "source": "AEMET",
                    "level": level,
                    "severity": (severity or "").lower(),
                    "urgency": urgency,
                    "certainty": certainty,
                    "headline": headline,
                    "description": description,
                    "area_desc": area_desc,
                    "onset": onset,
                    "expires": expires,
                    **aemet,
                    "icon": PHENO_ICON.get(aemet["fenomeno"], "⚠️"),
                }
            )
    return out
