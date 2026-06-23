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

# Paleta alineada con logo_sira_2.svg
C_NAVY = "#0a1628"
C_NAVY_MID = "#0f2847"
C_PANEL = "#0f2847"
C_BORDER = "#1e4976"
C_CYAN = "#22d3ee"
C_TEAL = "#06b6d4"
C_ORANGE = "#f97316"
C_GREEN = "#22c55e"
C_TEXT = "#f0f9ff"
C_MUTED = "#94a3b8"

COLORES = {"MÍNIMO": "#2ECC71", "BAJO": "#F1C40F", "MODERADO": "#E67E22", "ALTO": "#E74C3C", "CRÍTICO": "#8B0000"}
BG = dict(paper_bgcolor=C_NAVY_MID, plot_bgcolor=C_NAVY_MID, font=dict(color=C_TEXT))
PANEL = dict(
    background=f"linear-gradient(145deg, {C_NAVY_MID} 0%, {C_NAVY} 100%)",
    borderRadius="14px",
    padding="1.25rem",
    border=f"1px solid {C_BORDER}",
    boxShadow="0 4px 20px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(34, 211, 238, 0.06)",
)
CARD = dict(
    **PANEL,
    display="flex",
    flexDirection="column",
    gap="0.35rem",
    transition="border-color 0.2s ease, box-shadow 0.2s ease",
)
CARD_TITLE = dict(color=C_MUTED, fontSize="0.8rem", fontWeight="600", textTransform="uppercase", letterSpacing="0.06em")
CARD_VALUE = dict(fontSize="1.75rem", fontWeight="700", color=C_TEXT, lineHeight="1.1")
CARD_DETAIL = dict(color="#cbd5e1", fontSize="0.82rem", lineHeight="1.45")
HELP = dict(color="#64748b", fontSize="0.75rem", margin="0.35rem 0 0", lineHeight="1.4")
BLOQUE = dict(**PANEL, borderTop=f"3px solid {C_CYAN}")
TOOLBAR = dict(
    display="flex", alignItems="center", flexWrap="wrap", gap="0.75rem",
    padding="0.75rem 1.25rem",
    marginTop="1rem", marginBottom="1.25rem",
    background=f"linear-gradient(135deg, {C_NAVY_MID}, {C_NAVY})",
    borderRadius="12px",
    border=f"1px solid {C_BORDER}",
    boxShadow="0 2px 12px rgba(6, 182, 212, 0.08)",
)
CONTENT = dict(maxWidth="1400px", margin="0 auto", padding="0 2rem", width="100%", boxSizing="border-box")
BTN_REFRESH = {
    "padding": "0.45rem 1.25rem",
    "background": f"linear-gradient(135deg, #ea580c, {C_ORANGE})",
    "color": "#fff", "border": "none", "borderRadius": "10px",
    "cursor": "pointer", "fontWeight": "600", "fontSize": "0.9rem",
    "boxShadow": "0 2px 12px rgba(249, 115, 22, 0.4)",
    **({} if ALLOW_DATA_REFRESH else {"display": "none"}),
}
FOOTER = dict(
    background=f"linear-gradient(180deg, {C_NAVY} 0%, #050a12 100%)",
    borderTop=f"1px solid {C_BORDER}",
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

THEME_CSS = """
:root {
  --sira-navy: #0a1628;
  --sira-navy-mid: #0f2847;
  --sira-cyan: #22d3ee;
  --sira-teal: #06b6d4;
  --sira-orange: #f97316;
  --sira-green: #22c55e;
  --sira-text: #f0f9ff;
  --sira-muted: #94a3b8;
  --sira-border: #1e4976;
}

body {
  margin: 0;
  overflow-x: hidden;
  -webkit-text-size-adjust: 100%;
  background: var(--sira-navy);
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
}

#react-entry-point, #react-entry-point > div { min-height: 100vh; }

.sira-page {
  background: linear-gradient(180deg, #050a12 0%, var(--sira-navy) 40%, #0f2847 100%);
  min-height: 100vh;
}

.sira-header {
  position: relative;
  padding: 1.5rem 2rem;
  background: linear-gradient(135deg, #050a12 0%, var(--sira-navy-mid) 45%, var(--sira-navy) 100%);
  box-shadow: 0 8px 32px rgba(6, 182, 212, 0.1);
}

.sira-header::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--sira-orange), var(--sira-cyan), var(--sira-green));
}

.sira-header-inner {
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.sira-header-brand {
  display: flex;
  align-items: center;
  gap: 1.75rem;
}

.sira-logo {
  display: block;
  width: 100%;
  max-width: 340px;
  height: auto;
  object-fit: contain;
  filter: drop-shadow(0 6px 16px rgba(0, 0, 0, 0.45));
  flex-shrink: 0;
}

.sira-header-text { flex: 1; min-width: 0; }

.sira-subtitle {
  margin: 0;
  color: #e0f2fe;
  font-size: 1.1rem;
  font-weight: 500;
  line-height: 1.35;
}

.sira-tags {
  margin: 0.4rem 0 0;
  color: var(--sira-muted);
  font-size: 0.88rem;
  line-height: 1.5;
}

.sira-card:hover {
  box-shadow: 0 6px 24px rgba(6, 182, 212, 0.12), 0 0 0 1px rgba(34, 211, 238, 0.1) !important;
}

@media (max-width: 640px) {
  .sira-header { padding: 1rem !important; }
  .sira-header-brand {
    flex-direction: column;
    text-align: center;
    gap: 0.75rem;
  }
  .sira-logo { max-width: 240px !important; }
  .sira-subtitle { font-size: 0.92rem !important; }
  .sira-tags { font-size: 0.76rem !important; }
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
  .sira-logo { max-width: 200px !important; }
  .sira-graph--map { height: 260px !important; }
  .sira-graph { height: 230px !important; }
}

@media (min-width: 641px) and (max-width: 900px) {
  .sira-header-brand { gap: 1.25rem; }
  .sira-logo { max-width: 280px; }
  #cards { grid-template-columns: repeat(2, 1fr) !important; padding-left: 1.25rem !important; padding-right: 1.25rem !important; }
  .sira-charts { grid-template-columns: 1fr !important; }
  .sira-content { padding: 0 1.25rem !important; }
}

@media (min-width: 901px) {
  .sira-logo { max-width: 380px; }
  .sira-charts { grid-template-columns: 1fr 1fr; }
}
"""

MOBILE_CSS = THEME_CSS

app.index_string = f"""
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <link rel="icon" href="/assets/logo_sira_2.svg" type="image/svg+xml">
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


def _card(t, v, d, h, accent=C_CYAN):
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
        ("Mediterráneo", reg.get("MEDITERRÁNEO", 0), C_ORANGE),
        ("Cantábrico", reg.get("CANTÁBRICO", 0), C_GREEN),
        ("Atlántico", reg.get("ATLÁNTICO", 0), C_CYAN),
    ]
    return html.Div(style={"display": "flex", "flexDirection": "column", "gap": "0.2rem"}, children=[
        html.Div([
            html.Span(n, style={"color": c, "fontWeight": "600"}),
            html.Span(f": {v}", style={"color": "#cbd5e1"}),
        ]) for n, v, c in items
    ])


def _bloque(gid, titulo, ayuda=None, full=False, accent=C_CYAN):
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


app.layout = html.Div(className="sira-page", style={
    "minHeight": "100vh", "color": C_TEXT,
    "display": "flex", "flexDirection": "column", "overflowX": "hidden",
}, children=[
    html.Header(className="sira-header", children=[
        html.Div(className="sira-header-inner", children=[
            html.Div(className="sira-header-brand", children=[
                html.Img(src="/assets/logo_sira_2.svg", className="sira-logo", alt="SIRA — Sistema Ibérico de Riesgos y Alerta"),
                html.Div(className="sira-header-text", children=[
                    html.P(
                        "Sistema Ibérico de Riesgos y Alerta",
                        className="sira-subtitle",
                    ),
                    html.P(
                        "Sismos · Cantábrico · Atlántico · Oceanografía · Meteorología",
                        className="sira-tags",
                    ),
                ]),
            ]),
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
                    full=True, accent=C_ORANGE,
                ),
                _bloque("riesgo", "Riesgo diario", "Score máximo (barras) y medio (línea) por día.", accent=C_ORANGE),
                _bloque("lluvia", "Previsión de lluvia", "AEMET con fallback Open-Meteo.", accent=C_TEAL),
                _bloque("sst", "SST — Mar Mediterráneo", f"Temperatura superficial del mar · {ZONA['ciudad_ref']}.", accent=C_CYAN),
                _bloque("corrientes", "Corrientes marinas", "Velocidad (m/s) y dirección de la corriente.", accent=C_GREEN),
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
        showcountries=True, countrycolor=C_BORDER, coastlinecolor=C_MUTED,
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
        fig.add_trace(go.Bar(x=g["fecha"], y=g["mx"], name="Máx.", marker_color=C_ORANGE))
        fig.add_trace(go.Scatter(x=g["fecha"], y=g["md"], name="Medio", line=dict(color=C_CYAN)))
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
            accent=C_ORANGE,
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
            accent=C_TEAL,
        ),
        _card(
            "SST — Mar Mediterráneo", f"{res_oce.get('sst_actual_c', '—')} °C",
            f"Temperatura superficial del mar · anomalía {res_oce.get('anomalia_c', '—')} °C",
            f"Punto de referencia: {ZONA['ciudad_ref']} · Open-Meteo marine",
            accent=C_CYAN,
        ),
        _card(
            "Corriente marina", f"{res_oce.get('corriente_vel_ms', '—')} m/s",
            html.Div([
                html.Span("Dirección: ", style={"color": C_MUTED}),
                html.Span(
                    _dir_compass(res_oce.get("corriente_dir_grados")),
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
        cards, f"Actualizado: {ts}", sismos,
        _fig_riesgo(sismos), _fig_lluvia(met.get("serie_horaria", [])),
        _fig_linea(oce.get("serie_horaria", []), "sst_c", C_CYAN, "°C"),
        _fig_linea(oce.get("serie_horaria", []), "corriente_vel_ms", C_GREEN, "m/s"),
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
