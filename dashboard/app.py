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
from dash.exceptions import PreventUpdate

from ui.components import bloque, card_lluvia
from sira.config.settings import (
    ALLOW_DATA_REFRESH,
    API_BASE_URL,
    API_KEY,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_REFRESH_MS,
    DASHBOARD_REFRESH_MIN,
    DATA_FILE,
    FORECAST_DAYS,
    INGESTA_INTERVAL_MIN,
    MARES,
)
from sira.infrastructure.http.client import fmt_ingesta_local, read_dashboard  # noqa: E402
from routes.flask_routes import register_routes
from geo.context import DEFAULT_LOC, DEFAULT_MUNI, DEFAULT_PROV, default_geo, geo_resuelto, theme_val
from geo.panel import alertas_meteo_fuente, build_mapa_fig, build_panel_geo
from sira.infrastructure.geo.es import (
    coords_observacion,
    localidades,
    municipio_por_id,
    municipios,
    opciones,
    provincia_de_municipio,
    provincias,
    viewport_ccaa_centro,
)
from geo.ui import selector_geo
from sira.infrastructure.sources.meteo.aemet_alerts import alerta_firma
from ui.theme import C_CYAN, C_GREEN, C_ORANGE, C_TEAL

from charts.figures import (
    fig_corrientes as _fig_corrientes,
    fig_linea as _fig_linea,
    fig_historial as _fig_historial_impl,
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
        <link rel="stylesheet" href="/assets/sira.css?v=36">
        <meta name="theme-color" content="#0a1628">
        <script src="/assets/theme.js"></script>
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

_AYUDA_OCE_PREVISION = f"Previsión horaria · {FORECAST_DAYS} días · Open-Meteo Marine"

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
            dcc.Store(id="theme-store", data="dark"),
            dcc.Store(id="geo-store", data=default_geo()),
            dcc.Interval(id="geo-locate-poll", interval=500, n_intervals=0, disabled=True, max_intervals=60),
            html.Div(id="geo-locate-pending", style={"display": "none"}),
            selector_geo(DEFAULT_PROV, DEFAULT_MUNI, DEFAULT_LOC),
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
                        html.Button(
                            [
                                html.Span("☀ Modo claro", className="sira-theme-label sira-theme-label--to-light"),
                                html.Span("🌙 Modo oscuro", className="sira-theme-label sira-theme-label--to-dark"),
                            ],
                            id="theme-toggle",
                            n_clicks=0,
                            className="sira-btn-theme",
                            title="Cambiar entre modo claro y oscuro",
                            type="button",
                        ),
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
                                {"label": "Tsunami", "value": "costa"},
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


def _bloque_oce(oce: dict, clave: str) -> dict:
    bloque = oce.get(clave)
    if isinstance(bloque, dict) and bloque.get("serie_horaria") is not None:
        return bloque
    if clave == "MEDITERRÁNEO" and oce.get("serie_horaria") is not None:
        return oce
    return {"serie_horaria": [], "resumen": {}}


def _data_refresh_token(d: dict, alertas: list[dict] | None = None) -> str:
    src = alertas if alertas is not None else alertas_meteo_fuente(d)
    firmas = sorted(
        "|".join(alerta_firma(a))
        for a in src
        if isinstance(a, dict)
    )
    tsunami_sig = "|".join(
        f"{s.get('lat')},{s.get('lon')},{s.get('radio_tsunami_km')}"
        for s in d.get("sismos", [])
        if isinstance(s, dict) and s.get("alerta_tsunami")
    )
    return (
        f"{d.get('generado_en', '—')}|{len(d.get('sismos', []))}|{len(d.get('incendios', []))}|{len(d.get('embalses', []))}|{len(d.get('aforos', []))}"
        f"|{'|'.join(firmas)}|{bool(d.get('sismo_prueba_activo'))}|prueba:{d.get('sismos_prueba_activos', 0)}|tsunami:{tsunami_sig}"
    )


def _fig_historial(municipio_id: str | None, uirev: str, theme: str = "dark") -> go.Figure:
    return _fig_historial_impl(municipio_id, DEFAULT_MUNI, uirev, theme=theme)


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
            provincia_id or DEFAULT_PROV, lat_obs, lon_obs, alejado=True,
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
    Input("theme-store", "data"),
)
def refresh_historial(pathname, municipio_id, theme):
    if pathname != "/historial":
        raise PreventUpdate
    return _fig_historial(municipio_id or DEFAULT_MUNI, "sira-historial", theme_val(theme))


@callback(
    Output("cards", "children", allow_duplicate=True),
    Output("mapa", "figure", allow_duplicate=True),
    Output("lluvia", "figure", allow_duplicate=True),
    Input("geo-store", "data"),
    Input("theme-store", "data"),
    State("map-layers", "value"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def refresh_geo(geo, theme, capas, pathname):
    if pathname == "/historial":
        raise PreventUpdate
    d = _load()
    t = theme_val(theme)
    return build_panel_geo(geo, d, capas, t)


@callback(
    Output("mapa", "figure", allow_duplicate=True),
    Input("map-layers", "value"),
    Input("theme-store", "data"),
    State("geo-store", "data"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def refresh_map_layers(capas, theme, geo, pathname):
    if pathname == "/historial":
        raise PreventUpdate
    return build_mapa_fig(geo, _load(), capas, theme_val(theme))


@callback(
    Output("cards", "children"), Output("ts", "children"), Output("data-ts-store", "data"),
    Output("mapa", "figure"), Output("lluvia", "figure"),
    Output("sst_med", "figure"), Output("sst_cant", "figure"), Output("sst_atl", "figure"),
    Output("cor_med", "figure"), Output("cor_cant", "figure"), Output("cor_atl", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"),
    Input("theme-store", "data"),
    State("geo-store", "data"),
    State("map-layers", "value"),
    State("data-ts-store", "data"),
    State("url", "pathname"),
)
def refresh(n_intervals, clicks, theme, geo, capas, last_ts, pathname):
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
    alertas_fuente = alertas_meteo_fuente(d)
    refresh_token = _data_refresh_token(d, alertas_fuente)
    if ctx.triggered_id == "tick" and n_intervals and last_ts == refresh_token:
        raise PreventUpdate

    geo = geo_resuelto(geo)
    t = theme_val(theme)
    cards, mapa, lluvia = build_panel_geo(geo, d, capas, t)
    oce = d.get("oceanografia", {})
    ts = fmt_ingesta_local(d.get("generado_en"))
    if d.get("sismo_prueba_activo"):
        ts = f"{ts} · Sismo de prueba en mapa"

    oce_med = _bloque_oce(oce, "MEDITERRÁNEO")
    oce_cant = _bloque_oce(oce, "CANTÁBRICO")
    oce_atl = _bloque_oce(oce, "ATLÁNTICO")

    return (
        cards, ts, refresh_token,
        mapa, lluvia,
        _fig_linea(oce_med.get("serie_horaria", []), "sst_c", C_ORANGE, "°C", "sira-sst-med", con_semaforo_sst=True, theme=t),
        _fig_linea(oce_cant.get("serie_horaria", []), "sst_c", C_GREEN, "°C", "sira-sst-cant", con_semaforo_sst=True, theme=t),
        _fig_linea(oce_atl.get("serie_horaria", []), "sst_c", C_CYAN, "°C", "sira-sst-atl", con_semaforo_sst=True, theme=t),
        _fig_corrientes(oce_med.get("serie_horaria", []), "sira-cor-med", theme=t),
        _fig_corrientes(oce_cant.get("serie_horaria", []), "sira-cor-cant", theme=t),
        _fig_corrientes(oce_atl.get("serie_horaria", []), "sira-cor-atl", theme=t),
    )


if __name__ == "__main__":
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)


# WSGI (gunicorn en Render)
server = app.server
register_routes(server, app, _ASSETS)


clientside_callback(
    """
    function(pathname) {
        if (window.siraTheme) {
            return window.siraTheme.preferred();
        }
        return 'dark';
    }
    """,
    Output("theme-store", "data"),
    Input("url", "pathname"),
)


clientside_callback(
    """
    function(n_clicks, theme) {
        if (!n_clicks) {
            return window.dash_clientside.no_update;
        }
        if (window.siraTheme) {
            return window.siraTheme.toggle(theme || 'dark');
        }
        return (theme === 'light') ? 'dark' : 'light';
    }
    """,
    Output("theme-store", "data", allow_duplicate=True),
    Input("theme-toggle", "n_clicks"),
    State("theme-store", "data"),
    prevent_initial_call=True,
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
