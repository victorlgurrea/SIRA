"""Construcción del panel geográfico: mapa, tarjetas KPI y datos enriquecidos."""
from __future__ import annotations

import requests
from dash import html
import plotly.graph_objects as go

from sira.infrastructure.sources.meteo.aemet_alerts import alerta_coincide_zona, alertas_para_dia, deduplicar_alertas
from sira.infrastructure.sources.hydrology.chj import aforos_para_mapa, resumen_aforos
from ui.components import (
    card,
    card_doble,
    card_impacto_local,
    card_lluvia,
    card_sismos_combinada,
    lluvia_embalses_valor,
    meteo_ahora,
    riesgo_meteo_panel,
)
from sira.config.settings import (
    AFORO_RADIO_LOCAL_KM,
    API_BASE_URL,
    EMBALSE_RADIO_LOCAL_KM,
    INCENDIO_RADIO_LOCAL_KM,
    RIESGO_METEO_HORAS,
    ZONA,
)
from sira.domain.costa.mapa import alertas_a_capa_costera
from charts.figures import (
    fmt_sismo_fecha as _fmt_sismo_fecha,
    fig_lluvia as _fig_lluvia,
    fig_mapa as _fig_mapa,
)
from geo.context import DEFAULT_MUNI, DEFAULT_PROV, geo_resuelto
from sira.infrastructure.geo.es import coords_observacion, provincia_de_municipio, viewport_ccaa_centro
from sira.infrastructure.sources.hydrology.reservoirs import embalses_para_mapa, resumen_embalses
from sira.infrastructure.sources.fire.firms import enriquecer_local as enriquecer_incendio_local
from sira.infrastructure.sources.meteo.live import meteo_localidad
from sira.domain.risks.local import calcular_riesgo_local
from sira.domain.risks.meteo import calcular_riesgo_meteo
from sira.domain.seismic.sismos import enriquecer_local
from sira.domain.seismic.tsunami_oficial import anexar_boletin_tsunami
from ui.theme import C_CYAN, C_GREEN, C_ORANGE, C_TEAL, COLORES


def meteo_para_geo(municipio_id: str, localidad: str | None = None) -> dict:
    """GET /api/meteo/{municipio} al cambiar zona; fallback local si la API no responde."""
    mid = str(municipio_id or DEFAULT_MUNI).zfill(5)
    params = {"localidad": localidad} if localidad else None
    try:
        r = requests.get(f"{API_BASE_URL}/api/meteo/{mid}", params=params, timeout=30)
        if r.ok:
            data = r.json()
            if isinstance(data, dict):
                return data
    except requests.RequestException:
        pass
    return meteo_localidad(mid, localidad)


def alertas_meteo_fuente(d: dict) -> list[dict]:
    """Avisos de prueba + live ya resueltos por read_dashboard/API (caché AEMET 90 s)."""
    local = list(d.get("meteo_alertas_test", [])) if isinstance(d.get("meteo_alertas_test"), list) else []
    live = list(d.get("meteo_alertas_live", [])) if isinstance(d.get("meteo_alertas_live"), list) else []
    return [*local, *live]


def alertas_meteo_locales(geo: dict, alertas: list[dict]) -> list[dict]:
    geo = geo_resuelto(geo)
    filtradas = [
        a for a in alertas
        if alerta_coincide_zona(
            a,
            provincia_id=geo.get("provincia_id"),
            municipio_id=geo.get("municipio_id"),
            provincia=geo.get("provincia"),
            municipio=geo.get("municipio"),
        )
    ]
    return deduplicar_alertas(filtradas)


def cobertura_aforos(fuentes_estado: dict | None) -> tuple[str, str]:
    fuentes = fuentes_estado if isinstance(fuentes_estado, dict) else {}
    info_chj = fuentes.get("saih_chj") if isinstance(fuentes.get("saih_chj"), dict) else {}
    info_che = fuentes.get("saih_che") if isinstance(fuentes.get("saih_che"), dict) else {}
    info_chs = fuentes.get("saih_chs") if isinstance(fuentes.get("saih_chs"), dict) else {}

    activas = []
    if info_chj.get("ok"):
        activas.append("CHJ")
    if info_che.get("ok") and int(info_che.get("registros") or 0) > 0:
        activas.append("CHE")
    if info_chs.get("ok"):
        activas.append("CHS")
    if not activas:
        activas.append("sin cobertura")

    detalle_che = ""
    msg_che = str(info_che.get("error") or "").lower()
    if "pendiente" in msg_che or "sin api" in msg_che:
        detalle_che = " · CHE sin API pública"

    return (
        "Cobertura aforos: " + ", ".join(activas) + detalle_che,
        "Cobertura de cuencas SAIH activas para aforos y caudales de la zona.",
    )


def map_viewport(geo: dict | None) -> dict:
    zoom = (geo or {}).get("map_zoom")
    if zoom and zoom.get("lat_centro") is not None:
        return zoom
    muni_id = (geo or {}).get("municipio_id") or DEFAULT_MUNI
    pid = str((geo or {}).get("provincia_id") or provincia_de_municipio(muni_id) or DEFAULT_PROV).zfill(2)
    loc_id = (geo or {}).get("localidad_id")
    lat_obs, lon_obs, _ = coords_observacion(muni_id, loc_id)
    return viewport_ccaa_centro(pid, lat_obs, lon_obs, alejado=True)


def capas_activas(capas: list[str] | None) -> set[str]:
    return set(capas) if capas else {"sismos", "incendios", "embalses", "aforos", "aemet", "costa"}


def datos_mapa(geo: dict, d: dict) -> dict:
    """Enriquece datos del dashboard para el mapa de riesgos (sin llamadas meteo)."""
    geo = geo_resuelto(geo)
    muni_id = geo.get("municipio_id") or DEFAULT_MUNI
    localidad = geo.get("localidad") or ZONA["ciudad_ref"]
    lat_obs, lon_obs, _ = coords_observacion(muni_id, geo.get("localidad_id"))

    sismos_mapa = [enriquecer_local(s, lat_obs, lon_obs) for s in d.get("sismos", [])]
    sismos_mapa = [
        anexar_boletin_tsunami(s, lat_obs, lon_obs, muni_id)
        if s.get("alerta_tsunami")
        else s
        for s in sismos_mapa
    ]
    for s in sismos_mapa:
        if s.get("alerta_tsunami") and s.get("tsunami_texto_ola"):
            s["area_desc"] = str(s["tsunami_texto_ola"])

    incendios_mapa = [enriquecer_incendio_local(i, lat_obs, lon_obs) for i in d.get("incendios", [])]
    lluvia_24 = float((d.get("meteo") or {}).get("resumen", {}).get("precip_prox_24h_mm") or 0)
    embalses_mapa = embalses_para_mapa(d.get("embalses", []), lat_obs, lon_obs, lluvia_24h_mm=lluvia_24)
    aforos_mapa = aforos_para_mapa(d.get("aforos", []), lat_obs, lon_obs)
    alertas_fuente = alertas_meteo_fuente(d)
    alertas_mapa_hoy = alertas_para_dia(alertas_fuente)
    zonas_costeras = alertas_a_capa_costera(alertas_mapa_hoy)

    return {
        "geo": geo,
        "muni_id": muni_id,
        "localidad": localidad,
        "lat_obs": lat_obs,
        "lon_obs": lon_obs,
        "sismos_mapa": sismos_mapa,
        "incendios_mapa": incendios_mapa,
        "embalses_mapa": embalses_mapa,
        "aforos_mapa": aforos_mapa,
        "alertas_mapa_hoy": alertas_mapa_hoy,
        "zonas_costeras": zonas_costeras,
    }


def _sismo_mag_max(sismos: list, mag_max: float) -> dict | None:
    if not sismos:
        return None
    candidatos = [s for s in sismos if s.get("magnitud") == mag_max]
    if not candidatos:
        candidatos = sismos
    return max(candidatos, key=lambda s: (s.get("score_local", s.get("score_total", 0)), s.get("magnitud", 0)))


def _detalle_sismo(sismo: dict | None) -> html.Div | str:
    if not sismo:
        return "Sin eventos en el periodo"
    return html.Div(className="sira-evento-info", children=[
        html.Div(_fmt_sismo_fecha(sismo.get("timestamp")), className="sira-evento-fecha"),
        html.Div(sismo.get("lugar") or "—", className="sira-evento-lugar"),
    ])


def _riesgo_meteo_card(riesgo: dict) -> html.Div:
    elementos = riesgo.get("elementos") or []
    nivel_peligro = "amarillo"
    for e in elementos:
        n = str(e.get("nivel_peligro") or "").lower()
        if n == "rojo":
            nivel_peligro = "rojo"
            break
        if n == "naranja":
            nivel_peligro = "naranja"
    accent = {"rojo": "#ef4444", "naranja": C_ORANGE, "amarillo": "#eab308"}.get(
        nivel_peligro,
        COLORES.get(riesgo.get("nivel_global", riesgo.get("nivel", "MÍNIMO")), C_ORANGE),
    )
    h = riesgo.get("horas", RIESGO_METEO_HORAS)
    return card(
        "Riesgo meteorológico adverso",
        riesgo_meteo_panel(riesgo),
        riesgo.get("texto") or "",
        f"AEMET Meteoalerta + predicción horaria ({h} h).",
        accent=accent,
        tooltip="Síntesis de avisos AEMET y predicción horaria para priorizar fenómenos adversos.",
    )


def build_mapa_fig(geo: dict, d: dict, capas: list[str] | None = None, theme: str = "dark") -> go.Figure:
    ctx = datos_mapa(geo, d)
    geo_r = ctx["geo"]
    act = capas_activas(capas)
    viewport = map_viewport(geo_r)
    map_rev = f"sira-mapa-{ctx['muni_id']}-{viewport.get('nivel', 'municipio')}"
    return _fig_mapa(
        ctx["sismos_mapa"] if "sismos" in act else [],
        ctx["incendios_mapa"] if "incendios" in act else None,
        ctx["lat_obs"], ctx["lon_obs"], ctx["localidad"],
        ctx["zonas_costeras"] if "costa" in act else None,
        ctx["alertas_mapa_hoy"] if "aemet" in act else None,
        ctx["embalses_mapa"] if "embalses" in act else None,
        ctx["aforos_mapa"] if "aforos" in act else None,
        viewport=viewport, map_uirevision=map_rev,
        provincia_id=geo_r.get("provincia_id") if "aemet" in act else None,
        theme=theme,
    )


def build_panel_geo(
    geo: dict, d: dict, capas: list[str] | None = None, theme: str = "dark",
) -> tuple[list, go.Figure, go.Figure]:
    """Tarjetas, mapa y lluvia según la zona seleccionada."""
    ctx = datos_mapa(geo, d)
    geo_r = ctx["geo"]
    muni_id = ctx["muni_id"]
    localidad = ctx["localidad"]
    lat_obs, lon_obs = ctx["lat_obs"], ctx["lon_obs"]
    sismos_mapa = ctx["sismos_mapa"]
    incendios_mapa = ctx["incendios_mapa"]

    sismos = [s for s in sismos_mapa if s.get("perceptible_local")]
    incendios_local = [i for i in incendios_mapa if i.get("cerca_local")]
    met = meteo_para_geo(muni_id, localidad)
    res_met = met.get("resumen", {})
    lluvia_24 = float(res_met.get("precip_prox_24h_mm") or 0)
    res_emb = resumen_embalses(d.get("embalses", []), lat_obs, lon_obs, lluvia_24h_mm=lluvia_24)
    res_afor = resumen_aforos(d.get("aforos", []), lat_obs, lon_obs)
    alertas_meteo = alertas_meteo_locales(geo_r, alertas_meteo_fuente(d))

    mag_max = max((s["magnitud"] for s in sismos), default=0)
    sismo_max = _sismo_mag_max(sismos, mag_max)
    nivel_max = sismo_max.get("nivel_local", sismo_max.get("nivel_alerta")) if sismo_max else None
    loc_label = f"{localidad}, {geo_r.get('municipio') or ''}".strip(", ")

    riesgo_met = calcular_riesgo_meteo(alertas_meteo, met, horas=RIESGO_METEO_HORAS)
    riesgo_local = calcular_riesgo_local(
        alertas_meteo=alertas_meteo,
        meteo=met,
        sismos=sismos_mapa,
        incendios_local=incendios_local,
        resumen_embalses=res_emb,
        resumen_aforos=res_afor,
        termico_ccaa=d.get("termico_ccaa"),
        provincia_id=geo_r.get("provincia_id"),
        horas_meteo=RIESGO_METEO_HORAS,
    )
    cobertura_txt, tooltip_aforos = cobertura_aforos(d.get("fuentes_estado"))

    cards = [
        card_impacto_local(riesgo_local),
        _riesgo_meteo_card(riesgo_met),
        card_lluvia(
            lluvia_embalses_valor(res_met.get("precip_prox_24h_mm", "—"), res_emb, res_afor),
            f"Prob. máx. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}",
            f"{loc_label} · {cobertura_txt} · embalses {EMBALSE_RADIO_LOCAL_KM:.0f} km · aforos {AFORO_RADIO_LOCAL_KM:.0f} km",
            accent=C_TEAL,
            tooltip=tooltip_aforos,
        ),
        card_sismos_combinada(
            len(d.get("sismos", [])),
            len(sismos),
            localidad,
            float(mag_max),
            nivel_max,
            _detalle_sismo(sismo_max),
            "",
            accent=C_ORANGE,
            tooltip="Eventos sísmicos recientes en España y perceptibilidad local respecto a la localidad seleccionada.",
        ),
        card_doble(
            "Incendios activos",
            len(d.get("incendios", [])),
            "España",
            len(incendios_local),
            f"cerca · {localidad}",
            f"NASA FIRMS · radio del foco ∝ área afectada · zona local ≤ {INCENDIO_RADIO_LOCAL_KM:.0f} km.",
            accent="#ea580c",
            tooltip="Focos térmicos satelitales (NASA FIRMS) con recuento nacional y proximidad local.",
        ),
        card(
            "Tiempo ahora",
            meteo_ahora(
                res_met,
                met.get("proximas_horas", []),
                fuente=met.get("fuente"),
                alertas=alertas_meteo,
            ),
            f"Según {met.get('fuente', '—')} · {loc_label}",
            "Estado del cielo, temperatura, sensación térmica, humedad y viento en la localidad seleccionada.",
            accent=C_CYAN,
            tooltip="Observación y próximas horas para la localidad seleccionada (AEMET o Open-Meteo fallback).",
        ),
    ]
    mapa = build_mapa_fig(geo_r, d, capas, theme)
    lluvia = _fig_lluvia(met.get("serie_horaria", []), theme=theme)
    return cards, mapa, lluvia
