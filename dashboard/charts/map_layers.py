"""Capas Scattergeo del mapa SIRA (sismos, incendios, hidrología, AEMET)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from sira.config.settings import MAP_CIRCLE_POINTS
from sira.domain.geo import circle_disk_polygon, circle_perimeter
from sira.infrastructure.geo.aemet_zonas import aviso_maximo_zona, color_nivel, es_zona_costera, zonas_ccaa_pintado
from sira.infrastructure.http.client import fmt_hora_espana


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
    # Naranja para todos los incendios (rojo queda reservado a sismos).
    fill_rgb = "249, 115, 22"
    border_rgb = "234, 88, 12"
    r_draw = r
    fill_op = 0.18 if destacado else 0.16
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


def add_leyenda_sst_med(
    fig: go.Figure,
    *,
    fecha: str | None = None,
    fuente: str | None = None,
    theme: str = "dark",
    tmin: float | None = None,
    tmax: float | None = None,
) -> None:
    """Barra de color tipo Copernicus MyOcean (5–25 °C)."""
    from charts.figures import (
        SST_MED_LEYENDA_MAX,
        SST_MED_LEYENDA_MIN,
        color_sst_med,
    )
    from ui.theme import chart_text

    lo = float(tmin if tmin is not None else SST_MED_LEYENDA_MIN)
    hi = float(tmax if tmax is not None else SST_MED_LEYENDA_MAX)
    txt = chart_text(theme)
    bg = "rgba(15, 23, 42, 0.92)" if theme == "dark" else "rgba(255, 255, 255, 0.95)"
    border = "rgba(148, 163, 184, 0.55)"

    x0, y0, w, h = 0.014, 0.10, 0.20, 0.028
    fig.add_shape(
        type="rect",
        xref="paper",
        yref="paper",
        x0=x0 - 0.006,
        x1=x0 + w + 0.006,
        y0=y0 - 0.042,
        y1=y0 + h + 0.022,
        fillcolor=bg,
        line=dict(color=border, width=1),
        layer="above",
    )
    steps = 64
    for i in range(steps):
        t = lo + (hi - lo) * i / max(steps - 1, 1)
        fig.add_shape(
            type="rect",
            xref="paper",
            yref="paper",
            x0=x0 + w * i / steps,
            x1=x0 + w * (i + 1) / steps,
            y0=y0,
            y1=y0 + h,
            fillcolor=color_sst_med(t),
            line_width=0,
            layer="above",
        )
    titulo = "Sea water potential temperature"
    subt = fecha or "—"
    if fuente:
        subt = f"{subt}<br><span style='font-size:10px'>{fuente}</span>"
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=x0,
        y=y0 + h + 0.018,
        xanchor="left",
        yanchor="bottom",
        text=f"<b>{titulo}</b><br>{subt}",
        showarrow=False,
        align="left",
        font=dict(size=11, color=txt),
    )
    for tick in (5, 10, 15, 20, 25):
        if tick < lo or tick > hi:
            continue
        frac = (tick - lo) / (hi - lo) if hi > lo else 0
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=x0 + w * frac,
            y=y0 - 0.008,
            xanchor="center",
            yanchor="top",
            text=f"{tick}",
            showarrow=False,
            font=dict(size=9, color=txt),
        )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=x0 + w + 0.014,
        y=y0 + h / 2,
        xanchor="left",
        yanchor="middle",
        text="°C",
        showarrow=False,
        font=dict(size=10, color=txt),
    )


def add_capa_sst_med(
    fig: go.Figure,
    celdas: list[dict] | None,
    *,
    fecha: str | None = None,
    paso_deg: float | None = None,
    fuente: str | None = None,
    theme: str = "dark",
) -> None:
    """Malla SST solo-mar con markers cuadrados (Scattergeo fill=toself fusiona todo en un bloque)."""
    if not celdas:
        return
    from charts.figures import (
        SST_MED_COLORSCALE,
        SST_MED_LEYENDA_MAX,
        SST_MED_LEYENDA_MIN,
    )
    from sira.infrastructure.geo.mar_mediterraneo import fraccion_mar_celda, punto_en_mar_mediterraneo

    paso = float(paso_deg or 0.12)
    half_mask = max(paso * 0.48, 0.05)
    # Tamaño en px aprox. para paso ~0.12° en vista Valencia (sin huecos graves ni invasión).
    size = max(8, min(13, round(paso * 90)))
    fecha_txt = f" · {fecha}" if fecha else ""

    lats: list[float] = []
    lons: list[float] = []
    temps: list[float] = []
    hovers: list[str] = []

    for c in celdas:
        if c.get("sst_c") is None:
            continue
        lat = float(c["lat"])
        lon = float(c["lon"])
        if not punto_en_mar_mediterraneo(lat, lon):
            continue
        if fraccion_mar_celda(lat, lon, half_mask) < 0.8:
            continue
        temp = float(c["sst_c"])
        lats.append(lat)
        lons.append(lon)
        temps.append(temp)
        hovers.append(
            f"SST Mediterráneo{fecha_txt}<br>"
            f"<b>{temp:.1f} °C</b><br>"
            f"Zona {lat:.2f}°N, {lon:.2f}°E"
        )

    if not lats:
        return

    fig.add_trace(go.Scattergeo(
        lat=lats,
        lon=lons,
        mode="markers",
        showlegend=False,
        legendgroup="sst_med",
        marker=dict(
            symbol="square",
            size=size,
            color=temps,
            colorscale=SST_MED_COLORSCALE,
            cmin=SST_MED_LEYENDA_MIN,
            cmax=SST_MED_LEYENDA_MAX,
            line=dict(width=0),
            opacity=0.92,
        ),
        text=hovers,
        hovertemplate="%{text}<extra></extra>",
    ))

    add_leyenda_sst_med(fig, fecha=fecha, fuente=fuente, theme=theme)


def add_capa_aemet_zonas(
    fig: go.Figure,
    provincia_id: str,
    alertas: list[dict],
    *,
    sst_mar_activo: bool = False,
) -> None:
    from sira.infrastructure.sources.meteo.aemet_alerts import fmt_alerta_detalle

    for zona in zonas_ccaa_pintado(provincia_id):
        aviso = aviso_maximo_zona(zona, alertas)
        nivel = str((aviso or {}).get("level") or "").lower()
        es_costa = es_zona_costera(zona)
        fill, line_color = color_nivel(nivel if aviso else None, costera=es_costa)
        if sst_mar_activo and es_costa and not aviso:
            fill = "rgba(0,0,0,0)"
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
                ini = fmt_hora_espana(aviso.get("onset"))
                fin = fmt_hora_espana(aviso.get("expires"))
                vigencia = f"<br>Vigencia: {ini} → {fin}"
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
