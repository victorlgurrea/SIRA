"""Figura principal del mapa geográfico SIRA y layout geo."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go

_HORA_ES = ZoneInfo("Europe/Madrid")

from charts.map_layers import (
    add_capa_aemet_zonas,
    add_circulos_perceptibles,
    add_marcador_observacion,
    add_marcadores_aforos,
    add_marcadores_embalses,
    add_zona_incendio,
)
from sira.config.settings import (
    INCENDIO_MAP_MAX,
    MAPA,
    ZONA,
)
from sira.domain.geo import distancia_km
from sira.infrastructure.geo.ccaa_mapa import anadir_bordes_ccaa, anadir_bordes_provincias, anadir_costa_ign
from sira.infrastructure.geo.es import (
    projection_scale_for_viewport,
    viewport_fit_contenedor,
    viewport_fit_observacion,
)
from ui.theme import C_CYAN, C_NAVY, COLORES, plotly_bg


def es_sismo_hoy(ts) -> bool:
    try:
        return pd.to_datetime(ts, utc=True).date() == datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        return False


def fmt_sismo_fecha(ts) -> str:
    try:
        dt = pd.to_datetime(ts, utc=True).to_pydatetime().astimezone(_HORA_ES)
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return "—"


def geo_layout(
    fig: go.Figure,
    viewport: dict | None = None,
    *,
    uirevision: str = "sira-mapa",
    estilo_aemet: bool = False,
    theme: str = "dark",
    aspect: float = 1.65,
) -> None:
    vp = viewport or {
        "lat_centro": MAPA["lat_centro"],
        "lon_centro": MAPA["lon_centro"],
        "lat_min": MAPA["lat_min"],
        "lat_max": MAPA["lat_max"],
        "lon_min": MAPA["lon_min"],
        "lon_max": MAPA["lon_max"],
    }
    aspect = max(0.55, min(3.2, float(aspect or 1.65)))
    if vp.get("centrar_obs"):
        vp = viewport_fit_observacion(vp, aspect=aspect)
    else:
        vp = viewport_fit_contenedor(vp, aspect=aspect)
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
        fitbounds=False,
    )
    layout = dict(
        margin=dict(t=36, b=0, l=0, r=0) if aspect < 1.2 else dict(t=28, b=0, l=0, r=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(size=10)),
        autosize=True,
        uirevision=uirevision,
        height=None,
    )
    if estilo_aemet:
        layout.update(paper_bgcolor="#eef1f5", plot_bgcolor="#eef1f5", font=dict(color="#1f2937"))
    else:
        layout.update(**plotly_bg(theme))
    fig.update_layout(**layout)


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
    map_aspect: float | None = None,
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

    refs: list[tuple[float, float, str, str]] = []
    if lat_obs is not None and lon_obs is not None:
        if distancia_km(lat_obs, lon_obs, ZONA["lat_ref"], ZONA["lon_ref"]) < 8:
            refs.append((ZONA["lat_ref"], ZONA["lon_ref"], ZONA["ciudad_ref"], C_CYAN))
    for lat, lon, name, color in refs:
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lon], mode="markers+text", text=[name], showlegend=False,
            marker=dict(size=10, color=color, symbol="star"),
        ))
    geo_layout(
        fig, viewport,
        uirevision=map_uirevision,
        estilo_aemet=bool(provincia_id),
        theme=theme,
        aspect=float(map_aspect or 1.65),
    )
    fig.update_layout(legend=dict(title="Alerta", orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig
