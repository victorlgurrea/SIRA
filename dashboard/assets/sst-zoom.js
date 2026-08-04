(function () {
  /** Escala el tamaño de celdas SST al hacer zoom en Scattergeo (evita huecos blancos). */
  let baseScaleByPlot = new WeakMap();
  let timer = null;

  function getPlotDiv() {
    const wrap = document.getElementById("mapa");
    if (!wrap) return null;
    return wrap.querySelector(".js-plotly-plot");
  }

  function geoScale(gd) {
    try {
      const geo = gd._fullLayout && gd._fullLayout.geo;
      if (!geo || !geo.projection) return null;
      const s = Number(geo.projection.scale);
      return Number.isFinite(s) && s > 0 ? s : null;
    } catch (_) {
      return null;
    }
  }

  function updateSstSizes(gd) {
    if (!gd || !gd.data || !window.Plotly) return;
    const scale = geoScale(gd);
    if (scale == null) return;
    let baseScale = baseScaleByPlot.get(gd);
    if (baseScale == null) {
      baseScale = scale;
      baseScaleByPlot.set(gd, baseScale);
    }

    const idxs = [];
    const sizes = [];
    for (let i = 0; i < gd.data.length; i++) {
      const tr = gd.data[i];
      const meta = tr && tr.meta;
      if (!meta || meta.sira_layer !== "sst_med") continue;
      const base = Number(meta.base_size) || 12;
      const factor = Math.min(2.2, Math.max(1, scale / baseScale));
      const size = Math.min(28, Math.max(base, Math.round(base * factor)));
      idxs.push(i);
      sizes.push(size);
    }
    if (!idxs.length) return;
    try {
      window.Plotly.restyle(gd, { "marker.size": sizes }, idxs);
    } catch (_) {
      /* ignore */
    }
  }

  function schedule(gd) {
    clearTimeout(timer);
    timer = setTimeout(function () {
      updateSstSizes(gd || getPlotDiv());
    }, 80);
  }

  function bind(gd) {
    if (!gd || gd.__siraSstZoom) return;
    gd.__siraSstZoom = true;
    gd.on("plotly_relayout", function () {
      schedule(gd);
    });
    gd.on("plotly_afterplot", function () {
      const s = geoScale(gd);
      if (s != null) baseScaleByPlot.set(gd, s);
      schedule(gd);
    });
    schedule(gd);
  }

  function watch() {
    const gd = getPlotDiv();
    if (gd && gd.data) bind(gd);
  }

  setInterval(watch, 700);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setTimeout(watch, 400);
    });
  } else {
    setTimeout(watch, 400);
  }
})();
