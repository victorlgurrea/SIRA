"""Construcción del panel geográfico: mapa, tarjetas KPI (UI Dash)."""
from __future__ import annotations

from dash import html
import plotly.graph_objects as go

from sira.infrastructure.sources.hydrology.chj import resumen_aforos
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
    EMBALSE_RADIO_LOCAL_KM,
    INCENDIO_RADIO_LOCAL_KM,
    RIESGO_METEO_HORAS,
)
from charts.figures import (
    fmt_sismo_fecha as _fmt_sismo_fecha,
    fmt_sismo_linea as _fmt_sismo_linea,
    fig_lluvia as _fig_lluvia,
    fig_mapa as _fig_mapa,
)
from geo.context import geo_resuelto
from sira.infrastructure.sources.hydrology.reservoirs import resumen_embalses
from sira.infrastructure.sources.meteo.live import _proximas_horas_desde_serie
from sira.services.mapa.panel_data import (
    alertas_meteo_fuente,
    alertas_meteo_locales,
    calcular_riesgos_panel,
    datos_mapa as _datos_mapa_svc,
    map_viewport,
    meteo_para_geo,
)
from ui.theme import C_CYAN, C_ORANGE, C_TEAL, COLORES


def datos_mapa(geo: dict, d: dict) -> dict:
    """Enriquece datos del dashboard para el mapa (usa servicio de aplicación)."""
    return _datos_mapa_svc(geo, d, geo_resolver=geo_resuelto)


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


def capas_activas(capas: list[str] | None) -> set[str]:
    return set(capas) if capas else {"sismos", "incendios", "embalses", "aforos", "aemet", "costa", "sst"}


def _sismo_mag_max(sismos: list, mag_max: float) -> dict | None:
    if not sismos:
        return None
    candidatos = [s for s in sismos if s.get("magnitud") == mag_max]
    if not candidatos:
        candidatos = sismos
    return max(candidatos, key=lambda s: (s.get("score_local", s.get("score_total", 0)), s.get("magnitud", 0)))


def _lineas_sismos(sismos: list[dict], *, limite: int = 8) -> list[str]:
    """Una línea por sismo, del más reciente al más antiguo."""
    ordenados = sorted(
        sismos,
        key=lambda s: str(s.get("timestamp") or ""),
        reverse=True,
    )
    lineas = [_fmt_sismo_linea(s, bullet=True) for s in ordenados[:limite]]
    if len(sismos) > limite:
        lineas.append(f"· … y {len(sismos) - limite} más.")
    return lineas


def _tooltip_sismos_espana(sismos_espana: list[dict]) -> str:
    n = len(sismos_espana)
    if n <= 0:
        return "Sin sismos recientes en España."
    return "\n".join([f"{n} sismo(s) recientes en España:", *_lineas_sismos(sismos_espana)])


def _tooltip_sismos_perceptibles(sismos_local: list[dict], localidad: str) -> str:
    n = len(sismos_local)
    if n <= 0:
        return f"Ningún sismo perceptible cerca de {localidad}."
    return "\n".join([
        f"{n} sismo(s) perceptible(s) cerca de {localidad}:",
        *_lineas_sismos(sismos_local),
    ])


def _ubicacion_foco(incendio: dict) -> str:
    """Municipio más cercano al centroide del foco (fallback a coords)."""
    try:
        from sira.infrastructure.geo.es import municipio_mas_cercano

        lat = float(incendio["lat"])
        lon = float(incendio["lon"])
        muni = municipio_mas_cercano(lat, lon)
        if muni and muni.get("municipio"):
            nom = str(muni["municipio"])
            prov = muni.get("provincia")
            if prov:
                return f"{nom} ({prov})"
            return nom
    except Exception:  # noqa: BLE001
        pass
    try:
        return f"{float(incendio['lat']):.2f}°N, {float(incendio['lon']):.2f}°E"
    except (TypeError, ValueError, KeyError):
        return "ubicación desconocida"


def _tooltip_incendios_local(incendios_local: list[dict], localidad: str) -> str:
    """Una línea por foco cercano: municipio próximo + hectáreas estimadas."""
    n = len(incendios_local)
    if n <= 0:
        return f"Ningún foco cerca de {localidad}."
    ordenados = sorted(
        incendios_local,
        key=lambda i: float(i.get("dist_local_km") or 1e9),
    )
    lineas = [f"{n} foco(s) cerca de {localidad}:"]
    for i in ordenados[:8]:
        ubi = _ubicacion_foco(i)
        area_km2 = float(i.get("area_km2") or 0)
        ha = area_km2 * 100.0
        if ha >= 100:
            ha_txt = f"{ha:,.0f} ha".replace(",", ".")
        else:
            ha_txt = f"{ha:.0f} ha"
        dist = i.get("dist_local_km")
        linea = f"· Cerca de {ubi} · {ha_txt}"
        if dist is not None:
            linea += f" · a {float(dist):.0f} km"
        lineas.append(linea)
    if n > 8:
        lineas.append(f"· … y {n - 8} más.")
    return "\n".join(lineas)


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
        tooltip=riesgo.get("motivo_indice")
        or "Síntesis de avisos AEMET y predicción horaria para priorizar fenómenos adversos.",
    )


def build_mapa_fig(
    geo: dict,
    d: dict,
    capas: list[str] | None = None,
    theme: str = "dark",
    map_aspect: float | None = None,
    *,
    ctx: dict | None = None,
) -> go.Figure:
    try:
        ctx = ctx or datos_mapa(geo, d)
        geo_r = ctx["geo"]
        act = capas_activas(capas)
        viewport = map_viewport(geo_r)
        map_rev = f"sira-mapa-{ctx['muni_id']}-{viewport.get('nivel', 'municipio')}"
        return _fig_mapa(
            ctx["sismos_mapa"] if "sismos" in act else [],
            ctx["incendios_mapa"] if "incendios" in act else None,
            ctx["lat_obs"], ctx["lon_obs"], ctx["localidad"],
            ctx["alertas_mapa_hoy"] if "aemet" in act else None,
            ctx["embalses_mapa"] if "embalses" in act else None,
            ctx["aforos_mapa"] if "aforos" in act else None,
            viewport=viewport, map_uirevision=map_rev,
            provincia_id=geo_r.get("provincia_id") if "aemet" in act else None,
            theme=theme,
            mostrar_tsunami="costa" in act,
            map_aspect=map_aspect,
            sst_med_grid=ctx.get("sst_med_grid") if "sst" in act else None,
            sst_cant_grid=ctx.get("sst_cant_grid") if "sst" in act else None,
            sst_atl_grid=ctx.get("sst_atl_grid") if "sst" in act else None,
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("build_mapa_fig falló")
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark" if theme != "light" else "plotly_white",
            margin=dict(l=0, r=0, t=0, b=0),
            geo=dict(showland=True, landcolor="#1e293b" if theme != "light" else "#e2e8f0"),
            annotations=[
                dict(
                    text="Mapa no disponible (reintenta en unos segundos)",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=14, color="#94a3b8"),
                )
            ],
        )
        return fig


def build_panel_geo(
    geo: dict,
    d: dict,
    capas: list[str] | None = None,
    theme: str = "dark",
    map_aspect: float | None = None,
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
    met = meteo_para_geo(muni_id, localidad, dashboard=d)
    res_met = met.get("resumen", {})
    lluvia_24 = float(res_met.get("precip_prox_24h_mm") or 0)
    res_emb = resumen_embalses(d.get("embalses", []), lat_obs, lon_obs, lluvia_24h_mm=lluvia_24)
    res_afor = resumen_aforos(d.get("aforos", []), lat_obs, lon_obs)
    alertas_meteo = alertas_meteo_locales(geo_r, alertas_meteo_fuente(d))

    mag_max = max((s["magnitud"] for s in sismos), default=0)
    sismo_max = _sismo_mag_max(sismos, mag_max)
    nivel_max = sismo_max.get("nivel_local", sismo_max.get("nivel_alerta")) if sismo_max else None
    loc_label = f"{localidad}, {geo_r.get('municipio') or ''}".strip(", ")

    riesgo_met, riesgo_local = calcular_riesgos_panel(
        alertas_meteo=alertas_meteo,
        meteo=met,
        sismos_mapa=sismos_mapa,
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
            tooltip_espana=_tooltip_sismos_espana(d.get("sismos") or []),
            tooltip_local=_tooltip_sismos_perceptibles(sismos, localidad),
        ),
        card_doble(
            "Incendios activos",
            len(d.get("incendios", [])),
            "España",
            len(incendios_local),
            f"cerca · {localidad}",
            f"NASA FIRMS · radio del foco ∝ área afectada · zona local ≤ {INCENDIO_RADIO_LOCAL_KM:.0f} km.",
            accent="#ea580c",
            tooltip_local=_tooltip_incendios_local(incendios_local, localidad),
        ),
        card(
            "Tiempo ahora",
            meteo_ahora(
                res_met,
                met.get("proximas_horas") or _proximas_horas_desde_serie(met.get("serie_horaria", []), horas=6),
                fuente=met.get("fuente"),
                alertas=alertas_meteo,
            ),
            f"Según {met.get('fuente', '—')} · {loc_label}",
            "Estado del cielo, temperatura, sensación térmica, humedad y viento en la localidad seleccionada.",
            accent=C_CYAN,
            tooltip="Observación y próximas horas para la localidad seleccionada (AEMET o Open-Meteo fallback).",
        ),
    ]
    mapa = build_mapa_fig(geo_r, d, capas, theme, map_aspect=map_aspect, ctx=ctx)
    lluvia = _fig_lluvia(met.get("serie_horaria", []), theme=theme)
    return cards, mapa, lluvia
