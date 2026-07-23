"""Funciones de generación de figuras Plotly para el dashboard SIRA."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from sira.config.settings import (
    INCENDIO_MAP_MAX,
    MAP_CIRCLE_POINTS,
    MAPA,
)
from sira.infrastructure.persistence.sqlite import get_historial_municipio
from sira.infrastructure.geo.ccaa_mapa import anadir_bordes_ccaa, anadir_bordes_provincias, anadir_costa_ign
from sira.infrastructure.geo.aemet_zonas import aviso_maximo_zona, color_nivel, es_zona_costera, zonas_ccaa_pintado
from sira.infrastructure.geo.es import (
    CCAA_PROVINCIAS,
    ccaa_de_provincia,
    projection_scale_for_viewport,
    provincias,
    viewport_ccaa,
    viewport_fit_contenedor,
    viewport_fit_observacion,
)
from ui.components import dir_compass
from sira.domain.seismic.sismos import circle_disk_polygon, circle_perimeter
from ui.theme import (
    C_CYAN,
    C_GREEN,
    C_MUTED,
    C_NAVY,
    C_ORANGE,
    C_TEAL,
    C_TEXT,
    COLORES,
    chart_muted,
    chart_text,
    plotly_bg,
)

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
# Helpers
# ---------------------------------------------------------------------------

def es_sismo_hoy(ts) -> bool:
    try:
        return pd.to_datetime(ts, utc=True).date() == datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        return False


def fmt_sismo_fecha(ts) -> str:
    try:
        return pd.to_datetime(ts, utc=True).strftime("%d/%m/%Y %H:%M UTC")
    except (ValueError, TypeError):
        return "—"


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
# Capas del mapa
# ---------------------------------------------------------------------------

def add_circulos_perceptibles(
    fig: go.Figure,
    rows: pd.DataFrame,
    *,
    legend_name: str,
    legendgroup: str,
    period_ms: int,
    fill_rgb: str = "248, 113, 113",
    border_rgb: str = "220, 38, 38",
    radio_col: str = "radio_perceptible_km",
    hover_label: str = "Zona perceptible",
    show_legend: bool = True,
) -> None:
    if rows.empty:
        return
    radios = (
        rows[radio_col].tolist()
        if radio_col in rows.columns
        else [120.0] * len(rows)
    )
    for idx, row in enumerate(rows.itertuples(index=False)):
        r = float(radios[idx]) if idx < len(radios) else 120.0
        if r <= 0:
            continue
        lat0 = float(row.lat)
        lon0 = float(row.lon)
        mag = float(getattr(row, "magnitud", 0) or 0)
        row_hover = getattr(row, "hover_label", None) or hover_label
        area = getattr(row, "area_desc", "") or ""
        hover_html = getattr(row, "hover_html", None)
        if hover_html:
            hover_body = str(hover_html)
        elif mag > 0:
            hover_body = f"{row_hover} (hasta ~{r:.0f} km)<br>Mag {mag:.1f} · epicentro"
            if area:
                hover_body += f"<br>{area}"
        elif area:
            hover_body = f"{row_hover} (hasta ~{r:.0f} km)<br>{area}"
        else:
            hover_body = f"{row_hover} (hasta ~{r:.0f} km)"
        # Relleno a radio completo (hover estable); el pulso anima opacidad/borde.
        lat_fill, lon_fill = circle_disk_polygon(lat0, lon0, r, MAP_CIRCLE_POINTS)
        lat_ring, lon_ring = circle_perimeter(lat0, lon0, max(r * 0.06, 3.0), MAP_CIRCLE_POINTS)
        pulse_meta = {
            "center_lat": lat0,
            "center_lon": lon0,
            "radius_km": r,
            "period_ms": period_ms,
            "fill_rgb": fill_rgb,
            "border_rgb": border_rgb,
        }
        fig.add_trace(
            go.Scattergeo(
                lat=lat_fill,
                lon=lon_fill,
                mode="lines",
                name=legend_name,
                legendgroup=legendgroup,
                showlegend=show_legend and idx == 0,
                fill="toself",
                fillcolor=f"rgba({fill_rgb}, 0.12)",
                line=dict(width=0, color="rgba(0, 0, 0, 0)"),
                hovertemplate=hover_body + "<extra></extra>",
                meta={**pulse_meta, "pulse": "grow", "part": "fill", "fill_mode": "opacity"},
            )
        )
        fig.add_trace(
            go.Scattergeo(
                lat=lat_ring,
                lon=lon_ring,
                mode="lines",
                name=legend_name,
                legendgroup=legendgroup,
                showlegend=False,
                fill="none",
                line=dict(width=2, color=f"rgba({border_rgb}, 0.75)"),
                hoverinfo="skip",
                meta={**pulse_meta, "pulse": "grow", "part": "border", "radius_fraction": 1.0},
            )
        )


def add_marcador_observacion(fig: go.Figure, lat_obs: float | None, lon_obs: float | None, obs_nombre: str) -> None:
    if lat_obs is not None and lon_obs is not None:
        fig.add_trace(go.Scattergeo(
            lat=[lat_obs], lon=[lon_obs], mode="markers+text",
            text=[obs_nombre or "Ubicación"], showlegend=False,
            marker=dict(size=11, color="#fbbf24", symbol="star", line=dict(width=1, color="white")),
            textposition="top center",
        ))


def add_zona_incendio(fig: go.Figure, inc: dict, *, destacado: bool, legend_name: str | None = None) -> None:
    lat = float(inc["lat"])
    lon = float(inc["lon"])
    r = float(inc.get("radio_km") or 2)
    fill_rgb = "239, 68, 68" if destacado else "249, 115, 22"
    border_rgb = "220, 38, 38" if destacado else "234, 88, 12"
    if destacado:
        r_draw = r
        fill_op = 0.12
        border_op = 0.75
        pulse_meta = {
            "center_lat": lat,
            "center_lon": lon,
            "radius_km": r,
            "period_ms": 2000,
            "fill_rgb": fill_rgb,
            "border_rgb": border_rgb,
        }
        fill_meta = {**pulse_meta, "pulse": "grow", "part": "fill", "fill_mode": "opacity"}
        border_meta = {**pulse_meta, "pulse": "grow", "part": "border", "radius_fraction": 1.0}
        r_border = max(r * 0.06, 1.5)
    else:
        r_draw = r
        fill_op = 0.16
        border_op = 1.0
        fill_meta = None
        border_meta = None
        r_border = r
    lat_fill, lon_fill = circle_disk_polygon(lat, lon, r_draw, MAP_CIRCLE_POINTS)
    lat_ring, lon_ring = circle_perimeter(lat, lon, r_border, MAP_CIRCLE_POINTS)
    fig.add_trace(go.Scattergeo(
        lat=lat_fill, lon=lon_fill, mode="lines", name=legend_name or "Foco",
        legendgroup="inc", showlegend=bool(legend_name),
        fill="toself", fillcolor=f"rgba({fill_rgb}, {fill_op})",
        line=dict(width=0, color="rgba(0, 0, 0, 0)"),
        hovertemplate=(
            f"Foco activo<br>"
            f"Radio ~{r:.1f} km · área ~{inc.get('area_km2', '—')} km²<br>"
            f"FRP {inc.get('frp_mw', '—')} MW · {inc.get('n_detecciones', 1)} detecciones"
            + (" · cerca de tu zona<extra></extra>" if destacado else "<extra></extra>")
        ),
        meta=fill_meta,
    ))
    fig.add_trace(go.Scattergeo(
        lat=lat_ring, lon=lon_ring, mode="lines", showlegend=False,
        fill="none",
        line=dict(width=2 if destacado else 1.6, color=f"rgba({border_rgb}, {border_op})"),
        hoverinfo="skip",
        meta=border_meta,
    ))


def add_marcadores_embalses(fig: go.Figure, embalses: list[dict]) -> None:
    if not embalses:
        return
    colores = {"critico": "#1d4ed8", "alerta": "#2563eb", "vigilancia": "#38bdf8"}
    leyenda = False
    for emb in embalses:
        lat = float(emb.get("lat") or 0)
        lon = float(emb.get("lon") or 0)
        if not lat and not lon:
            continue
        nivel = str(emb.get("nivel_riesgo") or "vigilancia")
        color = colores.get(nivel, "#38bdf8")
        size = {"critico": 13, "alerta": 11, "vigilancia": 9}.get(nivel, 9)
        pct = emb.get("porcentaje", "—")
        vol = emb.get("volumen_hm3", "—")
        dist = emb.get("dist_local_km", "—")
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers",
            name="Embalse en vigilancia" if not leyenda else None,
            legendgroup="embalses", showlegend=not leyenda,
            marker=dict(size=size, color=color, symbol="circle", line=dict(width=1.2, color="white")),
            text=[emb.get("nombre", "Embalse")],
            hovertemplate=(
                "%{text}<br>"
                f"Nivel: {pct}% · {vol} hm³<br>"
                f"Riesgo: {nivel.title()}<br>"
                f"Distancia: {dist} km"
                "<extra></extra>"
            ),
        ))
        leyenda = True


def add_marcadores_aforos(fig: go.Figure, aforos: list[dict]) -> None:
    if not aforos:
        return
    colores = {"critico": "#dc2626", "alerta": "#f97316", "vigilancia": "#14b8a6"}
    leyenda = False
    for af in aforos:
        lat = float(af.get("lat") or 0)
        lon = float(af.get("lon") or 0)
        if not lat and not lon:
            continue
        nivel = str(af.get("nivel_riesgo") or "vigilancia")
        sin_datos = bool(af.get("sin_datos_recientes"))
        if sin_datos:
            color, symbol, size = "#f59e0b", "x", 10
            tipo_txt = "Aforo — sensor sin datos"
        else:
            color = colores.get(nivel, "#14b8a6")
            symbol = "diamond"
            size = {"critico": 12, "alerta": 10, "vigilancia": 8}.get(nivel, 8)
            tipo_txt = "Aforo CHJ"
        q = af.get("caudal_m3s")
        h = af.get("nivel_m")
        dist = af.get("dist_local_km", "—")
        q_txt = f"{q} m³/s" if q is not None else "—"
        h_txt = f"{h} m" if h is not None else "—"
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers",
            name="Aforo CHJ en alerta" if not leyenda else None,
            legendgroup="aforos", showlegend=not leyenda,
            marker=dict(size=size, color=color, symbol=symbol, line=dict(width=1.2, color="white")),
            text=[af.get("nombre", "Aforo")],
            hovertemplate=(
                f"{tipo_txt}<br>"
                "%{text}<br>"
                f"Nivel: {h_txt} · Caudal: {q_txt}<br>"
                f"Riesgo: {nivel.title()}{' · sin lectura reciente' if sin_datos else ''}<br>"
                f"Distancia: {dist} km"
                "<extra></extra>"
            ),
        ))
        leyenda = True


def add_capa_aemet_zonas(fig: go.Figure, provincia_id: str, alertas: list[dict]) -> None:
    from sira.infrastructure.sources.meteo.aemet_alerts import fmt_alerta_detalle

    for zona in zonas_ccaa_pintado(provincia_id):
        aviso = aviso_maximo_zona(zona, alertas)
        nivel = str((aviso or {}).get("level") or "").lower()
        es_costa = es_zona_costera(zona)
        fill, line_color = color_nivel(nivel if aviso else None, costera=es_costa)
        nombre = str(zona.get("nombre") or zona.get("id") or "Zona AEMET")
        if aviso:
            nivel_txt = nivel.upper()
            fen = str(aviso.get("fenomeno_desc") or "—")
            fen_code = str(aviso.get("fenomeno") or "").upper()
            if fen_code in {"CO", "RI"} or es_costa:
                tipo = "Fenómeno costero (AEMET)" if fen_code != "RI" else "Rissaga (AEMET)"
            else:
                tipo = "Aviso AEMET"
            prob = str(aviso.get("probabilidad") or "—")
            detalle = fmt_alerta_detalle(aviso)
            vigencia = ""
            if aviso.get("onset") or aviso.get("expires"):
                vigencia = f"<br>Vigencia: {aviso.get('onset') or '—'} → {aviso.get('expires') or '—'}"
            hover = (
                f"{nombre}<br>"
                f"{tipo}<br>"
                f"Nivel: {nivel_txt} (hoy)<br>"
                f"Fenómeno: {fen}<br>"
                f"Detalle: {detalle}<br>"
                f"Probabilidad: {prob}"
                f"{vigencia}"
                "<extra></extra>"
            )
        else:
            hover = f"{nombre}<br>Sin aviso para hoy<extra></extra>"
        for ring in zona.get("rings") or []:
            lats = ring.get("lat") or []
            lons = ring.get("lon") or []
            if len(lats) < 3:
                continue
            fig.add_trace(
                go.Scattergeo(
                    lat=lats, lon=lons, mode="lines",
                    fill="toself", fillcolor=fill,
                    line=dict(color=line_color, width=1.0 if aviso else 0.85),
                    showlegend=False, name=nombre, hovertemplate=hover,
                )
            )


# ---------------------------------------------------------------------------
# Geo layout
# ---------------------------------------------------------------------------

def geo_layout(
    fig: go.Figure,
    viewport: dict | None = None,
    *,
    uirevision: str = "sira-mapa",
    estilo_aemet: bool = False,
    theme: str = "dark",
) -> None:
    vp = viewport or {
        "lat_centro": MAPA["lat_centro"],
        "lon_centro": MAPA["lon_centro"],
        "lat_min": MAPA["lat_min"],
        "lat_max": MAPA["lat_max"],
        "lon_min": MAPA["lon_min"],
        "lon_max": MAPA["lon_max"],
    }
    if vp.get("centrar_obs"):
        vp = viewport_fit_observacion(vp, aspect=2.85)
    else:
        vp = viewport_fit_contenedor(vp, aspect=2.85)
    zoom_margin = 1.38 if vp.get("nivel") == "ccaa" else 1.0
    proj_scale = projection_scale_for_viewport(vp, margin=zoom_margin)
    use_light = estilo_aemet or theme == "light"
    landcolor = "#d8dde3" if use_light else C_NAVY
    oceancolor = "#eef1f5" if use_light else "#1e4976"
    fig.update_geos(
        scope="world",
        projection_type="mercator",
        center=dict(lat=vp["lat_centro"], lon=vp["lon_centro"]),
        projection_scale=proj_scale,
        lataxis_range=[vp["lat_min"], vp["lat_max"]],
        lonaxis_range=[vp["lon_min"], vp["lon_max"]],
        domain=dict(x=[0, 1], y=[0, 1]),
        showland=True, landcolor=landcolor,
        showocean=True, oceancolor=oceancolor,
        showcountries=False,
        showcoastlines=False,
        resolution=110,
    )
    layout = dict(
        margin=dict(t=10, b=0, l=0, r=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        autosize=True,
        uirevision=uirevision,
    )
    if estilo_aemet:
        layout.update(paper_bgcolor="#eef1f5", plot_bgcolor="#eef1f5", font=dict(color="#1f2937"))
    else:
        layout.update(**plotly_bg(theme))
    fig.update_layout(**layout)


# ---------------------------------------------------------------------------
# Figuras principales
# ---------------------------------------------------------------------------

def fig_mapa(
    sismos: list,
    incendios: list | None = None,
    lat_obs: float | None = None,
    lon_obs: float | None = None,
    obs_nombre: str = "",
    alertas_meteo: list | None = None,
    embalses_mapa: list | None = None,
    aforos_mapa: list | None = None,
    viewport: dict | None = None,
    map_uirevision: str = "sira-mapa",
    provincia_id: str | None = None,
    theme: str = "dark",
    mostrar_tsunami: bool = True,
) -> go.Figure:
    fig = go.Figure()
    estilo_aemet = bool(provincia_id)
    anadir_costa_ign(
        fig, viewport,
        color="#6b7280" if estilo_aemet else "#94a3b8",
        width=0.9 if estilo_aemet else 0.8,
    )
    if provincia_id:
        add_capa_aemet_zonas(fig, str(provincia_id).zfill(2), alertas_meteo or [])
    if estilo_aemet:
        anadir_bordes_ccaa(
            fig, provincia_id,
            color_base="rgba(55, 65, 81, 0.42)", width_base=1.4,
            color_activa="rgba(17, 24, 39, 0.88)", width_activa=2.6,
        )
        anadir_bordes_provincias(
            fig, provincia_id,
            color_base="rgba(75, 85, 99, 0.72)", width_base=1.0,
            color_activa="rgba(17, 24, 39, 0.95)", width_activa=2.0,
        )
    else:
        anadir_bordes_ccaa(fig, provincia_id)
        anadir_bordes_provincias(fig, provincia_id)
    df = pd.DataFrame(sismos) if sismos else pd.DataFrame()

    if not df.empty and "nivel_local" not in df.columns:
        df = df.copy()
        if "nivel_alerta" in df.columns:
            df["nivel_local"] = df["nivel_alerta"]
        if "score_total" in df.columns:
            df["score_local"] = df["score_total"]

    if not df.empty and "es_prueba" in df.columns:
        mask_prueba = df["es_prueba"].fillna(False)
        df_prueba = df[mask_prueba]
        df = df[~mask_prueba]
    else:
        df_prueba = pd.DataFrame()

    if not df.empty and "perceptible_local" in df.columns:
        en_mar_col = df["en_mar"].fillna(False) if "en_mar" in df.columns else False
        perceptible_tierra = df["perceptible_local"].fillna(False)
        tsunami_mar = (
            df["alerta_tsunami"].fillna(False) & en_mar_col
            if "alerta_tsunami" in df.columns
            else False
        )
        hoy_col = (
            df["timestamp"].map(es_sismo_hoy)
            if "timestamp" in df.columns
            else pd.Series([False] * len(df), index=df.index)
        )
        radio_col = (
            df["radio_perceptible_km"].fillna(0)
            if "radio_perceptible_km" in df.columns
            else pd.Series([0.0] * len(df), index=df.index)
        )
        hoy_tierra_zona = hoy_col & ~en_mar_col & (radio_col > 0)
        mask_mapa = perceptible_tierra | tsunami_mar | hoy_tierra_zona
        df_per = df[mask_mapa]
    else:
        df_per = df

    inc_list = incendios or []
    if inc_list:
        leyenda_inc = False
        for inc in sorted(inc_list, key=lambda x: (-float(x.get("frp_mw") or 0),))[:INCENDIO_MAP_MAX]:
            add_zona_incendio(
                fig, inc, destacado=bool(inc.get("afecta_local")),
                legend_name="Incendio activo" if not leyenda_inc else None,
            )
            leyenda_inc = True

    for nivel, color in COLORES.items():
        sub = df_per[df_per["nivel_local"] == nivel] if not df_per.empty else pd.DataFrame()
        if sub.empty:
            continue
        reg_col = sub["region"] if "region" in sub.columns else [""] * len(sub)
        fechas = [fmt_sismo_fecha(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else ["—"] * len(sub)
        dist_loc = sub["dist_local_km"] if "dist_local_km" in sub.columns else [""] * len(sub)
        hoy_mask = [es_sismo_hoy(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else [False] * len(sub)
        base = sub["magnitud"] * 2 + 5
        sizes = [9 if h else b for b, h in zip(base, hoy_mask)]
        borders = [("white", 1) if h else ("white", 0.5) for h in hoy_mask]
        fig.add_trace(go.Scattergeo(
            lat=sub["lat"], lon=sub["lon"], mode="markers", name=nivel,
            marker=dict(
                size=sizes, color=color,
                line=dict(width=[b[1] for b in borders], color=[b[0] for b in borders]),
            ),
            text=sub["lugar"],
            customdata=list(zip(sub["magnitud"], sub["score_local"], reg_col, fechas, dist_loc)),
            hovertemplate=(
                "Sismo — %{text}<br>"
                "Fecha: %{customdata[3]}<br>"
                "Mag %{customdata[0]} · Score local %{customdata[1]} · %{customdata[2]}<br>"
                "Distancia: %{customdata[4]} km"
                "<extra></extra>"
            ),
        ))

    if not df_per.empty and "timestamp" in df_per.columns:
        hoy_df = df_per[df_per["timestamp"].map(es_sismo_hoy)]
    else:
        hoy_df = pd.DataFrame()

    if not hoy_df.empty:
        if "en_mar" in hoy_df.columns:
            hoy_perceptible = hoy_df[~hoy_df["en_mar"].fillna(False)]
        else:
            hoy_perceptible = hoy_df
        if not hoy_perceptible.empty:
            add_circulos_perceptibles(
                fig, hoy_perceptible,
                legend_name="Zona perceptible (hoy)", legendgroup="hoy", period_ms=1600,
            )
        if "alerta_tsunami" in hoy_df.columns and mostrar_tsunami:
            mask_tsunami = hoy_df["alerta_tsunami"].fillna(False)
            if "en_mar" in hoy_df.columns:
                mask_tsunami = mask_tsunami & hoy_df["en_mar"].fillna(False)
            df_tsunami = hoy_df[mask_tsunami].copy()
            if not df_tsunami.empty:
                hover_rows = []
                for row in df_tsunami.itertuples(index=False):
                    r = float(getattr(row, "radio_tsunami_km", 0) or 0)
                    mag = getattr(row, "magnitud", None)
                    lugar = getattr(row, "lugar", None) or "epicentro en el mar"
                    mag_txt = f"Mag {mag}" if mag is not None else "Magnitud —"
                    hover_rows.append(
                        "Alerta tsunami (sismo en el mar)<br>"
                        f"Radio aproximado de impacto del agua ~{r:.0f} km<br>"
                        f"{mag_txt} · {lugar}"
                    )
                df_tsunami["hover_html"] = hover_rows
                add_circulos_perceptibles(
                    fig, df_tsunami,
                    legend_name="Alerta tsunami (hoy)", legendgroup="tsunami", period_ms=1800,
                    fill_rgb="96, 165, 250", border_rgb="37, 99, 235",
                    radio_col="radio_tsunami_km", hover_label="Alerta tsunami",
                )

    if embalses_mapa:
        add_marcadores_embalses(fig, embalses_mapa)
    if aforos_mapa:
        add_marcadores_aforos(fig, aforos_mapa)

    if not df_prueba.empty:
        reg_col = df_prueba["region"] if "region" in df_prueba.columns else [""] * len(df_prueba)
        fechas = [fmt_sismo_fecha(ts) for ts in df_prueba["timestamp"]] if "timestamp" in df_prueba.columns else ["—"] * len(df_prueba)
        dist_loc = df_prueba["dist_local_km"] if "dist_local_km" in df_prueba.columns else [""] * len(df_prueba)
        hoy_mask_prueba = (
            [es_sismo_hoy(ts) for ts in df_prueba["timestamp"]]
            if "timestamp" in df_prueba.columns
            else [False] * len(df_prueba)
        )
        df_prueba_hoy = df_prueba[hoy_mask_prueba] if len(hoy_mask_prueba) else pd.DataFrame()
        if not df_prueba_hoy.empty:
            add_circulos_perceptibles(
                fig, df_prueba_hoy,
                legend_name="Zona perceptible (prueba)", legendgroup="prueba", period_ms=1400,
                show_legend=False,
            )
        prueba_sizes = [9 if h else (m * 2 + 8) for m, h in zip(df_prueba["magnitud"], hoy_mask_prueba)]
        prueba_borders = [("white", 1) if h else ("#f87171", 2) for h in hoy_mask_prueba]
        fig.add_trace(go.Scattergeo(
            lat=df_prueba["lat"], lon=df_prueba["lon"], mode="markers", name="Prueba",
            marker=dict(
                size=prueba_sizes, color="rgba(239, 68, 68, 0.9)", symbol="circle",
                line=dict(width=[b[1] for b in prueba_borders], color=[b[0] for b in prueba_borders]),
            ),
            text=df_prueba["lugar"],
            customdata=list(zip(df_prueba["magnitud"], df_prueba["score_local"], reg_col, fechas, dist_loc)),
            hovertemplate=(
                "🧪 %{text}<br>"
                "Fecha: %{customdata[3]}<br>"
                "Mag %{customdata[0]} · Score local %{customdata[1]} · %{customdata[2]}<br>"
                "Distancia: %{customdata[4]} km"
                "<extra></extra>"
            ),
        ))

    add_marcador_observacion(fig, lat_obs, lon_obs, obs_nombre)
    from sira.domain.seismic.sismos import distancia_km
    from sira.config.settings import ZONA

    refs: list[tuple[float, float, str, str]] = []
    if lat_obs is not None and lon_obs is not None:
        if distancia_km(lat_obs, lon_obs, ZONA["lat_ref"], ZONA["lon_ref"]) < 8:
            refs.append((ZONA["lat_ref"], ZONA["lon_ref"], ZONA["ciudad_ref"], C_CYAN))
    for lat, lon, name, color in refs:
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers+text", text=[name], showlegend=False,
            marker=dict(size=10, color=color, symbol="star"),
        ))
    geo_layout(fig, viewport, uirevision=map_uirevision, estilo_aemet=bool(provincia_id), theme=theme)
    fig.update_layout(legend=dict(title="Alerta", orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig


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
