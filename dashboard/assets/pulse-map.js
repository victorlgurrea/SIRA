(function () {
  const TICK_MS = 120;

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
    // 0..1..0: latido (aparece/desaparece) con expansión/contracción
    return Math.sin(phase * Math.PI);
  }

  function clamp(x, min, max) {
    return Math.max(min, Math.min(max, x));
  }

  function pxPerKm(gd, lat) {
    const fl = gd && gd._fullLayout;
    if (!fl || !fl.geo || !fl.geo.lataxis || !fl.geo.lonaxis) return 0;
    const latRange = fl.geo.lataxis.range || [32, 46];
    const lonRange = fl.geo.lonaxis.range || [-12, 8];
    const latSpan = Math.abs(Number(latRange[1]) - Number(latRange[0])) || 1;
    const lonSpan = Math.abs(Number(lonRange[1]) - Number(lonRange[0])) || 1;
    const w = Math.max(200, Number(fl.width || gd.clientWidth || 800));
    const h = Math.max(200, Number(fl.height || gd.clientHeight || 500));
    const pxPerDegLon = w / lonSpan;
    const pxPerDegLat = h / latSpan;
    const kmPerDegLat = 111.2;
    const kmPerDegLon = 111.2 * Math.max(0.2, Math.cos((Number(lat || 39.5) * Math.PI) / 180));
    const pLon = pxPerDegLon / kmPerDegLon;
    const pLat = pxPerDegLat / kmPerDegLat;
    return Math.max(0.01, Math.min(pLon, pLat));
  }

  function animatePulse(gd) {
    if (!gd || !gd.data || !window.Plotly) return;
    const now = Date.now();
    for (let i = 0; i < gd.data.length; i++) {
      const tr = gd.data[i];
      const meta = tr && tr.meta;
      const byMeta = meta && meta.pulse === true;
      const byName = tr && (tr.name === "Hoy" || tr.name === "Pulso prueba");
      if (!byMeta && !byName) continue;

      let base = [];
      let period = 1500;
      let radiusKm = [];

      if (byMeta) {
        base = Array.isArray(meta.base_sizes) ? meta.base_sizes : [];
        period = Number(meta.period_ms) || period;
      }

      // Extrae radio perceptible desde customdata: [radio_km, period_ms]
      if (Array.isArray(tr.customdata) && tr.customdata.length) {
        const b = [];
        const r = [];
        for (const row of tr.customdata) {
          if (!Array.isArray(row) || row.length < 1) continue;
          if (Number.isFinite(Number(row[0]))) {
            r.push(Number(row[0]));
          }
          if (row.length >= 2 && Number(row[1]) > 0) {
            period = Number(row[1]);
          }
        }
        if (r.length) radiusKm = r;
        if (!base.length && b.length) base = b;
      }

      if (!base.length) continue;
      if (!radiusKm.length) {
        radiusKm = new Array(base.length).fill(120);
      }
      if (radiusKm.length !== base.length) {
        radiusKm = new Array(base.length).fill(radiusKm[0] || 120);
      }
      const lats = Array.isArray(tr.lat) ? tr.lat : [];
      const max = base.map((b, idx) => {
        const lat = lats[idx] != null ? Number(lats[idx]) : 39.5;
        const ppk = pxPerKm(gd, lat);
        const r = Number(radiusKm[idx] || 120);
        const target = Number(b) + (r * ppk * 1.8);
        return clamp(target, Number(b) + 8, 220);
      });
      const t = pulseFactor(now, period);
      const sizes = base.map((b, idx) => lerp(Number(b), Number(max[idx]), t));
      const op = lerp(0.06, 0.45, t);
      try {
        window.Plotly.restyle(
          gd,
          {
            "marker.size": [sizes],
            "marker.opacity": [op],
          },
          [i]
        );
      } catch (e) {
        // Evita romper el resto de la UI si una traza cambia.
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
