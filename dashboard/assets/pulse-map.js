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
      if (!meta || meta.pulse !== true) continue;
      const base = Array.isArray(meta.base_sizes) ? meta.base_sizes : [];
      const max = Array.isArray(meta.max_sizes) ? meta.max_sizes : [];
      if (!base.length || base.length !== max.length) continue;
      const t = pulseFactor(now, Number(meta.period_ms) || 1500);
      const sizes = base.map((b, idx) => lerp(Number(b), Number(max[idx]), t));
      const op = lerp(0.06, 0.45, t);
      window.Plotly.restyle(
        gd,
        {
          "marker.size": [sizes],
          "marker.opacity": [op],
        },
        [i]
      );
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
