"""Fachada de figuras Plotly del dashboard SIRA.

Reexporta el mapa desde map_fig; mantiene las series temporales y el mapa térmico.
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from charts.map_fig import es_sismo_hoy, fig_mapa, fmt_sismo_fecha, geo_layout
from sira.infrastructure.persistence.sqlite import get_historial_municipio
from sira.infrastructure.geo.ccaa_mapa import anadir_bordes_ccaa, anadir_bordes_provincias
from sira.infrastructure.geo.es import (
    CCAA_PROVINCIAS,
    ccaa_de_provincia,
    projection_scale_for_viewport,
    provincias,
    viewport_ccaa,
)
from ui.components import dir_compass
from ui.theme import (
    C_CYAN,
    C_GREEN,
    C_MUTED,
    C_ORANGE,
    C_TEAL,
    chart_muted,
    chart_text,
    plotly_bg,
)

# Reexportaciones públicas (imports existentes: from charts.figures import …)
__all__ = [
    "es_sismo_hoy",
    "fmt_sismo_fecha",
    "geo_layout",
    "fig_mapa",
    "fig_corrientes",
    "fig_linea",
    "fig_historial",
    "fig_lluvia",
    "fig_termico_ccaa",
    "xaxis_lluvia",
]

SEMAFORO_COLORES = {
    "VERDE": "#22c55e",
    "AMARILLO": "#eab308",
    "NARANJA": "#f97316",
    "ROJO": "#ef4444",
}

_MESES_EJE_LLUVIA = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_PROV_BORDES_FILE = Path(__file__).resolve().parent.parent / "data" / "geo" / "provincias_bordes.json"
_TEMP_COLORSCALE = [
    (-20.0, "#f8fafc"),
    (15.0, "#fde047"),
    (25.0, "#f59e0b"),
    (32.0, "#f97316"),
    (38.0, "#ef4444"),
    (50.0, "#b91c1c"),
]


# ---------------------------------------------------------------------------
# Helpers (series / térmico)
# ---------------------------------------------------------------------------

def color_temp(temp_c: float | None) -> str:
    if temp_c is None:
        return "rgba(100,116,139,0.28)"
    color = _TEMP_COLORSCALE[0][1]
    for threshold, c in _TEMP_COLORSCALE:
        if temp_c >= threshold:
            color = c
    return color


def fmt_hora_pico(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime("%d-%m %H:%M")
    except ValueError:
        return "—"


@lru_cache(maxsize=1)
def _prov_rings() -> dict[str, dict]:
    if not _PROV_BORDES_FILE.is_file():
        return {}
    try:
        data = json.loads(_PROV_BORDES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for feat in data.get("features", []):
        pid = str(feat.get("id") or "").zfill(2)
        if pid:
            out[pid] = feat
    return out


def color_sst(temp_c: float | None) -> str:
    if temp_c is None:
        return C_MUTED
    if temp_c >= 26:
        return SEMAFORO_COLORES["ROJO"]
    if temp_c >= 23:
        return SEMAFORO_COLORES["NARANJA"]
    if temp_c >= 20:
        return SEMAFORO_COLORES["AMARILLO"]
    return SEMAFORO_COLORES["VERDE"]


def color_corriente(vel_ms: float | None) -> str:
    if vel_ms is None:
        return C_MUTED
    if vel_ms >= 1.0:
        return SEMAFORO_COLORES["ROJO"]
    if vel_ms >= 0.6:
        return SEMAFORO_COLORES["NARANJA"]
    if vel_ms >= 0.3:
        return SEMAFORO_COLORES["AMARILLO"]
    return SEMAFORO_COLORES["VERDE"]


def annots_ultima_con_semaforo(texto: str, color_dot: str, *, theme: str = "dark") -> list[dict]:
    pad = max(72, int(len(texto) * 6.2))
    txt_color = chart_text(theme)
    return [
        dict(
            text=texto,
            xref="paper", yref="paper", x=1, y=1.12,
            xanchor="right", showarrow=False,
            font=dict(color=txt_color, size=11),
        ),
        dict(
            text="●",
            xref="paper", yref="paper", x=1, y=1.12,
            xanchor="right", xshift=-pad, showarrow=False,
            font=dict(color=color_dot, size=13),
        ),
    ]


# ---------------------------------------------------------------------------
# Figuras de series temporales
# ---------------------------------------------------------------------------

def fig_corrientes(serie: list, uirev: str, *, theme: str = "dark") -> go.Figure:
    fig = go.Figure()
    dir_txt = "—"
    ult_txt = "Última: — m/s"
    dot_color = chart_muted(theme)
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=s["timestamp"], y=s["corriente_vel_ms"],
            mode="lines", name="m/s", line=dict(color=C_GREEN),
        ))
        vel = s["corriente_vel_ms"].dropna()
        if not vel.empty:
            ult_val = float(vel.iloc[-1])
            dot_color = color_corriente(ult_val)
            ult_txt = f"Última: {ult_val:.2f} m/s"
        if s["corriente_dir_grados"].notna().any():
            dir_txt = dir_compass(s["corriente_dir_grados"].dropna().iloc[-1])
    annotations = [
        dict(
            text=f"Dirección: {dir_txt}",
            xref="paper", yref="paper", x=0, y=1.12,
            showarrow=False, font=dict(color=C_GREEN, size=11),
        ),
        *annots_ultima_con_semaforo(ult_txt, dot_color, theme=theme),
    ]
    fig.update_layout(
        margin=dict(t=28, b=0, l=0, r=0), autosize=True,
        yaxis_title="m/s", uirevision=uirev, annotations=annotations, **plotly_bg(theme),
    )
    return fig


def fig_linea(serie: list, campo: str, color: str, unidad: str, uirev: str, *, con_semaforo_sst: bool = False, theme: str = "dark") -> go.Figure:
    fig = go.Figure()
    ult_txt = f"Última: — {unidad}"
    dot_color = chart_muted(theme)
    if serie:
        s = pd.DataFrame(serie)
        s["timestamp"] = pd.to_datetime(s["timestamp"], errors="coerce")
        fig.add_trace(go.Scatter(x=s["timestamp"], y=s[campo], mode="lines", line=dict(color=color)))
        vals = s[campo].dropna()
        if not vals.empty:
            ult_val = float(vals.iloc[-1])
            ult_txt = f"Última: {ult_val:.2f} {unidad}"
            if con_semaforo_sst:
                dot_color = color_sst(ult_val)
    if con_semaforo_sst:
        annotations = annots_ultima_con_semaforo(ult_txt, dot_color, theme=theme)
    else:
        annotations = [dict(
            text=ult_txt, xref="paper", yref="paper", x=1, y=1.12,
            xanchor="right", showarrow=False, font=dict(color=chart_text(theme), size=11),
        )]
    fig.update_layout(
        margin=dict(t=28, b=0, l=0, r=0), autosize=True,
        yaxis_title=unidad, uirevision=uirev, annotations=annotations, **plotly_bg(theme),
    )
    return fig


def fig_historial(municipio_id: str, default_muni: str, uirev: str, *, theme: str = "dark") -> go.Figure:
    fig = go.Figure()
    mid = str(municipio_id or default_muni).zfill(5)
    serie = get_historial_municipio(mid, 30)
    if serie:
        fechas = [r["fecha"] for r in serie]
        fig.add_trace(go.Scatter(
            x=fechas, y=[r["score_sismo_max"] for r in serie],
            mode="lines+markers", name="Score sísmico máx.", line=dict(color=C_ORANGE),
        ))
        fig.add_trace(go.Scatter(
            x=fechas, y=[r["indice_impacto_local"] for r in serie],
            mode="lines+markers", name="Impacto local %", line=dict(color=C_CYAN), yaxis="y2",
        ))
        fig.add_trace(go.Scatter(
            x=fechas, y=[r["indice_riesgo_meteo"] for r in serie],
            mode="lines+markers", name="Índice riesgo meteo", line=dict(color=C_TEAL, dash="dot"), yaxis="y2",
        ))
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0), autosize=True, uirevision=uirev,
        yaxis=dict(title="Score", rangemode="tozero"),
        yaxis2=dict(title="Índice / %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02), **plotly_bg(theme),
    )
    return fig


def xaxis_lluvia(timestamps: pd.Series, *, theme: str = "dark") -> dict:
    ts = timestamps.dropna().sort_values().reset_index(drop=True)
    if ts.empty:
        return {"type": "date"}

    pick_idx = [0]
    for i in range(1, len(ts)):
        dt = pd.Timestamp(ts.iloc[i])
        if dt.minute != 0 or dt.hour % 6 != 0:
            continue
        last = pd.Timestamp(ts.iloc[pick_idx[-1]])
        if (dt - last).total_seconds() >= 5 * 3600:
            pick_idx.append(i)

    tickvals = ts.iloc[pick_idx]
    ticktext: list[str] = []
    prev_date = None
    for i, tv in enumerate(tickvals):
        dt = pd.Timestamp(tv)
        d = dt.date()
        if i == 0 or prev_date is None or d != prev_date:
            mes = _MESES_EJE_LLUVIA[dt.month - 1]
            ticktext.append(f"{dt.day:02d}-{mes} {dt.strftime('%H:%M')}")
        else:
            ticktext.append(dt.strftime("%H:%M"))
        prev_date = d

    return {
        "type": "date",
        "tickmode": "array",
        "tickvals": tickvals.tolist(),
        "ticktext": ticktext,
        "tickangle": -90,
        "tickfont": dict(size=9, color=chart_muted(theme)),
    }


def fig_lluvia(serie: list, *, theme: str = "dark") -> go.Figure:
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
        x = xaxis_lluvia(s["timestamp"], theme=theme)
    else:
        x = {"type": "date"}
    fig.update_layout(
        margin=dict(t=6, b=42, l=4, r=4), autosize=True, showlegend=False,
        xaxis=x, yaxis=yaxis,
        yaxis2=dict(overlaying="y", side="right", range=[0, 100], title=dict(text="%", font=dict(size=10)), tickfont=dict(size=9)),
        uirevision="sira-lluvia", **plotly_bg(theme),
    )
    return fig


def fig_termico_ccaa(
    provincia_id: str | None,
    termico_data: dict | None,
    *,
    uirev: str = "sira-termico-ccaa",
    theme: str = "dark",
) -> go.Figure:
    """Mapa coroplético de temperatura máxima prevista (24 h) por provincia de la CCAA."""
    fig = go.Figure()
    pid_sel = str(provincia_id or "").zfill(2)
    ccaa_id = ccaa_de_provincia(pid_sel)
    if not ccaa_id:
        fig.update_layout(margin=dict(t=10, b=0, l=0, r=0), autosize=True, uirevision=uirev, **plotly_bg(theme))
        return fig

    por_prov = {
        str(p.get("provincia_id") or "").zfill(2): p
        for p in (termico_data or {}).get("provincias") or []
        if isinstance(p, dict)
    }
    prov_ids = [str(p).zfill(2) for p in CCAA_PROVINCIAS.get(ccaa_id, [])]
    feat_by_pid = _prov_rings()
    pmeta = {str(p["id"]).zfill(2): p.get("nombre", str(p["id"])) for p in provincias()}

    for pid in prov_ids:
        feat = feat_by_pid.get(pid)
        if not feat:
            continue
        row = por_prov.get(pid, {})
        tmax = row.get("temp_max_c")
        sens = row.get("sensacion_max_c")
        hora = fmt_hora_pico(row.get("hora_pico"))
        fuente = str(row.get("fuente") or "—")
        color = color_temp(tmax if tmax is None else float(tmax))
        ttxt = f"{float(tmax):.1f} °C" if tmax is not None else "—"
        stxt = f"{float(sens):.1f} °C" if sens is not None else "—"
        prov_name = pmeta.get(pid, row.get("provincia") or pid)
        for ring in feat.get("rings", []):
            lats = ring.get("lat") or []
            lons = ring.get("lon") or []
            if len(lats) < 3:
                continue
            fig.add_trace(
                go.Scattergeo(
                    lat=lats, lon=lons, mode="lines", fill="toself", fillcolor=color,
                    line=dict(color="rgba(15,23,42,0.45)", width=0.7),
                    showlegend=False, name=prov_name,
                    hovertemplate=(
                        f"{prov_name}<br>"
                        f"T. máxima prevista (24 h): {ttxt}<br>"
                        f"Sensación térmica en pico: {stxt}<br>"
                        f"Hora pico: {hora}<br>"
                        f"Fuente: {fuente}"
                        "<extra></extra>"
                    ),
                )
            )

    anadir_bordes_ccaa(fig, pid_sel)
    anadir_bordes_provincias(
        fig, pid_sel,
        color_base="rgba(30,41,59,0.45)", width_base=0.8,
        color_activa="rgba(2,132,199,0.95)", width_activa=1.6,
    )
    vp = viewport_ccaa(pid_sel, alejado=False)
    fig.update_geos(
        resolution=50, showcountries=False, showcoastlines=False, showland=False,
        lonaxis_range=[vp["lon_min"], vp["lon_max"]],
        lataxis_range=[vp["lat_min"], vp["lat_max"]],
        fitbounds=False,
        projection_scale=projection_scale_for_viewport(vp),
    )
    fig.update_layout(
        margin=dict(t=10, b=0, l=0, r=0), autosize=True,
        uirevision=f"{uirev}-{ccaa_id}",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        **plotly_bg(theme),
    )
    return fig
