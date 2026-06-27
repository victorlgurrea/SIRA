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
    return Math.sin(phase * Math.PI);
  }

  function animatePulse(gd) {
    if (!gd || !gd.data || !window.Plotly) return;
    const now = Date.now();
    for (let i = 0; i < gd.data.length; i++) {
      const tr = gd.data[i];
      const meta = tr && tr.meta;
      if (!meta || meta.pulse !== "circle") continue;

      const period = Number(meta.period_ms) || 1600;
      const rgb = meta.fill_rgb || "248, 113, 113";
      const t = pulseFactor(now, period);
      const fillOp = lerp(0.05, 0.28, t);
      const lineOp = lerp(0.35, 0.9, t);

      try {
        window.Plotly.restyle(
          gd,
          {
            fillcolor: ["rgba(" + rgb + ", " + fillOp + ")"],
            "line.color": ["rgba(" + rgb + ", " + lineOp + ")"],
          },
          [i]
        );
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
