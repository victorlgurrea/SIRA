"""Figura principal del mapa geográfico SIRA y layout geo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go

_HORA_ES = ZoneInfo("Europe/Madrid")

from charts.map_layers import (
    add_capa_aemet_zonas,
    add_capa_sst_med,
    add_circulos_perceptibles,
    add_marcador_observacion,
    add_marcadores_aforos,
    add_marcadores_embalses,
    add_zona_incendio,
)
from sira.config.settings import (
    INCENDIO_MAP_MAX,
    MAPA,
    SISMO_MAPA_HORAS,
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


def es_sismo_reciente(ts, horas: int | None = None) -> bool:
    """True si el sismo ocurrió en las últimas N horas (mapa)."""
    ventana = SISMO_MAPA_HORAS if horas is None else int(horas)
    if ventana <= 0:
        return True
    try:
        t = pd.to_datetime(ts, utc=True).to_pydatetime()
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - t <= timedelta(hours=ventana)
    except (ValueError, TypeError):
        return False


def es_sismo_hoy(ts) -> bool:
    """True si el timestamp cae en el día UTC actual (compatibilidad)."""
    try:
        return pd.to_datetime(ts, utc=True).date() == datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        return False


def _sismos_mapa_df(df: pd.DataFrame) -> pd.DataFrame:
    """Sismos visibles en el mapa: ventana reciente (p. ej. 24 h)."""
    if df.empty or "timestamp" not in df.columns:
        return df
    mask = df["timestamp"].map(es_sismo_reciente)
    return df[mask]


def fmt_sismo_fecha(ts) -> str:
    try:
        dt = pd.to_datetime(ts, utc=True).to_pydatetime().astimezone(_HORA_ES)
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return "—"


def fmt_sismo_linea(sismo: dict | object, *, bullet: bool = False) -> str:
    """Misma línea que la tooltip de la card SISMOS: lugar · M… · fecha."""
    if isinstance(sismo, dict):
        lugar = sismo.get("lugar")
        mag = sismo.get("magnitud")
        ts = sismo.get("timestamp")
    else:
        lugar = getattr(sismo, "lugar", None)
        mag = getattr(sismo, "magnitud", None)
        ts = getattr(sismo, "timestamp", None)
    lugar_txt = str(lugar or "epicentro desconocido").strip()
    partes = [lugar_txt]
    if mag is not None and mag != "":
        partes.append(f"M{mag}")
    fecha = fmt_sismo_fecha(ts)
    if fecha and fecha != "—":
        partes.append(fecha)
    linea = " · ".join(partes)
    return f"· {linea}" if bullet else linea


def hover_html_zona_sismo(sismo: dict | object, radio_km: float | None = None) -> str:
    """Hover del círculo perceptible: texto de card + radio aproximado."""
    linea = fmt_sismo_linea(sismo, bullet=False)
    if radio_km is not None and float(radio_km) > 0:
        return f"{linea}<br>Zona perceptible (hasta ~{float(radio_km):.0f} km)"
    return linea


def _con_hover_sismos(df: pd.DataFrame, *, radio_col: str = "radio_perceptible_km") -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    radios = (
        out[radio_col].fillna(0).tolist()
        if radio_col in out.columns
        else [0.0] * len(out)
    )
    hovers: list[str] = []
    for idx, row in enumerate(out.itertuples(index=False)):
        r = float(radios[idx] or 0)
        hovers.append(hover_html_zona_sismo(row, r if r > 0 else None))
    out["hover_html"] = hovers
    return out


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
    sst_med_grid: dict | None = None,
    sst_cant_grid: dict | None = None,
    sst_atl_grid: dict | None = None,
) -> go.Figure:
    fig = go.Figure()
    estilo_aemet = bool(provincia_id)
    anadir_costa_ign(
        fig, viewport,
        color="#6b7280" if estilo_aemet else "#94a3b8",
        width=0.9 if estilo_aemet else 0.8,
    )
    from charts.map_layers import add_capa_sst_grid

    from sira.infrastructure.geo.mar_costa_atlantica import punto_en_mar_costa_atlantica
    from sira.infrastructure.geo.mar_mediterraneo import punto_en_mar_mediterraneo

    sst_capas = [
        ("Mediterráneo", sst_med_grid, punto_en_mar_mediterraneo, "sst_med"),
        ("Cantábrico", sst_cant_grid, punto_en_mar_costa_atlantica, "sst_cant"),
        ("Atlántico", sst_atl_grid, punto_en_mar_costa_atlantica, "sst_atl"),
    ]
    sst_activo = False
    leyenda_pintada = False
    for etiqueta, grid_raw, filtro_mar, grupo in sst_capas:
        grid = grid_raw if isinstance(grid_raw, dict) else {}
        celdas = grid.get("celdas") or []
        if not celdas:
            continue
        try:
            add_capa_sst_grid(
                fig,
                celdas,
                region_label=etiqueta,
                punto_en_mar=filtro_mar,
                fecha=str(grid.get("fecha") or "") or None,
                paso_deg=grid.get("paso_deg"),
                fuente=str(grid.get("fuente") or "") or None,
                theme=theme,
                legendgroup=grupo,
                show_legend=not leyenda_pintada,
                filtrar_tierra_al_pintar=(grupo == "sst_med"),
            )
            leyenda_pintada = True
            sst_activo = True
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception("Capa SST %s falló; omitiendo", etiqueta)
    if provincia_id:
        add_capa_aemet_zonas(
            fig, str(provincia_id).zfill(2), alertas_meteo or [],
            sst_mar_activo=sst_activo,
        )
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
        perceptible_tierra = df["perceptible_local"].fillna(False) & ~en_mar_col
        df_circulos_perceptibles = df[perceptible_tierra]
    else:
        df_circulos_perceptibles = df

    df_mapa = _sismos_mapa_df(df)
    df_circulos_perceptibles = _sismos_mapa_df(df_circulos_perceptibles)

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
        sub = df_mapa[df_mapa["nivel_local"] == nivel] if not df_mapa.empty else pd.DataFrame()
        if sub.empty:
            continue
        reg_col = sub["region"] if "region" in sub.columns else [""] * len(sub)
        fechas = [fmt_sismo_fecha(ts) for ts in sub["timestamp"]] if "timestamp" in sub.columns else ["—"] * len(sub)
        dist_loc = sub["dist_local_km"] if "dist_local_km" in sub.columns else [""] * len(sub)
        base = sub["magnitud"] * 2 + 5
        sizes = [max(9, float(b)) for b in base]
        hover_txt = [fmt_sismo_linea(row) for row in sub.itertuples(index=False)]
        fig.add_trace(go.Scattergeo(
            lat=sub["lat"], lon=sub["lon"], mode="markers", name=nivel,
            marker=dict(
                size=sizes, color=color,
                line=dict(width=1, color="white"),
            ),
            text=hover_txt,
            customdata=list(zip(sub["magnitud"], sub["score_local"], reg_col, fechas, dist_loc)),
            hovertemplate="%{text}<extra></extra>",
        ))

    if not df_circulos_perceptibles.empty:
        add_circulos_perceptibles(
            fig, _con_hover_sismos(df_circulos_perceptibles),
            legend_name=f"Zona perceptible ({SISMO_MAPA_HORAS} h)", legendgroup="hoy", period_ms=1600,
        )

    if not df_mapa.empty and mostrar_tsunami and "alerta_tsunami" in df_mapa.columns:
        mask_tsunami = df_mapa["alerta_tsunami"].fillna(False)
        if "en_mar" in df_mapa.columns:
            mask_tsunami = mask_tsunami & df_mapa["en_mar"].fillna(False)
        df_tsunami = df_mapa[mask_tsunami].copy()
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
                legend_name=f"Alerta tsunami ({SISMO_MAPA_HORAS} h)", legendgroup="tsunami", period_ms=1800,
                fill_rgb="96, 165, 250", border_rgb="37, 99, 235",
                radio_col="radio_tsunami_km", hover_label="Alerta tsunami",
            )

    if embalses_mapa:
        add_marcadores_embalses(fig, embalses_mapa)
    if aforos_mapa:
        add_marcadores_aforos(fig, aforos_mapa)

    if not df_prueba.empty:
        df_prueba_mapa = _sismos_mapa_df(df_prueba)
        if df_prueba_mapa.empty:
            df_prueba_mapa = df_prueba.iloc[0:0]
        reg_col = df_prueba_mapa["region"] if "region" in df_prueba_mapa.columns else [""] * len(df_prueba_mapa)
        fechas = [fmt_sismo_fecha(ts) for ts in df_prueba_mapa["timestamp"]] if "timestamp" in df_prueba_mapa.columns else ["—"] * len(df_prueba_mapa)
        dist_loc = df_prueba_mapa["dist_local_km"] if "dist_local_km" in df_prueba_mapa.columns else [""] * len(df_prueba_mapa)
        if not df_prueba_mapa.empty:
            add_circulos_perceptibles(
                fig, _con_hover_sismos(df_prueba_mapa),
                legend_name="Zona perceptible (prueba)", legendgroup="prueba", period_ms=1400,
                show_legend=False,
            )
            prueba_sizes = [max(9, float(m * 2 + 8)) for m in df_prueba_mapa["magnitud"]]
            fig.add_trace(go.Scattergeo(
                lat=df_prueba_mapa["lat"], lon=df_prueba_mapa["lon"], mode="markers", name="Prueba",
                marker=dict(
                    size=prueba_sizes, color="rgba(239, 68, 68, 0.9)", symbol="circle",
                    line=dict(width=1, color="white"),
                ),
                text=df_prueba_mapa["lugar"],
                customdata=list(zip(df_prueba_mapa["magnitud"], df_prueba_mapa["score_local"], reg_col, fechas, dist_loc)),
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
