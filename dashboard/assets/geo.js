(function () {
  function apiBase() {
    const meta = document.getElementById("sira-meta");
    return (meta && meta.dataset.apiBase) || "";
  }

  function init() {
    const btn = document.getElementById("geo-locate-btn");
    if (!btn || btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", function () {
      if (!navigator.geolocation) {
        window.alert("Tu navegador no soporta geolocalización.");
        return;
      }
      btn.disabled = true;
      btn.textContent = "Localizando…";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          const url =
            apiBase() +
            "/api/geo/municipio-cercano?lat=" +
            encodeURIComponent(pos.coords.latitude) +
            "&lon=" +
            encodeURIComponent(pos.coords.longitude);
          fetch(url)
            .then(function (r) {
              if (!r.ok) throw new Error("API " + r.status);
              return r.json();
            })
            .then(function (data) {
              window.__siraGeoLocateResult = data;
            })
            .catch(function () {
              window.alert("No se pudo resolver el municipio más cercano.");
            })
            .finally(function () {
              btn.disabled = false;
              btn.textContent = "Usar mi ubicación";
            });
        },
        function () {
          btn.disabled = false;
          btn.textContent = "Usar mi ubicación";
          window.alert("Permiso de ubicación denegado o no disponible.");
        },
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 }
      );
    });
  }

  document.addEventListener("DOMContentLoaded", init);
  document.addEventListener("dash-rendered", init);
})();
