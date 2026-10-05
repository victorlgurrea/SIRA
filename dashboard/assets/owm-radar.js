/**
 * Mapa Leaflet de precipitación OpenWeather en /lab (frame estático).
 * Las tiles pasan por /api/owm/tiles/... para no exponer la API key.
 */
(function () {
  "use strict";

  var LEAFLET_CSS =
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css";
  var LEAFLET_JS =
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";

  var state = {
    map: null,
    precip: null,
    loading: false,
    ready: false,
  };

  function ensureCss() {
    if (document.getElementById("sira-leaflet-css")) return;
    var link = document.createElement("link");
    link.id = "sira-leaflet-css";
    link.rel = "stylesheet";
    link.href = LEAFLET_CSS;
    document.head.appendChild(link);
  }

  function loadLeaflet(cb) {
    if (window.L) {
      cb();
      return;
    }
    if (state.loading) {
      var t = setInterval(function () {
        if (window.L) {
          clearInterval(t);
          cb();
        }
      }, 50);
      return;
    }
    state.loading = true;
    ensureCss();
    var s = document.createElement("script");
    s.src = LEAFLET_JS;
    s.onload = function () {
      state.loading = false;
      cb();
    };
    s.onerror = function () {
      state.loading = false;
      setStatus("No se pudo cargar Leaflet.", true);
    };
    document.head.appendChild(s);
  }

  function setStatus(msg, isErr) {
    var el = document.getElementById("wn_radar_status");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("sira-owm-radar-status--err", !!isErr);
  }

  function destroy() {
    if (state.map) {
      try {
        state.map.remove();
      } catch (_e) {}
    }
    state.map = null;
    state.precip = null;
    state.ready = false;
  }

  function centerFromMeta(meta) {
    var lat = 40.2;
    var lon = -3.7;
    var zoom = 6;
    if (meta && typeof meta === "object") {
      if (typeof meta.lat === "number") lat = meta.lat;
      if (typeof meta.lon === "number") lon = meta.lon;
      if (typeof meta.zoom === "number") zoom = meta.zoom;
    }
    return { lat: lat, lon: lon, zoom: zoom };
  }

  function initMap(meta) {
    var el = document.getElementById("wn_radar_map");
    if (!el || !window.L) return;

    if (state.map) {
      var c = centerFromMeta(meta);
      state.map.setView([c.lat, c.lon], c.zoom);
      setTimeout(function () {
        state.map.invalidateSize();
      }, 80);
      return;
    }

    var c = centerFromMeta(meta);
    state.map = L.map(el, {
      zoomControl: true,
      attributionControl: true,
    }).setView([c.lat, c.lon], c.zoom);

    // CARTO basemaps ahora exigen API key; Esri Dark Gray no.
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles &copy; Esri",
        maxZoom: 16,
      }
    ).addTo(state.map);

    var layer =
      (meta && meta.layer) || "precipitation_new";
    state.precip = L.tileLayer(
      "/api/owm/tiles/" + layer + "/{z}/{x}/{y}.png",
      {
        opacity: 0.72,
        maxZoom: 18,
        attribution:
          'Precipitación &copy; <a href="https://openweathermap.org/">OpenWeather</a>',
      }
    ).addTo(state.map);

    state.ready = true;
    setTimeout(function () {
      if (state.map) state.map.invalidateSize();
    }, 120);
  }

  function onPage(pathname, meta) {
    if (pathname !== "/lab" && pathname !== "/weathernext") {
      destroy();
      return;
    }
    if (meta && meta.ok === false) {
      destroy();
      setStatus(
        (meta && meta.detail) ||
          "Configura OPENWEATHER_API_KEY en .env para ver la precipitación.",
        true
      );
      return;
    }
    loadLeaflet(function () {
      fetch("/api/owm/status", { credentials: "same-origin" })
        .then(function (r) {
          return r.json();
        })
        .then(function (st) {
          if (!st || !st.ok) {
            destroy();
            setStatus(
              (st && st.detail) ||
                "OPENWEATHER_API_KEY no configurada en .env",
              true
            );
            return;
          }
          var merged = Object.assign({}, meta || {}, {
            ok: true,
            layer: st.layer || "precipitation_new",
          });
          setStatus(
            "Precipitación OpenWeather (ahora) · capa " + merged.layer,
            false
          );
          initMap(merged);
        })
        .catch(function () {
          setStatus("No se pudo comprobar el estado OpenWeather.", true);
        });
    });
  }

  window.SiraOwmRadar = {
    onPage: onPage,
    invalidate: function () {
      if (state.map) state.map.invalidateSize();
    },
  };
})();
