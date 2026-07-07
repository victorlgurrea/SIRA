"""Avisos AEMET CAP: parseo genérico (toda España) y coincidencia por zona."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from aemet_alerts import (  # noqa: E402
    alerta_coincide_zona,
    meteo_push_key,
    parse_cap_xml,
    texto_push_meteo,
)


def _cap_xml(*, area_desc: str, fenomeno: str = "FF;AT", nivel: str = "rojo", param: str = "TA;Temperatura maxima;42 C") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>TEST-{area_desc[:12]}</identifier>
  <msgType>Alert</msgType>
  <info>
    <language>es-ES</language>
    <severity>Extreme</severity>
    <headline>Aviso rojo por temperaturas maximas</headline>
    <onset>2020-01-01T00:00:00+00:00</onset>
    <expires>2099-12-31T23:59:59+00:00</expires>
    <eventCode><valueName>AEMET-Meteoalerta fenomeno</valueName><value>{fenomeno}</value></eventCode>
    <eventCode><valueName>AEMET-Meteoalerta nivel</valueName><value>{nivel}</value></eventCode>
    <eventCode><valueName>AEMET-Meteoalerta parametro</valueName><value>{param}</value></eventCode>
    <eventCode><valueName>AEMET-Meteoalerta probabilidad</valueName><value>40%-70%</value></eventCode>
    <area>
      <areaDesc>{area_desc}</areaDesc>
      <eventCode><valueName>AEMET-Meteoalerta zona</valueName><value>999999</value></eventCode>
    </area>
  </info>
</alert>
""".encode()


def test_parse_cap_ff_at_temperatura_maxima():
    avisos = parse_cap_xml(_cap_xml(area_desc="Litoral sur de Valencia-Valencia/Valencia"))
    assert len(avisos) == 1
    a = avisos[0]
    assert a["fenomeno"] == "AT"
    assert a["fenomeno_desc"] == "temperatura máxima"
    assert a["level"] == "rojo"


def test_parse_cap_at_prefijo_aemet_real():
    xml = _cap_xml(area_desc="Litoral norte de Valencia", fenomeno="AT;Temperaturas máximas", nivel="").replace(
        b"<severity>Extreme</severity>",
        b"<severity>Severe</severity>",
    )
    avisos = parse_cap_xml(xml)
    assert len(avisos) == 1
    assert avisos[0]["fenomeno"] == "AT"
    assert avisos[0]["level"] == "naranja"


def test_coincide_formato_aemet_web_valencia():
    aviso = parse_cap_xml(_cap_xml(area_desc="Litoral sur de Valencia-Valencia/Valencia"))[0]
    assert alerta_coincide_zona(aviso, provincia_id="46", municipio_id="46250", provincia="Valencia/Valencia")


def test_coincide_toledo_no_valencia():
    aviso = parse_cap_xml(_cap_xml(area_desc="Interior de Toledo-Toledo"))[0]
    assert alerta_coincide_zona(aviso, provincia_id="45", provincia="Toledo")
    assert not alerta_coincide_zona(aviso, provincia_id="46", provincia="Valencia/Valencia")


def test_coincide_guadalajara():
    aviso = parse_cap_xml(_cap_xml(area_desc="Sistema Central de Guadalajara-Guadalajara", nivel="naranja"))[0]
    assert alerta_coincide_zona(aviso, provincia_id="19", provincia="Guadalajara")
    assert not alerta_coincide_zona(aviso, provincia_id="45", provincia="Toledo")


def test_leon_no_confunde_castellon():
    aviso = parse_cap_xml(_cap_xml(area_desc="Interior sur de Castellon-Castello/Castellon"))[0]
    assert alerta_coincide_zona(aviso, provincia_id="12", provincia="Castellon/Castello")
    assert not alerta_coincide_zona(aviso, provincia_id="24", provincia="Leon")


def test_parse_cap_otros_fenomenos_espana():
    lluvia = parse_cap_xml(_cap_xml(area_desc="Sierra norte de Madrid-Madrid", fenomeno="FF;PR", param="P1;Precipitacion 1h;30 mm"))[0]
    assert lluvia["fenomeno"] == "PR"
    viento = parse_cap_xml(_cap_xml(area_desc="Litoral de Cadiz-Cadiz", fenomeno="FF;VI", param="RM;Racha maxima;90 km/h"))[0]
    assert viento["fenomeno"] == "VI"


def test_texto_push_meteo_generico():
    aviso = parse_cap_xml(_cap_xml(area_desc="Interior de Toledo-Toledo"))[0]
    title, body = texto_push_meteo(aviso)
    assert "Aviso meteorológico" in title
    assert "ROJO" in title


def test_meteo_push_key_cambia_si_sube_nivel():
    base = parse_cap_xml(_cap_xml(area_desc="Interior de Guadalajara-Guadalajara"))[0]
    naranja = {**base, "level": "naranja"}
    assert meteo_push_key(base) != meteo_push_key(naranja)
