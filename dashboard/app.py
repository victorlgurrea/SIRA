"""Dashboard SIRA."""
from __future__ import annotations

import _bootstrap  # noqa: F401

import math
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, callback, ctx, dcc, html

from config import (  # noqa: E402
    ALLOW_DATA_REFRESH,
    API_BASE_URL,
    API_KEY,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_REFRESH_MS,
    DATA_FILE,
    MAPA,
    ZONA,
)
from core import read_dashboard  # noqa: E402

COLORES = {"MÍNIMO": "#2ECC71", "BAJO": "#F1C40F", "MODERADO": "#E67E22", "ALTO": "#E74C3C", "CRÍTICO": "#8B0000"}
BG = dict(paper_bgcolor="#1e293b", plot_bgcolor="#1e293b", font=dict(color="#e2e8f0"))
PANEL = dict(
    background="linear-gradient(145deg, #1e293b 0%, #172033 100%)",
    borderRadius="12px",
    padding="1.25rem",
    border="1px solid #334155",
    boxShadow="0 4px 16px rgba(0, 0, 0, 0.25)",
)
CARD = dict(
    **PANEL,
    display="flex",
    flexDirection="column",
    gap="0.35rem",
    transition="border-color 0.2s ease",
)
CARD_TITLE = dict(color="#94a3b8", fontSize="0.8rem", fontWeight="600", textTransform="uppercase", letterSpacing="0.06em")
CARD_VALUE = dict(fontSize="1.75rem", fontWeight="700", color="#f1f5f9", lineHeight="1.1")
CARD_DETAIL = dict(color="#cbd5e1", fontSize="0.82rem", lineHeight="1.45")
HELP = dict(color="#64748b", fontSize="0.75rem", margin="0.35rem 0 0", lineHeight="1.4")
BLOQUE = dict(**PANEL, borderTop="3px solid #38bdf8")
TOOLBAR = dict(
    display="flex", alignItems="center", flexWrap="wrap", gap="0.75rem",
    padding="0.75rem 1.25rem",
    marginTop="1rem", marginBottom="1.25rem",
    background="#1e293b", borderRadius="10px", border="1px solid #334155",
)
CONTENT = dict(maxWidth="1400px", margin="0 auto", padding="0 2rem", width="100%", boxSizing="border-box")
BTN_REFRESH = {
    "padding": "0.45rem 1.1rem",
    "background": "linear-gradient(135deg, #0284c7, #0ea5e9)",
    "color": "#fff", "border": "none", "borderRadius": "8px",
    "cursor": "pointer", "fontWeight": "600", "fontSize": "0.9rem",
    "boxShadow": "0 2px 8px rgba(14, 165, 233, 0.35)",
    **({} if ALLOW_DATA_REFRESH else {"display": "none"}),
}
HEADER = dict(
    background="linear-gradient(135deg, #0c4a6e 0%, #1e40af 35%, #0f172a 100%)",
    padding="2rem 2.5rem",
    borderBottom="3px solid #38bdf8",
    boxShadow="0 4px 24px rgba(56, 189, 248, 0.15)",
)
FOOTER = dict(
    background="linear-gradient(180deg, #0f172a 0%, #020617 100%)",
    borderTop="1px solid #334155",
    padding="1.25rem 2rem",
    textAlign="center",
    color="#64748b",
    fontSize="0.85rem",
    marginTop="auto",
)

app = Dash(
    __name__,
    title="SIRA — Sistema Ibérico de Riesgos y Alerta",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

MOBILE_CSS = """
body { margin: 0; overflow-x: hidden; -webkit-text-size-adjust: 100%; }
#react-entry-point, #react-entry-point > div { min-height: 100vh; }

@media (max-width: 640px) {
  .sira-header { padding: 1.25rem 1rem !important; }
  .sira-header-inner { width: 100% !important; }
  .sira-title { font-size: 1.75rem !important; letter-spacing: 0.08em !important; }
  .sira-subtitle { font-size: 0.95rem !important; }
  .sira-tags { font-size: 0.78rem !important; line-height: 1.45 !important; }
  #cards { grid-template-columns: 1fr !important; padding: 0.75rem 1rem 0.5rem !important; gap: 0.75rem !important; }
  .sira-content { padding: 0 1rem !important; }
  .sira-toolbar { flex-direction: column !important; align-items: stretch !important; gap: 0.5rem !important; }
  .sira-toolbar #ts { font-size: 0.82rem !important; width: 100%; }
  .sira-toolbar #btn { width: 100%; min-height: 44px; }
  .sira-charts { grid-template-columns: 1fr !important; gap: 0.75rem !important; padding-bottom: 1.5rem !important; }
  .sira-bloque { padding: 1rem !important; }
  .sira-graph { height: 260px !important; }
  .sira-graph--map { height: 300px !important; }
  .sira-footer { padding: 1rem !important; font-size: 0.78rem !important; }
  .sira-card-value { font-size: 1.45rem !important; }
  .sira-card { padding: 1rem !important; }
}

@media (max-width: 400px) {
  .sira-title { font-size: 1.5rem !important; }
  .sira-graph--map { height: 260px !important; }
  .sira-graph { height: 230px !important; }
}

@media (min-width: 641px) and (max-width: 900px) {
  #cards { grid-template-columns: repeat(2, 1fr) !important; padding-left: 1.25rem !important; padding-right: 1.25rem !important; }
  .sira-charts { grid-template-columns: 1fr !important; }
  .sira-content { padding: 0 1.25rem !important; }
}
"""

app.index_string = f"""
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <style>{MOBILE_CSS}</style>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
"""


def _card(t, v, d, h, accent="#38bdf8"):
    return html.Div(className="sira-card", style={**CARD, "borderLeft": f"4px solid {accent}"}, children=[
        html.Div(t, style=CARD_TITLE),
        html.Div(v, className="sira-card-value", style=CARD_VALUE),
        html.Div(d, style=CARD_DETAIL) if isinstance(d, str) else d,
        html.P(h, style=HELP),
    ])


def _dir_compass(grados) -> str:
    if grados is None or grados == "—":
        return "—"
    g = float(grados) % 360
    puntos = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
    cardinal = puntos[int((g + 22.5) / 45) % 8]
    return f"{g:.0f}° ({cardinal})"


def _regiones(reg: dict) -> html.Div:
    items = [
        ("Mediterráneo", reg.get("MEDITERRÁNEO", 0), "#f97316"),
        ("Cantábrico", reg.get("CANTÁBRICO", 0), "#38bdf8"),
        ("Atlántico", reg.get("ATLÁNTICO", 0), "#2dd4bf"),
    ]
    return html.Div(style={"display": "flex", "flexDirection": "column", "gap": "0.2rem"}, children=[
        html.Div([
            html.Span(n, style={"color": c, "fontWeight": "600"}),
            html.Span(f": {v}", style={"color": "#cbd5e1"}),
        ]) for n, v, c in items
    ])


def _bloque(gid, titulo, ayuda=None, full=False, accent="#38bdf8"):
    st = {**BLOQUE, "borderTopColor": accent, **({"gridColumn": "1 / -1"} if full else {})}
    children = [html.H4(titulo, style={"margin": 0, "color": "#f1f5f9", "fontSize": "1rem", "fontWeight": "600"})]
    if ayuda:
        children.append(html.P(ayuda, style=HELP))
    graph_cls = "sira-graph sira-graph--map" if full else "sira-graph"
    children.append(dcc.Graph(
        id=gid, className=graph_cls,
        style={"height": "380px" if full else "320px", "width": "100%"},
        config={"displayModeBar": False, "responsive": True},
    ))
    return html.Div(className="sira-bloque", style=st, children=children)


app.layout = html.Div(style={
    "background": "#0f172a", "minHeight": "100vh", "color": "#e2e8f0",
    "fontFamily": "Segoe UI, system-ui, sans-serif",
    "display": "flex", "flexDirection": "column", "overflowX": "hidden",
}, children=[
    html.Header(className="sira-header", style=HEADER, children=[
        html.Div(className="sira-header-inner", style={"maxWidth": "1400px", "margin": "0 auto", "width": "100%"}, children=[
            html.H1("SIRA", className="sira-title", style={
                "margin": 0,
                "fontSize": "2.5rem",
                "fontWeight": "700",
                "letterSpacing": "0.12em",
                "background": "linear-gradient(90deg, #7dd3fc, #38bdf8, #a5f3fc)",
                "WebkitBackgroundClip": "text",
                "WebkitTextFillColor": "transparent",
            }),
            html.P(
                "Sistema Ibérico de Riesgos y Alerta",
                className="sira-subtitle",
                style={"color": "#e2e8f0", "margin": "0.35rem 0 0", "fontSize": "1.05rem", "fontWeight": "500"},
            ),
            html.P(
                "Sismos · Cantábrico · Atlántico · Oceanografía · Meteorología",
                className="sira-tags",
                style={"color": "#94a3b8", "margin": "0.4rem 0 0", "fontSize": "0.9rem"},
            ),
        ]),
    ]),
    html.Main(style={"flex": "1", "width": "100%"}, children=[
        html.Div(id="cards", style={
            "display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))",
            "gap": "1rem", "padding": "1rem 2rem 0.5rem", "maxWidth": "1400px", "margin": "0 auto", "width": "100%",
            "boxSizing": "border-box",
        }),
        html.Div(className="sira-content", style=CONTENT, children=[
            html.Div(className="sira-toolbar", style=TOOLBAR, children=[
                html.Span(id="ts", style={"color": "#94a3b8", "fontSize": "0.9rem", "flex": "1", "minWidth": 0}),
                html.Button("Actualizar", id="btn", n_clicks=0, style=BTN_REFRESH),
            ]),
            dcc.Interval(id="tick", interval=DASHBOARD_REFRESH_MS),
            dcc.Interval(id="pulse", interval=500, n_intervals=0),
            dcc.Store(id="sismos-store"),
            html.Div(className="sira-charts", style={
                "display": "grid", "gridTemplateColumns": "1fr 1fr",
                "gap": "1rem", "paddingBottom": "2rem", "width": "100%",
            }, children=[
                _bloque(
                    "mapa", "Mapa sísmico — España",
                    f"Últimos {ZONA['dias_atras']} días · M≥{ZONA['magnitud_min']}.",
                    full=True, accent="#f97316",
                ),
                _bloque("riesgo", "Riesgo diario", "Score máximo (barras) y medio (línea) por día.", accent="#f97316"),
                _bloque("lluvia", "Previsión de lluvia", "AEMET con fallback Open-Meteo.", accent="#60a5fa"),
                _bloque("sst", "SST — Mar Mediterráneo", f"Temperatura superficial del mar · {ZONA['ciudad_ref']}.", accent="#38bdf8"),
                _bloque("corrientes", "Corrientes marinas", "Velocidad (m/s) y dirección de la corriente.", accent="#2dd4bf"),
            ]),
        ]),
    ]),
    html.Footer(className="sira-footer", style=FOOTER, children=[
        html.P("© 2026 SIRA — Sistema Ibérico de Riesgos y Alerta. Todos los derechos reservados.", style={"margin": 0}),
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


def _pulse_scale(tick: int) -> float:
    return 1.0 + 0.35 * (0.5 + 0.5 * math.sin(tick * 0.45))


def _fmt_sismo_fecha(ts) -> str:
    try:
        return pd.to_datetime(ts, utc=True).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, TypeError):
        return "—"


def _fig_mapa(sismos: list, pulse: float = 1.0) -> go.Figure:
    fig = go.Figure()
    df = pd.DataFrame(sismos) if sismos else pd.DataFrame()
    hoy_df = pd.DataFrame()

    for nivel, color in COLORES.items():
        sub = df[df["nivel_alerta"] == nivel] if not df.empty else pd.DataFrame()
        if sub.empty:
            continue
        reg_col = sub["region"] if "region" in sub.columns else [""] * len(sub)
        fechas = [_fmt_sismo_fecha(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else ["—"] * len(sub)
        hoy_mask = [_es_sismo_hoy(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else [False] * len(sub)
        base = sub["magnitud"] * 2 + 5
        sizes = [b * pulse if h else b for b, h in zip(base, hoy_mask)]
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
                size=[s * pulse * 2.4 for s in halo],
                color="rgba(248, 113, 113, 0.35)",
                line=dict(width=1.5, color="#f87171"),
            ),
            hoverinfo="skip", legendgroup="hoy",
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
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        legend=dict(title="Alerta", orientation="h", yanchor="bottom", y=1.02, x=0),
        autosize=True,
        **BG,
    )
    return fig


def _fig_riesgo(sismos: list) -> go.Figure:
    fig = go.Figure()
    if sismos:
        dd = pd.DataFrame(sismos)
        dd["fecha"] = pd.to_datetime(dd["timestamp"]).dt.date
        g = dd.groupby("fecha").agg(mx=("score_total", "max"), md=("score_total", "mean")).reset_index()
        fig.add_trace(go.Bar(x=g["fecha"], y=g["mx"], name="Máx.", marker_color="#f97316"))
        fig.add_trace(go.Scatter(x=g["fecha"], y=g["md"], name="Medio", line=dict(color="#38bdf8")))
    fig.update_layout(margin=dict(t=10, b=0, l=0, r=0), autosize=True, yaxis_title="Score", **BG)
    return fig


def _fig_linea(serie: list, campo: str, color: str, unidad: str) -> go.Figure:
    fig = go.Figure()
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(x=s["timestamp"], y=s[campo], mode="lines", line=dict(color=color)))
    fig.update_layout(margin=dict(t=10, b=0, l=0, r=0), autosize=True, yaxis_title=unidad, **BG)
    return fig


def _fig_lluvia(serie: list) -> go.Figure:
    fig = go.Figure()
    yaxis = dict(title="mm", rangemode="tozero")
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        precip = s["precip_mm"].fillna(0)
        fig.add_trace(go.Bar(x=s["timestamp"], y=precip, name="mm", marker_color="#60a5fa"))
        if s["prob_precip_pct"].notna().any():
            fig.add_trace(go.Scatter(x=s["timestamp"], y=s["prob_precip_pct"], name="%", yaxis="y2", line=dict(color="#a78bfa")))
        max_precip = float(precip.max())
        yaxis["range"] = [0, max(1.0, max_precip * 1.15)]
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        autosize=True,
        yaxis=yaxis,
        yaxis2=dict(overlaying="y", side="right", range=[0, 100], title="%"),
        **BG,
    )
    return fig


@callback(
    Output("cards", "children"), Output("ts", "children"), Output("sismos-store", "data"),
    Output("riesgo", "figure"), Output("lluvia", "figure"),
    Output("sst", "figure"), Output("corrientes", "figure"),
    Input("tick", "n_intervals"), Input("btn", "n_clicks"),
)
def refresh(_, clicks):
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
    sismos, st = d.get("sismos", []), d.get("estadisticas", {})
    oce, met = d.get("oceanografia", {}), d.get("meteorologia", {})
    res_oce, res_met = oce.get("resumen", {}), met.get("resumen", {})
    reg = st.get("por_region", {})

    cards = [
        _card(
            "Sismos", str(st.get("n_sismos", 0)),
            _regiones(reg),
            f"M≥{ZONA['magnitud_min']}, últimos {ZONA['dias_atras']} días · fuente USGS",
            accent="#f97316",
        ),
        _card(
            "Magnitud máx.", f"{st.get('mag_max', 0):.1f}",
            f"Score {st.get('score_max', 0)} · {st.get('n_alto_critico', 0)} en nivel Alto o Crítico",
            "El score combina magnitud, profundidad, distancia a Valencia y zona submarina (0–100+). "
            "Alto/Crítico: eventos con score ≥ 55.",
            accent="#ef4444",
        ),
        _card(
            "Lluvia 24h", f"{res_met.get('precip_prox_24h_mm', '—')} mm",
            f"Prob. máx. {res_met.get('prob_max_pct', '—')}% · {met.get('fuente', '—')}",
            met.get("municipio", ZONA["ciudad_ref"]),
            accent="#60a5fa",
        ),
        _card(
            "SST — Mar Mediterráneo", f"{res_oce.get('sst_actual_c', '—')} °C",
            f"Temperatura superficial del mar · anomalía {res_oce.get('anomalia_c', '—')} °C",
            f"Punto de referencia: {ZONA['ciudad_ref']} · Open-Meteo marine",
            accent="#38bdf8",
        ),
        _card(
            "Corriente marina", f"{res_oce.get('corriente_vel_ms', '—')} m/s",
            html.Div([
                html.Span("Dirección: ", style={"color": "#94a3b8"}),
                html.Span(
                    _dir_compass(res_oce.get("corriente_dir_grados")),
                    style={"color": "#2dd4bf", "fontWeight": "600"},
                ),
            ]),
            f"Rumbo de la corriente en el Mediterráneo occidental · {ZONA['ciudad_ref']}",
            accent="#2dd4bf",
        ),
    ]
    ts = d.get("generado_en", "—")
    try:
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, AttributeError):
        pass

    return (
        cards, f"Actualizado: {ts}", sismos,
        _fig_riesgo(sismos), _fig_lluvia(met.get("serie_horaria", [])),
        _fig_linea(oce.get("serie_horaria", []), "sst_c", "#38bdf8", "°C"),
        _fig_linea(oce.get("serie_horaria", []), "corriente_vel_ms", "#2dd4bf", "m/s"),
    )


@callback(
    Output("mapa", "figure"),
    Input("sismos-store", "data"),
    Input("pulse", "n_intervals"),
)
def update_mapa(sismos, pulse_n):
    return _fig_mapa(sismos or [], pulse=_pulse_scale(pulse_n or 0))


if __name__ == "__main__":
    if not DATA_FILE.exists():
        raise SystemExit("Sin datos. Ejecuta startup.py para generar la ingesta inicial.")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
