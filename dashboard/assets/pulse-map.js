(function () {
  const TICK_MS = 280;
  const CIRCLE_POINTS = 40;

  function getPlotDiv() {
    const wrap = document.getElementById("mapa");
    if (!wrap) return null;
    return wrap.querySelector(".js-plotly-plot");
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function pulseT(nowMs, periodMs) {
    const phase = (nowMs % periodMs) / periodMs;
    return Math.sin(phase * Math.PI);
  }

  function radiusAt(t, minR, maxR, fraction) {
    const f = fraction > 0 ? fraction : 1;
    return lerp(minR, maxR, t) * f;
  }

  function circlePerimeter(lat, lon, radiusKm) {
    if (!radiusKm || radiusKm <= 0) {
      return [[lat], [lon]];
    }
    const latRad = (Number(lat) * Math.PI) / 180;
    const kmPerDegLat = 111.2;
    const kmPerDegLon = 111.2 * Math.max(0.2, Math.cos(latRad));
    const lats = [];
    const lons = [];
    for (let i = 0; i <= CIRCLE_POINTS; i++) {
      const ang = (2 * Math.PI * i) / CIRCLE_POINTS;
      lats.push(lat + (radiusKm * Math.sin(ang)) / kmPerDegLat);
      lons.push(lon + (radiusKm * Math.cos(ang)) / kmPerDegLon);
    }
    return [lats, lons];
  }

  function circleFillRing(lat, lon, radiusKm) {
    const ring = circlePerimeter(lat, lon, radiusKm);
    return [ring[0].slice().reverse(), ring[1].slice().reverse()];
  }

  function minRadius(maxR) {
    return Math.max(maxR < 20 ? 1.5 : 3, maxR * 0.06);
  }

  function animatePulse(gd) {
    if (!gd || !gd.data || !window.Plotly || document.hidden) return;
    const now = Date.now();
    for (let i = 0; i < gd.data.length; i++) {
      const tr = gd.data[i];
      const meta = tr && tr.meta;
      if (!meta || meta.pulse !== "grow") continue;

      const period = Number(meta.period_ms) || 1800;
      const fillRgb = meta.fill_rgb || "248, 113, 113";
      const borderRgb = meta.border_rgb || "220, 38, 38";
      const maxR = Number(meta.radius_km) || 120;
      const lat = Number(meta.center_lat);
      const lon = Number(meta.center_lon);
      const part = meta.part || "fill";
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

      const minR = minRadius(maxR);
      const t = pulseT(now, period);
      const r = radiusAt(t, minR, maxR, 1);

      try {
        if (part === "border") {
          const ring = circlePerimeter(lat, lon, r);
          const borderOp = lerp(0.55, 1.0, t);
          window.Plotly.restyle(
            gd,
            {
              lat: [ring[0]],
              lon: [ring[1]],
              "line.color": ["rgba(" + borderRgb + ", " + borderOp + ")"],
              "line.width": [lerp(1.8, 3.2, t)],
            },
            [i]
          );
        else:
          // Relleno a radio fijo: solo pulsa opacidad (hover estable en todo el círculo).
          const fillMode = meta.fill_mode || "grow";
          const fillR = fillMode === "opacity" ? maxR : r;
          const ring = circleFillRing(lat, lon, fillR);
          const fillOp = lerp(0.08, 0.38, t);
          window.Plotly.restyle(
            gd,
            {
              lat: [ring[0]],
              lon: [ring[1]],
              fillcolor: ["rgba(" + fillRgb + ", " + fillOp + ")"],
              "line.color": ["rgba(0, 0, 0, 0)"],
              "line.width": [0],
            },
            [i]
          );
        }
      } catch (e) {
        // Traza sustituida por Dash; ignorar.
      }
    }
  }

  function loop() {
    const gd = getPlotDiv();
    if (gd) animatePulse(gd);
    window.setTimeout(loop, TICK_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loop);
  } else {
    loop();
  }
})();
