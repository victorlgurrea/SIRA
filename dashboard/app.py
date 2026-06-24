"""Dashboard SIRA."""
from __future__ import annotations

import _bootstrap  # noqa: F401

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate

from components import bloque, card, dir_compass, mag_con_riesgo, regiones
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
    MARES,
    MAPA,
    ZONA,
)
from core import read_dashboard  # noqa: E402
from geo_es import coords_municipio, localidades, municipio_por_id, municipios, opciones, provincia_de_municipio, provincias
from geo_ui import selector_geo
from meteo_live import meteo_localidad
from sismos import filtrar_perceptibles
from theme import (
    C_CYAN,
    C_GREEN,
    C_MUTED,
    C_NAVY,
    C_ORANGE,
    C_TEAL,
    COLORES,
    PLOTLY_BG,
)

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_FILE = _ASSETS / "logo_sira_3.png"
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
        <link rel="stylesheet" href="/assets/sira.css?v=13">
        <link rel="icon" href="/assets/logo_sira_3.png?v=8" type="image/png">
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

_LOGO = app.get_asset_url("logo_sira_3.png") + "?v=8"

_DEFAULT_MUNI = str(AEMET_MUNICIPIO).zfill(5)
_DEFAULT_PROV = provincia_de_municipio(_DEFAULT_MUNI) or "46"
_locs = localidades(_DEFAULT_MUNI)
_DEFAULT_LOC = _locs[0]["id"] if _locs else _DEFAULT_MUNI

_BTN_CLASS = "sira-btn-refresh" + ("" if ALLOW_DATA_REFRESH else " sira-btn-refresh--hidden")

app.layout = html.Div(className="sira-page", children=[
    html.Header(className="sira-header", children=[
        html.Div(className="sira-header-inner", children=[
            html.Div(className="sira-header-text", children=[
                html.H1("SIRA", className="sira-title"),
                html.P("Sistema Ibérico de Riesgos y Alerta", className="sira-subtitle"),
                html.P(
                    "Sismos · Cantábrico · Atlántico · Oceanografía · Meteorología",
                    className="sira-tags",
                ),
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
            html.Div(id="cards", className="sira-cards"),
            html.Div(className="sira-content", children=[
                html.Div(className="sira-toolbar", children=[
                    html.Div(className="sira-ts-wrap", children=[
                        html.Span(id="ts", className="sira-ts"),
                        html.Span(f" · auto cada {DASHBOARD_REFRESH_MIN} min", className="sira-ts-hint"),
                    ]),
                    html.Button("Actualizar", id="btn", n_clicks=0, className=_BTN_CLASS),
                ]),
                dcc.Interval(id="tick", interval=DASHBOARD_REFRESH_MS, n_intervals=0),
                dcc.Store(id="data-ts-store"),
                dcc.Store(id="geo-store"),
                selector_geo(_DEFAULT_PROV, _DEFAULT_MUNI, _DEFAULT_LOC),
                html.Div(className="sira-charts", children=[
                    html.Div(className="sira-charts-row", children=[
                        bloque(
                            "mapa", "Mapa sísmico — España",
                            f"Últimos {ZONA['dias_atras']} días · M≥{ZONA['magnitud_min']}.",
                            map_chart=True, accent=C_ORANGE,
                        ),
                        bloque(
                            "lluvia", "Previsión de lluvia",
                            "Según la localidad seleccionada · AEMET o Open-Meteo.",
                            accent=C_TEAL,
                        ),
                    ]),
                    html.Div(className="sira-charts-row sira-charts-row--3", children=[
                        bloque(
                            "sst_med", "SST — Mediterráneo",
                            f"Temperatura superficial · {MARES['MEDITERRÁNEO']['punto']}.",
                            accent=C_ORANGE,
                        ),
                        bloque(
                            "sst_cant", "SST — Cantábrico",
                            f"Temperatura superficial · {MARES['CANTÁBRICO']['punto']}.",
                            accent=C_GREEN,
                        ),
                        bloque(
                            "sst_atl", "SST — Atlántico",
                            f"Temperatura superficial · {MARES['ATLÁNTICO']['punto']}.",
                            accent=C_CYAN,
                        ),
                    ]),
                    html.Div(className="sira-charts-row sira-charts-row--3", children=[
                        bloque(
                            "cor_med", "Corrientes — Mediterráneo",
                            f"Velocidad y dirección · {MARES['MEDITERRÁNEO']['punto']}.",
                            accent=C_ORANGE,
                        ),
                        bloque(
                            "cor_cant", "Corrientes — Cantábrico",
                            f"Velocidad y dirección · {MARES['CANTÁBRICO']['punto']}.",
                            accent=C_GREEN,
                        ),
                        bloque(
                            "cor_atl", "Corrientes — Atlántico",
                            f"Velocidad y dirección · {MARES['ATLÁNTICO']['punto']}.",
                            accent=C_CYAN,
                        ),
                    ]),
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
        r = requests.get(f"{API_BASE_URL}/api/dashboard", timeout=10)
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return read_dashboard()


def _es_sismo_hoy(ts) -> bool:
    try:
        return pd.to_datetime(ts, utc=True).date() == datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        return False


def _fmt_sismo_fecha(ts) -> str:
    try:
        return pd.to_datetime(ts, utc=True).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, TypeError):
        return "—"


def _sismo_mag_max(sismos: list, mag_max: float) -> dict | None:
    if not sismos:
        return None
    candidatos = [s for s in sismos if s.get("magnitud") == mag_max]
    if not candidatos:
        candidatos = sismos
    return max(candidatos, key=lambda s: (s.get("score_total", 0), s.get("magnitud", 0)))


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


def _fig_mapa(sismos: list, lat_obs: float | None = None, lon_obs: float | None = None, obs_nombre: str = "") -> go.Figure:
    fig = go.Figure()
    df = pd.DataFrame(sismos) if sismos else pd.DataFrame()
    hoy_df = pd.DataFrame()
    hoy_scale = 1.35

    for nivel, color in COLORES.items():
        sub = df[df["nivel_alerta"] == nivel] if not df.empty else pd.DataFrame()
        if sub.empty:
            continue
        reg_col = sub["region"] if "region" in sub.columns else [""] * len(sub)
        fechas = [_fmt_sismo_fecha(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else ["—"] * len(sub)
        dist_loc = sub["dist_local_km"] if "dist_local_km" in sub.columns else [""] * len(sub)
        hoy_mask = [_es_sismo_hoy(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else [False] * len(sub)
        base = sub["magnitud"] * 2 + 5
        sizes = [b * hoy_scale if h else b for b, h in zip(base, hoy_mask)]
        borders = [("#f87171", 2.5) if h else ("white", 0.5) for h in hoy_mask]
        fig.add_trace(go.Scattergeo(
            lat=sub["lat"], lon=sub["lon"], mode="markers", name=nivel,
            marker=dict(
                size=sizes, color=color,
                line=dict(width=[b[1] for b in borders], color=[b[0] for b in borders]),
            ),
            text=sub["lugar"],
            customdata=list(zip(sub["magnitud"], sub["score_total"], reg_col, fechas, dist_loc)),
            hovertemplate=(
                "%{text}<br>"
                "Fecha: %{customdata[3]}<br>"
                "Mag %{customdata[0]} · Score %{customdata[1]} · %{customdata[2]}<br>"
                "Distancia: %{customdata[4]} km"
                "<extra></extra>"
            ),
        ))

    if not df.empty and "timestamp" in df.columns:
        hoy_df = df[df["timestamp"].map(_es_sismo_hoy)]

    if not hoy_df.empty:
        halo = hoy_df["magnitud"] * 2 + 5
        fig.add_trace(go.Scattergeo(
            lat=hoy_df["lat"], lon=hoy_df["lon"], mode="markers", name="Hoy",
            marker=dict(
                size=[s * hoy_scale * 2.4 for s in halo],
                color="rgba(248, 113, 113, 0.35)",
                line=dict(width=1.5, color="#f87171"),
            ),
            hoverinfo="skip", legendgroup="hoy",
        ))
    if lat_obs is not None and lon_obs is not None:
        fig.add_trace(go.Scattergeo(
            lat=[lat_obs], lon=[lon_obs], mode="markers+text",
            text=[obs_nombre or "Ubicación"], showlegend=False,
            marker=dict(size=11, color="#fbbf24", symbol="star", line=dict(width=1, color="white")),
            textposition="top center",
        ))
    for lat, lon, name, color in (
        (MAPA["lat_centro"], MAPA["lon_centro"], MAPA["ciudad_centro"], "gold"),
        (ZONA["lat_ref"], ZONA["lon_ref"], ZONA["ciudad_ref"], C_CYAN),
    ):
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers+text", text=[name], showlegend=False,
            marker=dict(size=10, color=color, symbol="star"),
        ))
    fig.update_geos(
        scope="europe",
        projection_type="mercator",
        center=dict(lat=MAPA["lat_centro"], lon=MAPA["lon_centro"]),
        projection_scale=MAPA["projection_scale"],
        lataxis_range=[MAPA["lat_min"], MAPA["lat_max"]],
        lonaxis_range=[MAPA["lon_min"], MAPA["lon_max"]],
        showland=True, landcolor=C_NAVY,
        showocean=True, oceancolor="#1e4976",
        showcountries=True, countrycolor="#1e4976", coastlinecolor="#94a3b8",
    )
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        legend=dict(title="Alerta", orientation="h", yanchor="bottom", y=1.02, x=0),
        autosize=True,
        uirevision="sira-mapa",
        **PLOTLY_BG,
    )
    return fig


def _fig_corrientes(serie: list, uirev: str) -> go.Figure:
    fig = go.Figure()
    dir_txt = "—"
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=s["timestamp"], y=s["corriente_vel_ms"],
            mode="lines", name="m/s", line=dict(color=C_GREEN),
        ))
        ult = s.iloc[-1]
        dir_txt = dir_compass(ult.get("corriente_dir_grados"))
    fig.update_layout(
        margin=dict(t=28, b=0, l=0, r=0),
        autosize=True,
        yaxis_title="m/s",
        uirevision=uirev,
        annotations=[dict(
            text=f"Dirección: {dir_txt}",
            xref="paper", yref="paper", x=0, y=1.12,
            showarrow=False, font=dict(color=C_GREEN, size=11),
        )],
        **PLOTLY_BG,
    )
    return fig


def _stats_region(sismos: list) -> dict[str, int]:
    reg: dict[str, int] = {}
    for s in sismos:
        r = s.get("region", "")
        reg[r] = reg.get(r, 0) + 1
    return reg


def _fig_linea(serie: list, campo: str, color: str, unidad: str, uirev: str) -> go.Figure:
    fig = go.Figure()
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(x=s["timestamp"], y=s[campo], mode="lines", line=dict(color=color)))
    fig.update_layout(margin=dict(t=10, b=0, l=0, r=0), autosize=True, yaxis_title=unidad, uirevision=uirev, **PLOTLY_BG)
    return fig


def _fig_lluvia(serie: list) -> go.Figure:
    fig = go.Figure()
    yaxis = dict(title="mm", rangemode="tozero")
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        precip = s["precip_mm"].fillna(0)
        fig.add_trace(go.Bar(x=s["timestamp"], y=precip, name="mm", marker_color=C_TEAL))
        if s["prob_precip_pct"].notna().any():
            fig.add_trace(go.Scatter(x=s["timestamp"], y=s["prob_precip_pct"], name="%", yaxis="y2", line=dict(color="#a78bfa")))
        max_precip = float(precip.max())
        yaxis["range"] = [0, max(1.0, max_precip * 1.15)]
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        autosize=True,
        yaxis=yaxis,
        yaxis2=dict(overlaying="y", side="right", range=[0, 100], title="%"),
        uirevision="sira-lluvia",
        **PLOTLY_BG,
    )
    return fig


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
    ids = {m["id"] for m in munis}
    if current_muni in ids:
        return opts, current_muni
    return opts, munis[0]["id"]


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
    ids = {l["id"] for l in locs}
    if current_loc in ids:
        return opts, current_loc
    return opts, locs[0]["id"]


@callback(
    Output("geo-store", "data"),
    Input("geo-provincia", "value"),
    Input("geo-municipio", "value"),
    Input("geo-localidad", "value"),
)
def on_geo_change(provincia_id, municipio_id, localidad_id):
    prov = next((p for p in provincias() if p["id"] == provincia_id), None)
    muni = municipio_por_id(municipio_id)
    locs = localidades(municipio_id)
    loc = next((l for l in locs if l["id"] == localidad_id), locs[0] if locs else None)
    return {
        "provincia_id": provincia_id,
        "provincia": prov["nombre"] if prov else None,
        "municipio_id": municipio_id,
        "municipio": muni["nombre"] if muni else None,
        "localidad_id": localidad_id,
        "localidad": loc["nombre"] if loc else None,
    }


@callback(
    Output("cards", "children"), Output("ts", "children"), Output("data-ts-store", "data"),
    Output("mapa", "figure"), Output("lluvia", "figure"),
    Output("sst_med", "figure"), Output("sst_cant", "figure"), Output("sst_atl", "figure"),
    Output("cor_med", "figure"), Output("cor_cant", "figure"), Output("cor_atl", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"), Input("geo-store", "data"),
    State("data-ts-store", "data"),
)
def refresh(n_intervals, clicks, geo, last_ts):
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
    ts_raw = d.get("generado_en", "—")
    if ctx.triggered_id == "tick" and n_intervals and last_ts == ts_raw:
        raise PreventUpdate

    geo = geo or {}
    muni_id = geo.get("municipio_id") or _DEFAULT_MUNI
    localidad = geo.get("localidad") or ZONA["ciudad_ref"]
    lat_obs, lon_obs = coords_municipio(muni_id)

    sismos_all = d.get("sismos", [])
    sismos = filtrar_perceptibles(sismos_all, lat_obs, lon_obs)
    oce = d.get("oceanografia", {})
    met = meteo_localidad(muni_id, localidad)

    mag_max = max((s["magnitud"] for s in sismos), default=0)
    sismo_max = _sismo_mag_max(sismos, mag_max)
    nivel_max = sismo_max.get("nivel_alerta") if sismo_max else None
    reg = _stats_region(sismos)
    res_met = met.get("resumen", {})

    loc_label = f"{localidad}, {geo.get('municipio') or ''}".strip(", ")

    cards = [
        card(
            "Sismos perceptibles", str(len(sismos)),
            regiones(reg),
            f"Desde {loc_label} · M≥{ZONA['magnitud_min']}, últimos {ZONA['dias_atras']} días",
            accent=C_ORANGE,
        ),
        card(
            "Magnitud máx.",
            mag_con_riesgo(float(mag_max), nivel_max),
            _detalle_sismo(sismo_max),
            "Eventos críticos con score ≥ 55.",
            accent="#ef4444",
        ),
        card(
            "Lluvia 24h", f"{res_met.get('precip_prox_24h_mm', '—')} mm",
            f"Prob. máx. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}",
            loc_label,
            accent=C_TEAL,
        ),
    ]
    ts = d.get("generado_en", "—")
    try:
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, AttributeError):
        pass

    oce_med = _bloque_oce(oce, "MEDITERRÁNEO")
    oce_cant = _bloque_oce(oce, "CANTÁBRICO")
    oce_atl = _bloque_oce(oce, "ATLÁNTICO")

    return (
        cards, f"Actualizado: {ts}", ts_raw,
        _fig_mapa(sismos, lat_obs, lon_obs, localidad),
        _fig_lluvia(met.get("serie_horaria", [])),
        _fig_linea(oce_med.get("serie_horaria", []), "sst_c", C_ORANGE, "°C", "sira-sst-med"),
        _fig_linea(oce_cant.get("serie_horaria", []), "sst_c", C_GREEN, "°C", "sira-sst-cant"),
        _fig_linea(oce_atl.get("serie_horaria", []), "sst_c", C_CYAN, "°C", "sira-sst-atl"),
        _fig_corrientes(oce_med.get("serie_horaria", []), "sira-cor-med"),
        _fig_corrientes(oce_cant.get("serie_horaria", []), "sira-cor-cant"),
        _fig_corrientes(oce_atl.get("serie_horaria", []), "sira-cor-atl"),
    )


if __name__ == "__main__":
    if not DATA_FILE.exists():
        raise SystemExit("Sin datos. Ejecuta startup.py para generar la ingesta inicial.")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
