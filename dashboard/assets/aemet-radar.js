/**
 * Radar LAB: muestra GIF AEMET nacional si está disponible;
 * si no, tiles RainViewer (manchas tipo radar) en Leaflet.
 */
(function () {
  "use strict";

  var LEAFLET_CSS =
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css";
  var LEAFLET_JS =
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";

  var state = {
    map: null,
    layer: null,
    loading: false,
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

  function destroyMap() {
    if (state.map) {
      try {
        state.map.remove();
      } catch (_e) {}
    }
    state.map = null;
    state.layer = null;
  }

  function showAemet(url) {
    var img = document.getElementById("wn_radar_img");
    var mapEl = document.getElementById("wn_radar_map");
    if (mapEl) mapEl.style.display = "none";
    destroyMap();
    if (img) {
      img.style.display = "block";
      img.src = url + (url.indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now();
    }
  }

  function showRainViewer(meta) {
    var img = document.getElementById("wn_radar_img");
    var mapEl = document.getElementById("wn_radar_map");
    if (img) {
      img.removeAttribute("src");
      img.style.display = "none";
    }
    if (mapEl) mapEl.style.display = "block";

    loadLeaflet(function () {
      if (!mapEl || !window.L) return;
      if (!state.map) {
        state.map = L.map(mapEl, { zoomControl: true }).setView([40.0, -3.5], 6);
        L.tileLayer(
          "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
          {
            attribution:
              '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; CARTO',
            maxZoom: 18,
            subdomains: "abcd",
          }
        ).addTo(state.map);
      }
      if (state.layer) {
        try {
          state.map.removeLayer(state.layer);
        } catch (_e) {}
        state.layer = null;
      }
      var host = (meta && meta.host) || "https://tilecache.rainviewer.com";
      var path = (meta && meta.path) || "";
      if (!path) {
        setStatus("RainViewer sin frame de radar.", true);
        return;
      }
      var tmpl = host + path + "/256/{z}/{x}/{y}/2/1_1.png";
      state.layer = L.tileLayer(tmpl, {
        opacity: 0.75,
        maxZoom: 12,
        attribution:
          'Radar &copy; <a href="https://www.rainviewer.com/">RainViewer</a>',
      }).addTo(state.map);
      setTimeout(function () {
        if (state.map) state.map.invalidateSize();
      }, 120);
    });
  }

  function onPage(pathname) {
    if (pathname !== "/lab" && pathname !== "/weathernext") {
      destroyMap();
      return;
    }
    fetch("/api/aemet/radar/status", { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (st) {
        if (!st) {
          setStatus("Sin respuesta del radar.", true);
          return;
        }
        if (st.mode === "aemet" && st.image_url) {
          showAemet(st.image_url);
          setStatus(
            (st.fuente || "AEMET") + " · reflectividad (dBZ)",
            false
          );
          return;
        }
        if (st.rainviewer) {
          showRainViewer(st.rainviewer);
          setStatus(
            (st.detail || "AEMET nacional no disponible") +
              " · respaldo RainViewer",
            false
          );
          return;
        }
        setStatus(st.detail || "Radar no disponible.", true);
      })
      .catch(function () {
        setStatus("Error al cargar el radar.", true);
      });
  }

  window.SiraAemetRadar = { onPage: onPage };
})();
