(function () {
  const TICK_MS = 120;
  const CIRCLE_POINTS = 72;

  function getPlotDiv() {
    const wrap = document.getElementById("mapa");
    if (!wrap) return null;
    return wrap.querySelector(".js-plotly-plot");
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function pulseFactor(nowMs, periodMs) {
    const phase = (nowMs % periodMs) / periodMs;
    return Math.sin(phase * Math.PI);
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

  /** Anillo invertido: Plotly geo rellena el interior del disco. */
  function circleFillRing(lat, lon, radiusKm) {
    const ring = circlePerimeter(lat, lon, radiusKm);
    return [ring[0].slice().reverse(), ring[1].slice().reverse()];
  }

  function animatePulse(gd) {
    if (!gd || !gd.data || !window.Plotly) return;
    const now = Date.now();
    for (let i = 0; i < gd.data.length; i++) {
      const tr = gd.data[i];
      const meta = tr && tr.meta;
      if (!meta || meta.pulse !== "grow") continue;

      const period = Number(meta.period_ms) || 1600;
      const fillRgb = meta.fill_rgb || "248, 113, 113";
      const borderRgb = meta.border_rgb || "220, 38, 38";
      const maxR = Number(meta.radius_km) || 120;
      const lat = Number(meta.center_lat);
      const lon = Number(meta.center_lon);
      const part = meta.part || "fill";
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

      const t = pulseFactor(now, period);
      const minR = Math.max(3, maxR * 0.06);
      const r = lerp(minR, maxR, t);

      try {
        if (part === "border") {
          const ring = circlePerimeter(lat, lon, r);
          const borderOp = lerp(0.5, 1.0, t);
          const borderW = lerp(1.8, 3.5, t);
          window.Plotly.restyle(
            gd,
            {
              lat: [ring[0]],
              lon: [ring[1]],
              "line.color": ["rgba(" + borderRgb + ", " + borderOp + ")"],
              "line.width": [borderW],
            },
            [i]
          );
        } else {
          const ring = circleFillRing(lat, lon, r);
          const fillOp = lerp(0.1, 0.45, t);
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

  function boot() {
    window.setInterval(function () {
      const gd = getPlotDiv();
      if (!gd) return;
      animatePulse(gd);
    }, TICK_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
