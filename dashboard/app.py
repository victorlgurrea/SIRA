"""Dashboard SIRA."""
from __future__ import annotations

import _bootstrap  # noqa: F401

from datetime import datetime, timezone
import json
from pathlib import Path
import re

import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, State, callback, clientside_callback, ctx, dcc, html
from flask import jsonify, send_from_directory
from dash.exceptions import PreventUpdate

from components import bloque, card, card_doble, card_lluvia, card_sismos_combinada, lluvia_embalses_valor, meteo_ahora, riesgo_meteo_panel
from config import (  # noqa: E402
    AEMET_MUNICIPIO,
    ALLOW_DATA_REFRESH,
    API_BASE_URL,
    API_KEY,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_REFRESH_MS,
    DASHBOARD_REFRESH_MIN,
    DATA_FILE,
    AFORO_RADIO_LOCAL_KM,
    EMBALSE_RADIO_LOCAL_KM,
    FORECAST_DAYS,
    INCENDIO_RADIO_LOCAL_KM,
    INGESTA_INTERVAL_MIN,
    MARES,
    RIESGO_METEO_HORAS,
    ZONA,
)
from db import count_subscriptions, get_historial_municipio
from core import fmt_ingesta_local, read_dashboard  # noqa: E402
from geo_es import (
    coords_observacion,
    localidades,
    municipio_por_id,
    municipios,
    opciones,
    provincia_de_municipio,
    provincias,
    viewport_ccaa_centro,
)
from geo_ui import selector_geo
from meteo_live import meteo_localidad
from aemet_alerts import alerta_coincide_zona, alerta_firma, alertas_para_dia, deduplicar_alertas
from costa_mapa import alertas_a_capa_costera
from sismos import enriquecer_local
from incendios import enriquecer_local as enriquecer_incendio_local
from hidrologia import embalses_para_mapa, resumen_embalses
from aforos import aforos_para_mapa, resumen_aforos
from tsunami_oficial import anexar_boletin_tsunami
from riesgo_meteo import calcular_riesgo_meteo
from theme import (
    C_CYAN,
    C_GREEN,
    C_ORANGE,
    C_TEAL,
    COLORES,
)

from figures import (
    fmt_sismo_fecha as _fmt_sismo_fecha,
    fig_mapa as _fig_mapa,
    fig_corrientes as _fig_corrientes,
    fig_linea as _fig_linea,
    fig_historial as _fig_historial_impl,
    fig_lluvia as _fig_lluvia,
    fig_termico_ccaa as _fig_termico_ccaa,
)

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_FILE = _ASSETS / "logo-sira_4.png"
if not _LOGO_FILE.is_file():
    raise SystemExit(f"Falta el logo: {_LOGO_FILE}")

app = Dash(
    __name__,
    title="SIRA — Sistema Ibérico de Riesgos y Alerta",
    assets_folder=str(_ASSETS),
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="/assets/sira.css?v=32">
        <link rel="icon" href="/assets/logo-sira_4.png?v=8" type="image/png">
        <link rel="manifest" href="/manifest.webmanifest">
        <script src="/assets/geo.js"></script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

_LOGO = app.get_asset_url("logo-sira_4.png") + "?v=8"

_DEFAULT_MUNI = str(AEMET_MUNICIPIO).zfill(5)
_DEFAULT_PROV = provincia_de_municipio(_DEFAULT_MUNI) or "46"
_locs = localidades(_DEFAULT_MUNI)
_DEFAULT_LOC = _locs[0]["id"] if _locs else _DEFAULT_MUNI

_AYUDA_OCE_PREVISION = f"Previsión horaria · {FORECAST_DAYS} días · Open-Meteo Marine"


def _default_geo() -> dict:
    muni = municipio_por_id(_DEFAULT_MUNI)
    prov = next((p for p in provincias() if p["id"] == _DEFAULT_PROV), None)
    loc = _locs[0] if _locs else None
    lat_obs, lon_obs, _ = coords_observacion(_DEFAULT_MUNI, loc["id"] if loc else None)
    return {
        "provincia_id": _DEFAULT_PROV,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": _DEFAULT_MUNI,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": loc["id"] if loc else None,
        "localidad": loc["nombre"] if loc else None,
        "map_zoom": viewport_ccaa_centro(_DEFAULT_PROV, lat_obs, lon_obs, alejado=True),
    }


def _geo_resuelto(geo: dict | None) -> dict:
    """Geo efectiva del panel: nombres siempre coherentes con los IDs."""
    if not geo:
        return _default_geo()

    muni_id = str(geo.get("municipio_id") or _DEFAULT_MUNI).zfill(5)
    muni = municipio_por_id(muni_id)
    pid = str(geo.get("provincia_id") or provincia_de_municipio(muni_id) or _DEFAULT_PROV).zfill(2)
    prov = next((p for p in provincias() if p["id"] == pid), None)
    locs = localidades(muni_id)
    loc_id = geo.get("localidad_id")
    loc = next((l for l in locs if l["id"] == loc_id), locs[0] if locs else None)

    out = {
        "provincia_id": pid,
        "provincia": prov["nombre"] if prov else geo.get("provincia"),
        "municipio_id": muni_id,
        "municipio": muni["nombre"] if muni else geo.get("municipio"),
        "localidad_id": loc["id"] if loc else geo.get("localidad_id"),
        "localidad": loc["nombre"] if loc else geo.get("localidad"),
    }
    zoom = geo.get("map_zoom")
    if zoom:
        out["map_zoom"] = zoom
    else:
        lat_obs, lon_obs, _ = coords_observacion(muni_id, out.get("localidad_id"))
        out["map_zoom"] = viewport_ccaa_centro(pid, lat_obs, lon_obs, alejado=True)
    return out

_BTN_CLASS = "sira-btn-refresh" + ("" if ALLOW_DATA_REFRESH else " sira-btn-refresh--hidden")

app.layout = html.Div(className="sira-page", children=[
    dcc.Location(id="url", refresh=False),
    html.Div(id="sira-meta", **{"data-api-base": API_BASE_URL}, style={"display": "none"}),
    html.Div(id="push-geo", style={"display": "none"}),
    html.Header(className="sira-header", children=[
        html.Div(className="sira-header-inner", children=[
            html.Div(className="sira-header-text", children=[
                html.H1("SIRA", className="sira-title"),
                html.P("Sistema Ibérico de Riesgos y Alerta", className="sira-subtitle"),
            ]),
            html.Img(
                src=_LOGO,
                className="sira-logo",
                alt="SIRA — Sistema Ibérico de Riesgos y Alerta",
            ),
        ]),
    ]),
    html.Main(className="sira-main", children=[
        html.Div(className="sira-container", children=[
            dcc.Interval(id="tick", interval=DASHBOARD_REFRESH_MS, n_intervals=0),
            dcc.Store(id="data-ts-store"),
            dcc.Store(id="geo-store", data=_default_geo()),
            dcc.Interval(id="geo-locate-poll", interval=500, n_intervals=0, disabled=True, max_intervals=60),
            html.Div(id="geo-locate-pending", style={"display": "none"}),
            selector_geo(_DEFAULT_PROV, _DEFAULT_MUNI, _DEFAULT_LOC),
            html.Div(id="page-home", children=[
                html.Div(className="sira-toolbar", children=[
                    html.Div(className="sira-ts-wrap", children=[
                        html.Span("Última ingesta: ", className="sira-ts-label"),
                        html.Span(id="ts", className="sira-ts"),
                        html.Span("Hora local", className="sira-ts-badge"),
                        html.Span(
                            f" · pantalla cada {DASHBOARD_REFRESH_MIN} min · datos cada {INGESTA_INTERVAL_MIN} min",
                            className="sira-ts-hint",
                        ),
                    ]),
                    html.Div(className="sira-toolbar-actions", children=[
                        html.A("Historial 30 días", href="/historial", className="sira-link-nav"),
                        html.A("Estado", href="/status", className="sira-link-nav"),
                        html.Button("Actualizar", id="btn", n_clicks=0, className=_BTN_CLASS),
                        html.Button("Activar notificaciones", id="push-btn", n_clicks=0, className="sira-btn-push"),
                        html.Span("Push: desactivado", id="push-status", className="sira-push-status"),
                        dcc.Checklist(
                            id="push-prefs",
                            options=[
                                {"label": "Sismos", "value": "sismo"},
                                {"label": "Meteo", "value": "meteo"},
                                {"label": "Incendios", "value": "incendio"},
                                {"label": "Tsunami", "value": "tsunami"},
                            ],
                            value=["sismo", "meteo", "incendio", "tsunami"],
                            inline=True,
                            className="sira-push-prefs",
                        ),
                    ]),
                ]),
                html.Div(id="cards", className="sira-cards", children=[
                    card_lluvia("—", "Cargando previsión…", "", accent=C_TEAL),
                ]),
                html.Div(className="sira-charts", children=[
                html.Div(className="sira-charts-row sira-charts-row--map-full", children=[
                    html.Div(className="sira-map-layers", children=[
                        dcc.Checklist(
                            id="map-layers",
                            options=[
                                {"label": "Sismos", "value": "sismos"},
                                {"label": "Incendios", "value": "incendios"},
                                {"label": "Embalses", "value": "embalses"},
                                {"label": "Aforos", "value": "aforos"},
                                {"label": "Avisos AEMET", "value": "aemet"},
                                {"label": "Costa/Tsunami", "value": "costa"},
                            ],
                            value=["sismos", "incendios", "embalses", "aforos", "aemet", "costa"],
                            inline=True,
                            className="sira-layer-checklist",
                        ),
                    ]),
                    bloque(
                        "mapa", "Mapa de riesgos — España",
                        "Avisos AEMET por zona · sismos, incendios, embalses y aforos según la localidad seleccionada.",
                        map_chart=True, accent=C_ORANGE,
                    ),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--historial", children=[
                    bloque(
                        "termico_ccaa", "Mapa térmico — CCAA seleccionada",
                        "Temperatura máxima prevista 24 h por provincia (precalculado en ingesta).",
                        map_chart=True, accent=C_ORANGE,
                    ),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--3", children=[
                    bloque(
                        "sst_med", "Previsión SST — Mediterráneo",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['MEDITERRÁNEO']['punto']}.",
                        accent=C_ORANGE,
                    ),
                    bloque(
                        "sst_cant", "Previsión SST — Cantábrico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['CANTÁBRICO']['punto']}.",
                        accent=C_GREEN,
                    ),
                    bloque(
                        "sst_atl", "Previsión SST — Atlántico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['ATLÁNTICO']['punto']}.",
                        accent=C_CYAN,
                    ),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--3", children=[
                    bloque(
                        "cor_med", "Previsión corrientes — Mediterráneo",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['MEDITERRÁNEO']['punto']}.",
                        accent=C_ORANGE,
                    ),
                    bloque(
                        "cor_cant", "Previsión corrientes — Cantábrico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['CANTÁBRICO']['punto']}.",
                        accent=C_GREEN,
                    ),
                    bloque(
                        "cor_atl", "Previsión corrientes — Atlántico",
                        f"{_AYUDA_OCE_PREVISION} · {MARES['ATLÁNTICO']['punto']}.",
                        accent=C_CYAN,
                    ),
                ]),
            ]),
            ]),
            html.Div(id="page-historial", style={"display": "none"}, children=[
                html.Div(className="sira-historial-nav", children=[
                    html.A("← Volver al dashboard", href="/", className="sira-link-nav"),
                    html.A("Estado del sistema", href="/status", className="sira-link-nav"),
                ]),
                html.Div(className="sira-charts-row sira-charts-row--historial", children=[
                    bloque(
                        "historial", "Evolución 30 días — municipio seleccionado",
                        "Score sísmico máximo diario e índice de riesgo meteorológico.",
                        accent=C_CYAN,
                    ),
                ]),
            ]),
        ]),
    ]),
    html.Footer(className="sira-footer", children=[
        html.P("© 2026 SIRA — Sistema Ibérico de Riesgos y Alerta. Todos los derechos reservados."),
    ]),
])


def _load() -> dict:
    try:
        r = requests.get(f"{API_BASE_URL}/api/dashboard", timeout=30)
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return read_dashboard()


def _meteo_para_geo(municipio_id: str, localidad: str | None = None) -> dict:
    """GET /api/meteo/{municipio} al cambiar zona; fallback local si la API no responde."""
    mid = str(municipio_id or _DEFAULT_MUNI).zfill(5)
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


def _bloque_oce(oce: dict, clave: str) -> dict:
    bloque = oce.get(clave)
    if isinstance(bloque, dict) and bloque.get("serie_horaria") is not None:
        return bloque
    if clave == "MEDITERRÁNEO" and oce.get("serie_horaria") is not None:
        return oce
    return {"serie_horaria": [], "resumen": {}}


def _alertas_meteo_fuente(d: dict) -> list[dict]:
    """Avisos de prueba + live ya resueltos por read_dashboard/API (caché AEMET 90 s)."""
    local = list(d.get("meteo_alertas_test", [])) if isinstance(d.get("meteo_alertas_test"), list) else []
    live = list(d.get("meteo_alertas_live", [])) if isinstance(d.get("meteo_alertas_live"), list) else []
    return [*local, *live]


def _alertas_meteo_locales(geo: dict, alertas: list[dict]) -> list[dict]:
    geo = _geo_resuelto(geo)
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


def _data_refresh_token(d: dict, alertas: list[dict] | None = None) -> str:
    src = alertas if alertas is not None else _alertas_meteo_fuente(d)
    firmas = sorted(
        "|".join(alerta_firma(a))
        for a in src
        if isinstance(a, dict)
    )
    costa_sig = "|".join(
        f"{r['lat']:.2f},{r['lon']:.2f},{r['radio_tsunami_km']}"
        for r in alertas_a_capa_costera(src)
    )
    return (
        f"{d.get('generado_en', '—')}|{len(d.get('sismos', []))}|{len(d.get('incendios', []))}|{len(d.get('embalses', []))}|{len(d.get('aforos', []))}"
        f"|{'|'.join(firmas)}|{bool(d.get('sismo_prueba_activo'))}|prueba:{d.get('sismos_prueba_activos', 0)}|costa:{costa_sig}"
    )


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
    )


def _map_viewport(geo: dict | None) -> dict:
    zoom = (geo or {}).get("map_zoom")
    if zoom and zoom.get("lat_centro") is not None:
        return zoom
    muni_id = (geo or {}).get("municipio_id") or _DEFAULT_MUNI
    pid = str((geo or {}).get("provincia_id") or provincia_de_municipio(muni_id) or _DEFAULT_PROV).zfill(2)
    loc_id = (geo or {}).get("localidad_id")
    lat_obs, lon_obs, _ = coords_observacion(muni_id, loc_id)
    return viewport_ccaa_centro(pid, lat_obs, lon_obs, alejado=True)


def _fig_historial(municipio_id: str | None, uirev: str) -> go.Figure:
    return _fig_historial_impl(municipio_id, _DEFAULT_MUNI, uirev)


@callback(
    Output("geo-municipio", "options"),
    Output("geo-municipio", "value"),
    Input("geo-provincia", "value"),
    State("geo-municipio", "value"),
)
def on_provincia(provincia_id, current_muni):
    if not provincia_id:
        return opciones([], "Municipio"), None
    munis = municipios(provincia_id)
    opts = opciones(munis, "Municipio")
    if not munis:
        return opts, None
    ids = {str(m["id"]) for m in munis}
    cur = str(current_muni) if current_muni else None
    if cur in ids:
        return opts, cur
    return opts, str(munis[0]["id"])


@callback(
    Output("geo-localidad", "options"),
    Output("geo-localidad", "value"),
    Input("geo-municipio", "value"),
    State("geo-localidad", "value"),
)
def on_municipio(municipio_id, current_loc):
    if not municipio_id:
        return opciones([], "Localidad"), None
    locs = localidades(municipio_id)
    opts = opciones(locs, "Localidad")
    if not locs:
        return opts, None
    ids = {str(l["id"]) for l in locs}
    cur = str(current_loc) if current_loc else None
    if cur in ids:
        return opts, cur
    return opts, str(locs[0]["id"])


@callback(
    Output("geo-store", "data"),
    Input("geo-provincia", "value"),
    Input("geo-municipio", "value"),
    Input("geo-localidad", "value"),
)
def on_geo_change(provincia_id, municipio_id, localidad_id):
    prov = next((p for p in provincias() if p["id"] == str(provincia_id or "").zfill(2)), None)
    muni = municipio_por_id(municipio_id)
    locs = localidades(municipio_id)
    loc = next((l for l in locs if l["id"] == localidad_id), locs[0] if locs else None)
    lat_obs, lon_obs, _ = coords_observacion(municipio_id, localidad_id)
    trigger = ctx.triggered_id
    if trigger in ("geo-provincia", "geo-municipio", "geo-localidad"):
        map_zoom = viewport_ccaa_centro(provincia_id, lat_obs, lon_obs, alejado=True)
    else:
        map_zoom = viewport_ccaa_centro(
            provincia_id or _DEFAULT_PROV, lat_obs, lon_obs, alejado=True,
        )
    return {
        "provincia_id": provincia_id,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": municipio_id,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": localidad_id,
        "localidad": loc["nombre"] if loc else None,
        "map_zoom": map_zoom,
    }


@callback(
    Output("page-home", "style"),
    Output("page-historial", "style"),
    Output("tick", "disabled"),
    Output("geo-locate-poll", "disabled"),
    Input("url", "pathname"),
)
def route_pages(pathname):
    on_historial = pathname == "/historial"
    if on_historial:
        return {"display": "none"}, {"display": "block"}, True, True
    return {"display": "block"}, {"display": "none"}, False, True


@callback(
    Output("geo-locate-poll", "disabled", allow_duplicate=True),
    Input("geo-locate-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _activar_poll_geo(_n):
    return False


@callback(
    Output("historial", "figure"),
    Input("url", "pathname"),
    Input("geo-municipio", "value"),
)
def refresh_historial(pathname, municipio_id):
    if pathname != "/historial":
        raise PreventUpdate
    return _fig_historial(municipio_id or _DEFAULT_MUNI, "sira-historial")


def _capas_activas(capas: list[str] | None) -> set[str]:
    return set(capas) if capas else {"sismos", "incendios", "embalses", "aforos", "aemet", "costa"}


def _datos_mapa(geo: dict, d: dict) -> dict:
    """Enriquece datos del dashboard para el mapa de riesgos (sin llamadas meteo)."""
    geo = _geo_resuelto(geo)
    muni_id = geo.get("municipio_id") or _DEFAULT_MUNI
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
    alertas_fuente = _alertas_meteo_fuente(d)
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


def _build_mapa_fig(geo: dict, d: dict, capas: list[str] | None = None) -> go.Figure:
    ctx = _datos_mapa(geo, d)
    geo_r = ctx["geo"]
    act = _capas_activas(capas)
    viewport = _map_viewport(geo_r)
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
    )


def _build_panel_geo(geo: dict, d: dict, capas: list[str] | None = None) -> tuple[list, go.Figure, go.Figure, go.Figure]:
    """Tarjetas, mapa, lluvia y mapa térmico según la zona seleccionada."""
    ctx = _datos_mapa(geo, d)
    geo_r = ctx["geo"]
    muni_id = ctx["muni_id"]
    localidad = ctx["localidad"]
    lat_obs, lon_obs = ctx["lat_obs"], ctx["lon_obs"]
    sismos_mapa = ctx["sismos_mapa"]
    incendios_mapa = ctx["incendios_mapa"]

    sismos = [s for s in sismos_mapa if s.get("perceptible_local")]
    incendios_local = [i for i in incendios_mapa if i.get("cerca_local")]
    met = _meteo_para_geo(muni_id, localidad)
    res_met = met.get("resumen", {})
    lluvia_24 = float(res_met.get("precip_prox_24h_mm") or 0)
    res_emb = resumen_embalses(d.get("embalses", []), lat_obs, lon_obs, lluvia_24h_mm=lluvia_24)
    res_afor = resumen_aforos(d.get("aforos", []), lat_obs, lon_obs)
    alertas_meteo = _alertas_meteo_locales(geo_r, _alertas_meteo_fuente(d))

    mag_max = max((s["magnitud"] for s in sismos), default=0)
    sismo_max = _sismo_mag_max(sismos, mag_max)
    nivel_max = sismo_max.get("nivel_local", sismo_max.get("nivel_alerta")) if sismo_max else None
    loc_label = f"{localidad}, {geo_r.get('municipio') or ''}".strip(", ")

    cards = [
        card_sismos_combinada(
            len(d.get("sismos", [])),
            len(sismos),
            localidad,
            float(mag_max),
            nivel_max,
            _detalle_sismo(sismo_max),
            "",
            accent=C_ORANGE,
        ),
        card_doble(
            "Incendios activos",
            len(d.get("incendios", [])),
            "España",
            len(incendios_local),
            f"cerca · {localidad}",
            f"NASA FIRMS · radio del foco ∝ área afectada · zona local ≤ {INCENDIO_RADIO_LOCAL_KM:.0f} km.",
            accent="#ea580c",
        ),
        card_lluvia(
            lluvia_embalses_valor(res_met.get("precip_prox_24h_mm", "—"), res_emb, res_afor),
            f"Prob. máx. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}",
            f"{loc_label} · SAIH CHJ · embalses {EMBALSE_RADIO_LOCAL_KM:.0f} km · aforos {AFORO_RADIO_LOCAL_KM:.0f} km",
            accent=C_TEAL,
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
        ),
    ]
    cards.append(_riesgo_meteo_card(calcular_riesgo_meteo(alertas_meteo, met, horas=RIESGO_METEO_HORAS)))

    mapa = _build_mapa_fig(geo_r, d, capas)
    lluvia = _fig_lluvia(met.get("serie_horaria", []))
    termico = _fig_termico_ccaa(
        geo_r.get("provincia_id"),
        d.get("termico_ccaa"),
        uirev=f"sira-termico-{muni_id}",
    )
    return cards, mapa, lluvia, termico


@callback(
    Output("cards", "children", allow_duplicate=True),
    Output("mapa", "figure", allow_duplicate=True),
    Output("lluvia", "figure", allow_duplicate=True),
    Output("termico_ccaa", "figure", allow_duplicate=True),
    Input("geo-store", "data"),
    State("map-layers", "value"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def refresh_geo(geo, capas, pathname):
    if pathname == "/historial":
        raise PreventUpdate
    d = _load()
    return _build_panel_geo(geo, d, capas)


@callback(
    Output("mapa", "figure", allow_duplicate=True),
    Input("map-layers", "value"),
    State("geo-store", "data"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def refresh_map_layers(capas, geo, pathname):
    if pathname == "/historial":
        raise PreventUpdate
    return _build_mapa_fig(geo, _load(), capas)


@callback(
    Output("cards", "children"), Output("ts", "children"), Output("data-ts-store", "data"),
    Output("mapa", "figure"), Output("lluvia", "figure"), Output("termico_ccaa", "figure"),
    Output("sst_med", "figure"), Output("sst_cant", "figure"), Output("sst_atl", "figure"),
    Output("cor_med", "figure"), Output("cor_cant", "figure"), Output("cor_atl", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"),
    State("geo-store", "data"),
    State("map-layers", "value"),
    State("data-ts-store", "data"),
    State("url", "pathname"),
)
def refresh(n_intervals, clicks, geo, capas, last_ts, pathname):
    if pathname == "/historial":
        raise PreventUpdate
    if ALLOW_DATA_REFRESH and ctx.triggered_id == "btn" and clicks:
        try:
            requests.post(
                f"{API_BASE_URL}/api/actualizar",
                headers={"X-API-Key": API_KEY},
                timeout=120,
            )
        except requests.RequestException:
            pass

    d = _load()
    alertas_fuente = _alertas_meteo_fuente(d)
    refresh_token = _data_refresh_token(d, alertas_fuente)
    if ctx.triggered_id == "tick" and n_intervals and last_ts == refresh_token:
        raise PreventUpdate

    geo = _geo_resuelto(geo)
    cards, mapa, lluvia, termico = _build_panel_geo(geo, d, capas)
    oce = d.get("oceanografia", {})
    ts = fmt_ingesta_local(d.get("generado_en"))
    if d.get("sismo_prueba_activo"):
        ts = f"{ts} · Sismo de prueba en mapa"

    oce_med = _bloque_oce(oce, "MEDITERRÁNEO")
    oce_cant = _bloque_oce(oce, "CANTÁBRICO")
    oce_atl = _bloque_oce(oce, "ATLÁNTICO")

    return (
        cards, ts, refresh_token,
        mapa, lluvia, termico,
        _fig_linea(oce_med.get("serie_horaria", []), "sst_c", C_ORANGE, "°C", "sira-sst-med", con_semaforo_sst=True),
        _fig_linea(oce_cant.get("serie_horaria", []), "sst_c", C_GREEN, "°C", "sira-sst-cant", con_semaforo_sst=True),
        _fig_linea(oce_atl.get("serie_horaria", []), "sst_c", C_CYAN, "°C", "sira-sst-atl", con_semaforo_sst=True),
        _fig_corrientes(oce_med.get("serie_horaria", []), "sira-cor-med"),
        _fig_corrientes(oce_cant.get("serie_horaria", []), "sira-cor-cant"),
        _fig_corrientes(oce_atl.get("serie_horaria", []), "sira-cor-atl"),
    )


if __name__ == "__main__":
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)


# WSGI (gunicorn en Render)
server = app.server


@server.route("/sw.js")
def _service_worker():
    resp = send_from_directory(str(_ASSETS), "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# Huella SHA-256 del keystore debug (añade la de release al publicar en Play Store).
_ANDROID_SHA256_DEBUG = (
    "30:20:B7:AC:BD:FB:CF:A4:90:77:A2:20:6F:F0:73:10:"
    "B3:A0:A7:87:78:8E:E0:48:3F:B1:50:B8:D9:0E:F8:D4"
)


@server.route("/.well-known/assetlinks.json")
def _assetlinks():
    return jsonify(
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": "es.sira.alertas",
                    "sha256_cert_fingerprints": [_ANDROID_SHA256_DEBUG],
                },
            }
        ]
    )


_FUENTE_ETIQUETAS = {
    "usgs": "USGS (sismos)",
    "aemet_meteo": "AEMET meteo",
    "termico_ccaa": "Mapa térmico CCAA",
    "aemet_cap": "AEMET CAP",
    "open_meteo_marine": "Open-Meteo marine",
    "open_meteo_weather": "Open-Meteo weather",
    "firms": "NASA FIRMS",
    "embals_es": "embals.es",
    "saih_chj": "SAIH CHJ",
}

_FUENTE_DESCRIPCIONES = {
    "usgs": "Sismos recientes en España y entorno (magnitud, epicentro, profundidad, alerta tsunami USGS).",
    "aemet_meteo": "Predicción horaria municipal AEMET (lluvia, probabilidad de precipitación, tiempo actual).",
    "termico_ccaa": "Resumen térmico por provincia/CCAA precalculado en ingesta para evitar llamadas meteorológicas en el render.",
    "aemet_cap": "Avisos Meteoalerta CAP por zona (temperatura, viento, lluvia, costa, tormentas, etc.).",
    "open_meteo_marine": "Temperatura superficial del mar y corrientes (Mediterráneo, Cantábrico, Atlántico).",
    "open_meteo_weather": "Previsión horaria de precipitación (respaldo cuando AEMET no está disponible).",
    "firms": "Puntos de calor e incendios activos detectados por satélite en territorio español.",
    "embals_es": "Niveles, capacidad y riesgo hidrológico de embalses (cuencas Júcar, Segura y Ebro).",
    "saih_chj": "Caudales y estaciones de aforo en tiempo casi real (SAIH, Confederación Hidrográfica del Júcar).",
}


def _status_snapshot() -> dict:
    """Lee estado desde API; fallback local si no responde."""
    try:
        r = requests.get(f"{API_BASE_URL}/api/status", timeout=15)
        if r.ok:
            payload = r.json()
            if isinstance(payload, dict):
                return payload
    except requests.RequestException:
        pass
    data = read_dashboard()
    return {
        "generado_en": data.get("generado_en", "—"),
        "fuentes_estado": data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {},
        "suscripciones_push": count_subscriptions(),
        "ok": bool(data.get("generado_en")),
    }


def _fmt_status_dt(value: str | None) -> str:
    return fmt_ingesta_local(value)


@server.route("/status")
def _status_page():
    data = _status_snapshot()
    fuentes = data.get("fuentes_estado") if isinstance(data.get("fuentes_estado"), dict) else {}
    generado = _fmt_status_dt(data.get("generado_en"))
    n_push = data.get("suscripciones_push", 0)
    filas = []
    for clave, etiqueta in _FUENTE_ETIQUETAS.items():
        info = fuentes.get(clave, {})
        desc = _FUENTE_DESCRIPCIONES.get(clave, "—")
        ok = info.get("ok")
        if info.get("omitido"):
            estado = '<span class="sira-status-warn">omitido</span>'
        elif ok:
            n = info.get("registros", "—")
            estado = f'<span class="sira-status-ok">OK</span> <span class="sira-status-meta">({n} registros)</span>'
        else:
            err = info.get("error") or "error"
            estado = f'<span class="sira-status-fail">ERROR</span> <span class="sira-status-meta">{err}</span>'
        filas.append(
            f'<tr><td>{etiqueta}</td><td class="sira-status-desc">{desc}</td><td>{estado}</td></tr>'
        )
    tabla = "\n".join(filas)
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIRA — Estado del sistema</title>
  <link rel="stylesheet" href="/assets/sira.css?v=32">
</head>
<body class="sira-page sira-status-page">
  <main class="sira-main">
    <div class="sira-container">
      <h1 class="sira-title">Estado del sistema</h1>
      <p class="sira-status-ts">Última ingesta: <strong>{generado}</strong> <span class="sira-ts-badge">Hora local</span></p>
      <p class="sira-status-ts">Suscripciones push activas: <strong>{n_push}</strong></p>
      <table class="sira-status-table">
        <thead><tr><th>Fuente</th><th>Descripción</th><th>Estado</th></tr></thead>
        <tbody>{tabla}</tbody>
      </table>
      <p class="sira-status-back"><a href="/">← Volver al dashboard</a></p>
    </div>
  </main>
</body>
</html>"""
    from flask import Response
    return Response(html, mimetype="text/html")


@server.route("/manifest.webmanifest")
def _manifest():
    return jsonify(
        {
            "name": "SIRA — Sistema Ibérico de Riesgos y Alerta",
            "short_name": "SIRA",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#0a1628",
            "theme_color": "#0a1628",
            "icons": [
                {
                    "src": app.get_asset_url("logo-sira_4.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
            ],
        }
    )


clientside_callback(
    """
    function(n) {
        const d = window.__siraGeoLocateResult;
        if (!d) {
            return [
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
                window.dash_clientside.no_update,
            ];
        }
        window.__siraGeoLocateResult = null;
        return [
            d.provincia_id,
            d.municipio_id,
            d.localidad_id,
            {
                provincia_id: d.provincia_id,
                municipio_id: d.municipio_id,
                localidad_id: d.localidad_id,
                provincia: d.provincia,
                municipio: d.municipio,
                localidad: d.localidad,
            },
            true,
        ];
    }
    """,
    Output("geo-provincia", "value"),
    Output("geo-municipio", "value"),
    Output("geo-localidad", "value"),
    Output("geo-store", "data", allow_duplicate=True),
    Output("geo-locate-poll", "disabled", allow_duplicate=True),
    Input("geo-locate-poll", "n_intervals"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(geo) {
        const el = document.getElementById('push-geo');
        if (el && geo) {
            el.dataset.provinciaId = geo.provincia_id || '';
            el.dataset.municipioId = geo.municipio_id || '';
            el.dataset.localidadId = geo.localidad_id || '';
            el.dataset.municipio = geo.municipio || '';
            el.dispatchEvent(new CustomEvent('sira-geo-changed'));
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("push-geo", "children"),
    Input("geo-store", "data"),
)
