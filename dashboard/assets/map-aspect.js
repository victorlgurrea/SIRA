(function () {
  /** Actualiza el aspect del mapa al redimensionar (móvil/desktop). */
  let last = null;
  let timer = null;

  function computeAspect() {
    const el = document.querySelector(".sira-graph-wrap--map");
    const w = el && el.clientWidth > 40 ? el.clientWidth : window.innerWidth;
    const h =
      el && el.clientHeight > 40
        ? el.clientHeight
        : Math.min(window.innerHeight * (window.innerWidth <= 640 ? 0.72 : 0.56), 620);
    if (!h || h < 1) return null;
    let aspect = w / h;
    if (window.innerWidth <= 640) {
      aspect = Math.min(aspect, 0.85);
    } else if (window.innerWidth <= 900) {
      aspect = Math.min(Math.max(aspect, 1.05), 1.45);
    } else {
      aspect = Math.min(Math.max(aspect, 1.45), 2.2);
    }
    return Math.round(Math.max(0.55, Math.min(3.2, aspect)) * 100) / 100;
  }

  function pushAspect() {
    const aspect = computeAspect();
    if (aspect == null) return;
    if (last != null && Math.abs(last - aspect) < 0.04) return;
    last = aspect;
    window.__siraMapAspect = aspect;
    if (window.dash_clientside && typeof window.dash_clientside.set_props === "function") {
      try {
        window.dash_clientside.set_props("map-aspect", { data: aspect });
      } catch (_) {
        /* Dash aún no montado */
      }
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(pushAspect, 180);
  }

  window.addEventListener("resize", schedule);
  window.addEventListener("orientationchange", schedule);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setTimeout(pushAspect, 350);
    });
  } else {
    setTimeout(pushAspect, 350);
  }
})();
