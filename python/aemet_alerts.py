"""Avisos AEMET Meteoalerta (CAP) para notificaciones locales."""
from __future__ import annotations

import re
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


def _misma_provincia(municipio_a: str | None, municipio_b: str | None) -> bool:
    if not municipio_a or not municipio_b:
        return False
    from geo_es import provincia_de_municipio

    pa = provincia_de_municipio(str(municipio_a).zfill(5))
    pb = provincia_de_municipio(str(municipio_b).zfill(5))
    return bool(pa and pb and pa == pb)


def _coincide_por_area(
    area_desc: str | None,
    provincia_id: str | None,
    provincia: str | None,
    municipio: str | None,
    municipio_ref: str | None = None,
) -> bool:
    area = _norm_area(area_desc)
    if not area:
        return False
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
    if municipio_ref:
        from geo_es import municipio_por_id

        muni = municipio_por_id(str(municipio_ref).zfill(5))
        if muni:
            token = _norm_area(muni.get("nombre"))
            if token and token in area:
                return True
    return False


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
        from geo_es import provincia_de_municipio

        test_mid = zona[5:].zfill(5)
        test_pid = provincia_de_municipio(test_mid)
        if mid and mid == test_mid:
            return True
        if mid and _misma_provincia(mid, test_mid):
            return True
        sub_pid = str(provincia_id).zfill(2) if provincia_id else (provincia_de_municipio(mid) if mid else None)
        if test_pid and sub_pid and test_pid == sub_pid:
            return True
        return _coincide_por_area(alerta.get("area_desc"), provincia_id, provincia, municipio, mid or None)

    if not _norm_area(alerta.get("area_desc")):
        return not (provincia_id or municipio_id or provincia or municipio)

    return _coincide_por_area(alerta.get("area_desc"), provincia_id, provincia, municipio, mid or None)


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


def _valor_firma(alerta: dict) -> str:
    """Magnitud normalizada (39|c, 90|km/h) para deduplicar avisos equivalentes."""
    param = (alerta.get("parametro") or "").strip()
    raw = ""
    if ";" in param:
        parts = [p.strip() for p in param.split(";") if p.strip()]
        if len(parts) >= 3:
            raw = parts[2]
    if not raw:
        raw = param or fmt_alerta_detalle(alerta)
    norm = _norm_area(raw)
    m = re.search(r"(\d+(?:[.,]\d+)?)", norm)
    if not m:
        return norm
    num = m.group(1).replace(",", ".")
    if "km" in norm:
        return f"{num}|km/h"
    if "mm" in norm:
        return f"{num}|mm"
    if re.search(r"(^| )m( |$)", norm):
        return f"{num}|m"
    if "c" in norm or "oc" in norm:
        return f"{num}|c"
    return f"{num}|"


def alerta_firma(alerta: dict) -> tuple[str, str, str, str]:
    """Clave de contenido visible: fenómeno, nivel, zona y magnitud."""
    return (
        str(alerta.get("fenomeno") or "").upper().strip(),
        str(alerta.get("level") or "amarillo").lower().strip(),
        _norm_area(alerta.get("area_desc")),
        _valor_firma(alerta),
    )


def icono_alerta(alerta: dict) -> str:
    """Icono del fenómeno; ignora marcadores inválidos (p. ej. 'x' de pruebas antiguas)."""
    fen = str(alerta.get("fenomeno") or "").upper().strip()
    if fen in PHENO_ICON:
        return PHENO_ICON[fen]
    icon = str(alerta.get("icon") or "").strip()
    if icon and icon.lower() not in {"x", "-", "—"}:
        return icon
    return "⚠️"


def deduplicar_alertas(alertas: list[dict]) -> list[dict]:
    """Un aviso por combinación única de fenómeno, nivel, zona y magnitud."""
    prioridad = {"rojo": 3, "naranja": 2, "amarillo": 1}
    ordenadas = sorted(
        alertas,
        key=lambda a: (
            -prioridad.get(str(a.get("level", "")).lower(), 0),
            bool(a.get("is_test")),
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
    try:
        with tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:*") as tg:
            for m in tg.getmembers():
                if not m.isfile() or not m.name.lower().endswith(".xml"):
                    continue
                f = tg.extractfile(m)
                if not f:
                    continue
                yield f.read()
        return
    except tarfile.ReadError:
        pass

    # Algunos endpoints CAP devuelven XML directo en lugar de tar.
    if b"<alert" in tar_bytes[:4096]:
        yield tar_bytes


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
