"""Dashboard SIRA."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, callback, ctx, dcc, html

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
from config import API_BASE_URL, API_KEY, DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_REFRESH_MS, DATA_FILE, MAPA, ZONA  # noqa: E402
from core import read_dashboard  # noqa: E402

COLORES = {"MÍNIMO": "#2ECC71", "BAJO": "#F1C40F", "MODERADO": "#E67E22", "ALTO": "#E74C3C", "CRÍTICO": "#8B0000"}
BG = dict(paper_bgcolor="#1e293b", plot_bgcolor="#1e293b", font=dict(color="#e2e8f0"))
PANEL = dict(background="#1e293b", borderRadius="8px", padding="1rem")
HELP = dict(color="#94a3b8", fontSize="0.78rem", margin="0.5rem 0 0")

app = Dash(__name__, title="SIRA — Sistema Ibérico de Riesgos y Alerta")


def _card(t, v, d, h):
    return html.Div(style={**PANEL, "border": "1px solid #334155"}, children=[
        html.Div(t, style={"color": "#94a3b8", "fontSize": "0.85rem"}),
        html.Div(v, style={"fontSize": "1.5rem", "fontWeight": "bold"}),
        html.Div(d, style={"color": "#64748b", "fontSize": "0.8rem"}),
        html.P(h, style=HELP),
    ])


def _bloque(gid, titulo, ayuda, full=False):
    st = {**PANEL, **({"gridColumn": "1 / -1"} if full else {})}
    return html.Div(style=st, children=[
        html.H4(titulo, style={"margin": 0}), html.P(ayuda, style=HELP),
        dcc.Graph(id=gid, style={"height": "380px" if full else "320px"}),
    ])


app.layout = html.Div(style={"background": "#0f172a", "minHeight": "100vh", "color": "#e2e8f0", "fontFamily": "Segoe UI"}, children=[
    html.Header(style={"padding": "1.5rem 2rem", "borderBottom": "3px solid #38bdf8"}, children=[
        html.H1("SIRA", style={"margin": 0, "color": "#7dd3fc"}),
        html.P("Sistema Ibérico de Riesgos y Alerta · sismos · Cantábrico · Atlántico · oceanografía · meteorología",
               style={"color": "#94a3b8", "margin": "0.5rem 0 0"}),
    ]),
    html.Div(id="cards", style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))", "gap": "1rem", "padding": "1rem 2rem 0"}),
    html.Div(style={"padding": "0.5rem 2rem"}, children=[
        html.Span(id="ts"), html.Button("Actualizar", id="btn", n_clicks=0, style={"marginLeft": "1rem"}),
    ]),
    dcc.Interval(id="tick", interval=DASHBOARD_REFRESH_MS),
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "1rem", "padding": "0 2rem 2rem"}, children=[
        _bloque("mapa", "Mapa sísmico — España", "Color = alerta. Estrellas = Madrid y Valencia.", full=True),
        _bloque("riesgo", "Riesgo diario", "Score máximo (barras) y medio (línea) por día."),
        _bloque("lluvia", "Previsión de lluvia", "AEMET con fallback Open-Meteo."),
        _bloque("sst", f"SST — {ZONA['ciudad_ref']}", "Temperatura superficial del mar."),
        _bloque("corrientes", "Corrientes", "Velocidad en m/s."),
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


def _fig_mapa(sismos: list) -> go.Figure:
    fig = go.Figure()
    df = pd.DataFrame(sismos) if sismos else pd.DataFrame()
    for nivel, color in COLORES.items():
        sub = df[df["nivel_alerta"] == nivel] if not df.empty else pd.DataFrame()
        if sub.empty:
            continue
        reg_col = sub["region"] if "region" in sub.columns else [""] * len(sub)
        fig.add_trace(go.Scattergeo(
            lat=sub["lat"], lon=sub["lon"], mode="markers", name=nivel,
            marker=dict(size=sub["magnitud"] * 2 + 5, color=color, line=dict(width=0.5, color="white")),
            text=sub["lugar"],
            customdata=list(zip(sub["magnitud"], sub["score_total"], reg_col)),
            hovertemplate="%{text}<br>Mag %{customdata[0]} · Score %{customdata[1]} · %{customdata[2]}<extra></extra>",
        ))
    for lat, lon, name, color in (
        (MAPA["lat_centro"], MAPA["lon_centro"], MAPA["ciudad_centro"], "gold"),
        (ZONA["lat_ref"], ZONA["lon_ref"], ZONA["ciudad_ref"], "#38bdf8"),
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
        showland=True, landcolor="#1a2332",
        showocean=True, oceancolor="#e2e8f0",
        showcountries=True, countrycolor="#64748b", coastlinecolor="#94a3b8",
    )
    fig.update_layout(margin=dict(t=10, b=0), legend=dict(title="Alerta"), **BG)
    return fig


def _fig_riesgo(sismos: list) -> go.Figure:
    fig = go.Figure()
    if sismos:
        dd = pd.DataFrame(sismos)
        dd["fecha"] = pd.to_datetime(dd["timestamp"]).dt.date
        g = dd.groupby("fecha").agg(mx=("score_total", "max"), md=("score_total", "mean")).reset_index()
        fig.add_trace(go.Bar(x=g["fecha"], y=g["mx"], name="Máx.", marker_color="#f97316"))
        fig.add_trace(go.Scatter(x=g["fecha"], y=g["md"], name="Medio", line=dict(color="#38bdf8")))
    fig.update_layout(margin=dict(t=10, b=0), yaxis_title="Score", **BG)
    return fig


def _fig_linea(serie: list, campo: str, color: str, unidad: str) -> go.Figure:
    fig = go.Figure()
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(x=s["timestamp"], y=s[campo], mode="lines", line=dict(color=color)))
    fig.update_layout(margin=dict(t=10, b=0), yaxis_title=unidad, **BG)
    return fig


def _fig_lluvia(serie: list) -> go.Figure:
    fig = go.Figure()
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Bar(x=s["timestamp"], y=s["precip_mm"], name="mm", marker_color="#60a5fa"))
        if s["prob_precip_pct"].notna().any():
            fig.add_trace(go.Scatter(x=s["timestamp"], y=s["prob_precip_pct"], name="%", yaxis="y2", line=dict(color="#a78bfa")))
    fig.update_layout(margin=dict(t=10, b=0), yaxis2=dict(overlaying="y", side="right", range=[0, 100]), **BG)
    return fig


@callback(
    Output("cards", "children"), Output("ts", "children"),
    Output("mapa", "figure"), Output("riesgo", "figure"), Output("lluvia", "figure"),
    Output("sst", "figure"), Output("corrientes", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"),
)
def refresh(_, clicks):
    if ctx.triggered_id == "btn" and clicks:
        try:
            requests.post(f"{API_BASE_URL}/api/actualizar", headers={"X-API-Key": API_KEY} if API_KEY else {}, timeout=120)
        except requests.RequestException:
            pass

    d = _load()
    sismos, st = d.get("sismos", []), d.get("estadisticas", {})
    oce, met = d.get("oceanografia", {}), d.get("meteorologia", {})
    res_oce, res_met = oce.get("resumen", {}), met.get("resumen", {})
    reg = st.get("por_region", {})

    cards = [
        _card("Sismos", str(st.get("n_sismos", 0)), f"Med:{reg.get('MEDITERRÁNEO', 0)} Cant:{reg.get('CANTÁBRICO', 0)} Atl:{reg.get('ATLÁNTICO', 0)}", f"M≥{ZONA['magnitud_min']}, {ZONA['dias_atras']} días USGS"),
        _card("Magnitud máx.", f"{st.get('mag_max', 0):.1f}", f"Score {st.get('score_max', 0)} · Alto/Crítico {st.get('n_alto_critico', 0)}", f"Referencia {ZONA['ciudad_ref']}"),
        _card("Lluvia 24h", f"{res_met.get('precip_prox_24h_mm', '—')} mm", f"Prob. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}", met.get("municipio", ZONA["ciudad_ref"])),
        _card("SST", f"{res_oce.get('sst_actual_c', '—')} °C", f"Anomalía {res_oce.get('anomalia_c', '—')} °C", "Open-Meteo marine"),
        _card("Corriente", f"{res_oce.get('corriente_vel_ms', '—')} m/s", f"{res_oce.get('corriente_dir_grados', '—')}°", "Costa valenciana"),
    ]
    ts = d.get("generado_en", "—")
    try:
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, AttributeError):
        pass

    return (
        cards, f"Actualizado: {ts}",
        _fig_mapa(sismos), _fig_riesgo(sismos), _fig_lluvia(met.get("serie_horaria", [])),
        _fig_linea(oce.get("serie_horaria", []), "sst_c", "#38bdf8", "°C"),
        _fig_linea(oce.get("serie_horaria", []), "corriente_vel_ms", "#2dd4bf", "m/s"),
    )


if __name__ == "__main__":
    if not DATA_FILE.exists():
        from ingesta import ejecutar_ingesta
        ejecutar_ingesta()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
