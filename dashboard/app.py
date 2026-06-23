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
    ALLOW_DATA_REFRESH,
    API_BASE_URL,
    API_KEY,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_REFRESH_MS,
    DASHBOARD_REFRESH_MIN,
    DATA_FILE,
    MAPA,
    ZONA,
)
from core import read_dashboard  # noqa: E402
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
        <link rel="stylesheet" href="/assets/sira.css?v=9">
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
                html.Div(className="sira-charts", children=[
                    bloque(
                        "mapa", "Mapa sísmico — España",
                        f"Últimos {ZONA['dias_atras']} días · M≥{ZONA['magnitud_min']}.",
                        full=True, accent=C_ORANGE,
                    ),
                    bloque("lluvia", "Previsión de lluvia", "AEMET con fallback Open-Meteo.", accent=C_TEAL),
                    bloque("sst", "SST — Mar Mediterráneo", f"Temperatura superficial del mar · {ZONA['ciudad_ref']}.", accent=C_CYAN),
                    bloque("corrientes", "Corrientes marinas", "Velocidad (m/s) y dirección de la corriente.", accent=C_GREEN),
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


def _nivel_mag_max(sismos: list, mag_max: float) -> str | None:
    if not sismos:
        return None
    candidatos = [s for s in sismos if s.get("magnitud") == mag_max]
    if not candidatos:
        candidatos = sismos
    return max(candidatos, key=lambda s: (s.get("score_total", 0), s.get("magnitud", 0))).get("nivel_alerta")


def _fig_mapa(sismos: list) -> go.Figure:
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
            customdata=list(zip(sub["magnitud"], sub["score_total"], reg_col, fechas)),
            hovertemplate=(
                "%{text}<br>"
                "Fecha: %{customdata[3]}<br>"
                "Mag %{customdata[0]} · Score %{customdata[1]} · %{customdata[2]}"
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


def _fig_linea(serie: list, campo: str, color: str, unidad: str) -> go.Figure:
    fig = go.Figure()
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(x=s["timestamp"], y=s[campo], mode="lines", line=dict(color=color)))
    fig.update_layout(margin=dict(t=10, b=0, l=0, r=0), autosize=True, yaxis_title=unidad, uirevision=f"sira-{campo}", **PLOTLY_BG)
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
    Output("cards", "children"), Output("ts", "children"), Output("data-ts-store", "data"),
    Output("mapa", "figure"), Output("lluvia", "figure"),
    Output("sst", "figure"), Output("corrientes", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"),
    State("data-ts-store", "data"),
)
def refresh(n_intervals, clicks, last_ts):
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

    sismos, st = d.get("sismos", []), d.get("estadisticas", {})
    oce, met = d.get("oceanografia", {}), d.get("meteorologia", {})
    res_oce, res_met = oce.get("resumen", {}), met.get("resumen", {})
    reg = st.get("por_region", {})

    mag_max = float(st.get("mag_max", 0) or 0)
    nivel_max = _nivel_mag_max(sismos, mag_max)

    cards = [
        card(
            "Sismos", str(st.get("n_sismos", 0)),
            regiones(reg),
            f"M≥{ZONA['magnitud_min']}, últimos {ZONA['dias_atras']} días · fuente USGS",
            accent=C_ORANGE,
        ),
        card(
            "Magnitud máx.",
            mag_con_riesgo(mag_max, nivel_max),
            f"Score {st.get('score_max', 0)} · {st.get('n_alto_critico', 0)} en nivel Alto o Crítico",
            "El score combina magnitud, profundidad, distancia a Valencia y zona submarina (0–100+). "
            "Alto/Crítico: eventos con score ≥ 55.",
            accent="#ef4444",
        ),
        card(
            "Lluvia 24h", f"{res_met.get('precip_prox_24h_mm', '—')} mm",
            f"Prob. máx. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}",
            met.get("municipio", ZONA["ciudad_ref"]),
            accent=C_TEAL,
        ),
        card(
            "SST — Mar Mediterráneo", f"{res_oce.get('sst_actual_c', '—')} °C",
            f"Temperatura superficial del mar · anomalía {res_oce.get('anomalia_c', '—')} °C",
            f"Punto de referencia: {ZONA['ciudad_ref']} · Open-Meteo marine",
            accent=C_CYAN,
        ),
        card(
            "Corriente marina", f"{res_oce.get('corriente_vel_ms', '—')} m/s",
            html.Div([
                html.Span("Dirección: ", style={"color": C_MUTED}),
                html.Span(
                    dir_compass(res_oce.get("corriente_dir_grados")),
                    style={"color": C_GREEN, "fontWeight": "600"},
                ),
            ]),
            f"Rumbo de la corriente en el Mediterráneo occidental · {ZONA['ciudad_ref']}",
            accent=C_GREEN,
        ),
    ]
    ts = d.get("generado_en", "—")
    try:
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, AttributeError):
        pass

    return (
        cards, f"Actualizado: {ts}", ts_raw,
        _fig_mapa(sismos),
        _fig_lluvia(met.get("serie_horaria", [])),
        _fig_linea(oce.get("serie_horaria", []), "sst_c", C_CYAN, "°C"),
        _fig_linea(oce.get("serie_horaria", []), "corriente_vel_ms", C_GREEN, "m/s"),
    )


if __name__ == "__main__":
    if not DATA_FILE.exists():
        raise SystemExit("Sin datos. Ejecuta startup.py para generar la ingesta inicial.")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
