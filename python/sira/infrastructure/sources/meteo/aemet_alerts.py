"""Avisos AEMET Meteoalerta (CAP) para notificaciones locales."""
from __future__ import annotations

import re
import tarfile
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from sira.config.settings import AEMET_ALERT_PHENOMENA, AEMET_CAP_FORECAST_HOURS, AEMET_PUSH_MIN_LEVEL, HTTP_TIMEOUT
from sira.infrastructure.http.client import fetch_aemet_bytes, fetch_bytes, fetch_text

import logging

log = logging.getLogger(__name__)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
AEMET_ATOM_ESP = "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAE_ATOM.xml"

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
from sira.domain.risks.presentacion import (  # noqa: E402
    PHENO_ICON,
    fmt_alerta_detalle,
    icono_alerta,
)


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


def _palabras_area(area_norm: str) -> set[str]:
    return {w for w in re.split(r"[\s\-/]+", area_norm) if w}


def _token_en_area(token: str, area_norm: str) -> bool:
    """Coincidencia por palabra o frase completa (válido en toda España)."""
    if not token or not area_norm:
        return False
    if " " in token:
        return token in area_norm
    if len(token) < 4:
        return token in _palabras_area(area_norm)
    if token in _palabras_area(area_norm):
        return True
    return bool(re.search(rf"(^|[\s\-/]){re.escape(token)}([\s\-/]|$)", area_norm))


def _misma_provincia(municipio_a: str | None, municipio_b: str | None) -> bool:
    if not municipio_a or not municipio_b:
        return False
    from sira.infrastructure.geo.es import provincia_de_municipio

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
    """¿El aviso CAP afecta a la provincia/municipio de la suscripción?

    AEMET usa areaDesc como «Interior de Toledo-Toledo» o
    «Litoral sur de Valencia-València/Valencia» (comarca + provincia).
    El criterio es el mismo en cualquier CCAA (Toledo, Guadalajara, etc.).
    """
    area = _norm_area(area_desc)
    if not area:
        return False

    candidatos: list[str] = []
    candidatos.extend(_nombre_tokens(provincia))
    if provincia_id:
        from sira.infrastructure.geo.es import provincias

        pname = next(
            (p.get("nombre") for p in provincias() if str(p.get("id")) == str(provincia_id).zfill(2)),
            "",
        )
        candidatos.extend(_nombre_tokens(pname))
    for token in candidatos:
        if _token_en_area(token, area):
            return True

    for token in _nombre_tokens(municipio):
        if _token_en_area(token, area):
            return True
    if municipio_ref:
        from sira.infrastructure.geo.es import municipio_por_id

        muni = municipio_por_id(str(municipio_ref).zfill(5))
        if muni:
            token = _norm_area(muni.get("nombre"))
            if token and _token_en_area(token, area):
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
        from sira.infrastructure.geo.es import provincia_de_municipio

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


def meteo_push_key(alerta: dict) -> str:
    """Clave estable para push: cambia si sube nivel, zona o magnitud del aviso."""
    return "|".join(alerta_firma(alerta))


_NIVEL_AEMET_LABEL = {"amarillo": "AMARILLO", "naranja": "NARANJA", "rojo": "ROJO", "verde": "VERDE"}


def texto_push_meteo(alerta: dict) -> tuple[str, str]:
    """Título y cuerpo del push para un aviso AEMET CAP."""
    level = str(alerta.get("level", "amarillo")).lower()
    nivel_aemet = _NIVEL_AEMET_LABEL.get(level, level.upper())
    fen = str(alerta.get("fenomeno_desc") or "fenómeno adverso").strip()
    zona = (alerta.get("area_desc") or "tu zona").strip()
    detalle = fmt_alerta_detalle(alerta)
    headline = (alerta.get("headline") or "").strip()

    title = f"SIRA · Aviso meteorológico {nivel_aemet}"
    if headline:
        body = headline
    else:
        body = f"{fen.capitalize()} · {zona}"
    if detalle and detalle != "Sin detalle" and detalle not in body:
        body = f"{body} · {detalle}"
    if "AEMET" not in body.upper():
        body = f"AEMET {level.upper()} · {body}"
    return title, body


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


def _codigo_fenomeno_aemet(raw: str | None) -> str:
    """CAP AEMET: «FF;AT» o «AT;Temperaturas máximas» → AT."""
    if not raw:
        return ""
    parts = [p.strip() for p in str(raw).split(";") if p.strip()]
    if not parts:
        return ""
    head = parts[0].upper()
    if head in PHENO_LABEL:
        return head
    if head == "FF" and len(parts) >= 2:
        code = parts[1].upper()
        return code if code in PHENO_LABEL else code
    return parts[-1].upper()


def _extract_aemet(info: ET.Element, area: ET.Element) -> dict:
    level = _event_code(info, "AEMET-Meteoalerta nivel") or ""
    pheno_raw = _event_code(info, "AEMET-Meteoalerta fenomeno") or ""
    param_raw = _event_code(info, "AEMET-Meteoalerta parametro") or ""
    prob_raw = _event_code(info, "AEMET-Meteoalerta probabilidad") or ""
    zona = _event_code(area, "AEMET-Meteoalerta zona") or ""
    pheno = _codigo_fenomeno_aemet(pheno_raw)
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


def alerta_intersecta_dia(alerta: dict, dia: date | None = None) -> bool:
    """True si el aviso CAP afecta al menos un instante del día civil (Europe/Madrid)."""
    from zoneinfo import ZoneInfo

    madrid = ZoneInfo("Europe/Madrid")
    dia = dia or datetime.now(madrid).date()
    ini = _parse_iso(alerta.get("onset"))
    fin = _parse_iso(alerta.get("expires"))
    start = datetime.combine(dia, datetime.min.time(), tzinfo=madrid)
    end = start + timedelta(days=1)
    if fin is not None and fin <= start:
        return False
    if ini is not None and ini >= end:
        return False
    return True


def alertas_para_dia(alertas: list[dict], dia: date | None = None) -> list[dict]:
    """Filtra avisos que aplican a un día concreto (por defecto, hoy en Madrid)."""
    return [a for a in alertas if isinstance(a, dict) and alerta_intersecta_dia(a, dia)]


def _is_active(onset: str | None, expires: str | None) -> bool:
    """Aviso inmediato para push: ventana corta antes del onset."""
    now = datetime.now(timezone.utc)
    d_on = _parse_iso(onset)
    d_ex = _parse_iso(expires)
    # AEMET distribuye avisos CAP a veces antes del "onset" real.
    # Para que SIRA pueda notificar cuando la alerta ya está anunciada,
    # aceptamos avisos cuyo onset ocurra dentro de una ventana de gracia.
    grace = timedelta(hours=3)
    if d_ex and now >= d_ex:
        return False
    if d_on and d_on > now + grace:
        return False
    return True


def _cap_vigente(onset: str | None, expires: str | None) -> bool:
    """Aviso vigente para mapa/dashboard: incluye predicción Meteoalerta (hasta 72 h)."""
    now = datetime.now(timezone.utc)
    d_ex = _parse_iso(expires)
    if d_ex and now >= d_ex:
        return False
    d_on = _parse_iso(onset)
    if d_on and d_on > now + timedelta(hours=max(1, int(AEMET_CAP_FORECAST_HOURS))):
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


def _alertas_desde_cap_root(
    root: ET.Element,
    *,
    vigente_fn=_cap_vigente,
) -> list[dict]:
    msg_type = (root.findtext("cap:msgType", default="", namespaces=CAP_NS) or "").lower()
    if msg_type == "cancel":
        return []
    info = _pick_info(root)
    if info is None:
        return []
    onset = info.findtext("cap:onset", default="", namespaces=CAP_NS)
    expires = info.findtext("cap:expires", default="", namespaces=CAP_NS)
    if not vigente_fn(onset, expires):
        return []
    severity = info.findtext("cap:severity", default="", namespaces=CAP_NS)
    headline = info.findtext("cap:headline", default="", namespaces=CAP_NS) or ""
    description = info.findtext("cap:description", default="", namespaces=CAP_NS) or ""
    urgency = info.findtext("cap:urgency", default="", namespaces=CAP_NS) or ""
    certainty = info.findtext("cap:certainty", default="", namespaces=CAP_NS) or ""
    identifier = root.findtext("cap:identifier", default="", namespaces=CAP_NS) or ""

    out: list[dict] = []
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


def parse_cap_xml(xml_bytes: bytes, *, vigente_fn=_cap_vigente) -> list[dict]:
    """Parsea un mensaje CAP AEMET (XML) en avisos normalizados."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    return _alertas_desde_cap_root(root, vigente_fn=vigente_fn)


def _alertas_desde_tar(raw: bytes, vigente_fn) -> list[dict]:
    out: list[dict] = []
    for xml_bytes in _iter_cap_members(raw):
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            continue
        out.extend(_alertas_desde_cap_root(root, vigente_fn=vigente_fn))
    return out


def _tar_url_desde_atom(atom_xml: bytes) -> str | None:
    """Primera entrada Atom = tar.gz con el estado completo de avisos."""
    try:
        root = ET.fromstring(atom_xml)
    except ET.ParseError:
        return None
    for entry in root.findall("atom:entry", ATOM_NS):
        link = entry.find("atom:link", ATOM_NS)
        href = (link.get("href") if link is not None else "") or ""
        if href.lower().endswith(".tar.gz"):
            return href
        # Algunas entradas usan <link>texto</link> sin href
        if link is not None and not href and (link.text or "").lower().endswith(".tar.gz"):
            return str(link.text).strip()
    return None


def _fetch_cap_opendata(aemet_api_key: str, vigente_fn) -> list[dict]:
    if not aemet_api_key:
        raise ValueError("AEMET_API_KEY no configurada")
    raw = fetch_aemet_bytes("avisos_cap/ultimoelaborado/area/esp", aemet_api_key, timeout=max(45, HTTP_TIMEOUT))
    return _alertas_desde_tar(raw, vigente_fn)


def _fetch_cap_atom(vigente_fn) -> list[dict]:
    """Fallback público: Atom AEMET → tar.gz CAP (sin API key)."""
    atom_xml = fetch_text(AEMET_ATOM_ESP).encode("utf-8")
    tar_url = _tar_url_desde_atom(atom_xml)
    if not tar_url:
        raise ValueError("Atom AEMET sin enlace tar.gz de avisos")
    raw = fetch_bytes(tar_url, timeout=max(45, HTTP_TIMEOUT))
    return _alertas_desde_tar(raw, vigente_fn)


def _fetch_cap_alerts(aemet_api_key: str | None, vigente_fn) -> list[dict]:
    """OpenData CAP; si falla (404/429/etc.), Atom público de AEMET."""
    errors: list[str] = []
    if aemet_api_key:
        try:
            out = _fetch_cap_opendata(aemet_api_key, vigente_fn)
            if out:
                return out
            errors.append("OpenData CAP vacío")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"OpenData: {exc}")
            log.warning("AEMET OpenData CAP falló, intento Atom: %s", exc)
    else:
        errors.append("sin AEMET_API_KEY")
    try:
        out = _fetch_cap_atom(vigente_fn)
        if out:
            return out
        errors.append("Atom CAP vacío")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Atom: {exc}")
        log.warning("AEMET Atom CAP falló: %s", exc)
    raise RuntimeError("No se pudieron obtener avisos CAP (" + "; ".join(errors) + ")")


def fetch_vigentes_alerts(aemet_api_key: str | None = None) -> list[dict]:
    """Avisos CAP vigentes para mapa/dashboard (predicción hasta 72 h)."""
    return _fetch_cap_alerts(aemet_api_key, _cap_vigente)


def fetch_active_alerts(aemet_api_key: str | None = None) -> list[dict]:
    """Avisos CAP inmediatos para notificaciones push (onset ≤ 3 h)."""
    return _fetch_cap_alerts(aemet_api_key, _is_active)
