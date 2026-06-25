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
      let max = [];
      let period = 1500;

      if (byMeta) {
        base = Array.isArray(meta.base_sizes) ? meta.base_sizes : [];
        max = Array.isArray(meta.max_sizes) ? meta.max_sizes : [];
        period = Number(meta.period_ms) || period;
      }

      // Fallback robusto: extrae base/max/period desde customdata.
      if ((!base.length || base.length !== max.length) && Array.isArray(tr.customdata) && tr.customdata.length) {
        const b = [];
        const m = [];
        for (const row of tr.customdata) {
          if (!Array.isArray(row) || row.length < 2) continue;
          b.push(Number(row[0]));
          m.push(Number(row[1]));
          if (row.length >= 3 && Number(row[2]) > 0) {
            period = Number(row[2]);
          }
        }
        base = b;
        max = m;
      }

      if (!base.length || base.length !== max.length) continue;
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
