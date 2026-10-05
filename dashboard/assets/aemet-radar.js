/**
 * Mapa LAB unificado: provincias por T.máx + radar precipitación (RainViewer).
 * Base Esri (Carto libre ya exige API key).
 */
(function () {
  "use strict";

  var LEAFLET_CSS =
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css";
  var LEAFLET_JS =
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js";

  var state = {
    map: null,
    base: null,
    prov: null,
    radar: null,
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

  function destroy() {
    if (state.map) {
      try {
        state.map.remove();
      } catch (_e) {}
    }
    state.map = null;
    state.base = null;
    state.prov = null;
    state.radar = null;
  }

  function ensureMap(el) {
    if (state.map) return state.map;
    state.map = L.map(el, { zoomControl: true, preferCanvas: true }).setView(
      [40.0, -3.5],
      6
    );
    // Sin API key: Esri Dark Gray Canvas.
    state.base = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles &copy; Esri",
        maxZoom: 16,
      }
    ).addTo(state.map);
    return state.map;
  }

  function styleProv(feature) {
    var p = (feature && feature.properties) || {};
    return {
      fillColor: p.color || "rgba(100,116,139,0.35)",
      fillOpacity: 0.52,
      color: p.activa ? "#22d3ee" : "rgba(15,23,42,0.55)",
      weight: p.activa ? 2.2 : 0.7,
      opacity: 1,
    };
  }

  function onEachProv(feature, layer) {
    var p = feature.properties || {};
    var t =
      p.temp_max_c == null ? "—" : Number(p.temp_max_c).toFixed(1) + " °C";
    var pr =
      p.precip_24h_mm == null
        ? "—"
        : Number(p.precip_24h_mm).toFixed(1) + " mm";
    var html =
      "<b>" +
      (p.nombre || p.id) +
      "</b><br>T.máx 24 h: <b>" +
      t +
      "</b><br>Precip 24 h: " +
      pr;
    layer.bindTooltip(html, {
      sticky: true,
      direction: "top",
      opacity: 0.95,
      className: "sira-lab-tooltip",
    });
    layer.on({
      mouseover: function (e) {
        var ly = e.target;
        ly.setStyle({
          weight: 2.4,
          color: "#22d3ee",
          fillOpacity: 0.62,
        });
        if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
          ly.bringToFront();
        }
      },
      mouseout: function (e) {
        if (state.prov) state.prov.resetStyle(e.target);
      },
    });
  }

  function render(data) {
    var el = document.getElementById("wn_lab_map");
    if (!el || !window.L) return;
    el.style.display = "block";
    var map = ensureMap(el);

    if (state.prov) {
      try {
        map.removeLayer(state.prov);
      } catch (_e) {}
      state.prov = null;
    }
    if (state.radar) {
      try {
        map.removeLayer(state.radar);
      } catch (_e) {}
      state.radar = null;
    }

    if (data && data.features && data.features.length) {
      state.prov = L.geoJSON(
        { type: "FeatureCollection", features: data.features },
        { style: styleProv, onEachFeature: onEachProv }
      ).addTo(map);
    }

    var rv = data && data.rainviewer;
    if (rv && rv.host && rv.path) {
      var tmpl = rv.host + rv.path + "/256/{z}/{x}/{y}/2/1_1.png";
      state.radar = L.tileLayer(tmpl, {
        opacity: 0.68,
        maxZoom: 12,
        attribution:
          'Radar &copy; <a href="https://www.rainviewer.com/">RainViewer</a>',
      }).addTo(map);
    }

    setTimeout(function () {
      if (state.map) state.map.invalidateSize();
    }, 100);

    var bits = [];
    bits.push("T.máx por provincia (Open-Meteo)");
    if (rv) bits.push("radar precipitación (RainViewer)");
    else bits.push("sin capa radar");
    setStatus(bits.join(" · "), !rv);
  }

  function onPage(pathname, geo) {
    if (pathname !== "/lab" && pathname !== "/weathernext") {
      destroy();
      return;
    }
    var pid =
      geo && geo.provincia_id != null ? String(geo.provincia_id) : "";
    loadLeaflet(function () {
      fetch(
        "/api/lab/mapa" + (pid ? "?provincia=" + encodeURIComponent(pid) : ""),
        { credentials: "same-origin" }
      )
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data || !data.ok) {
            setStatus(
              (data && data.detail) || "No hay datos para el mapa LAB.",
              true
            );
            return;
          }
          render(data);
        })
        .catch(function () {
          setStatus("Error al cargar el mapa LAB.", true);
        });
    });
  }

  window.SiraLabMap = { onPage: onPage };
  // Compatibilidad con callback anterior.
  window.SiraAemetRadar = {
    onPage: function (pathname) {
      onPage(pathname, null);
    },
  };
})();
