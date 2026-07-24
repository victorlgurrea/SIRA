(function () {
  function resizeHistorial() {
    var root = document.getElementById("historial");
    if (!root) return;
    var plot = root.querySelector(".js-plotly-plot");
    if (plot && window.Plotly && window.Plotly.Plots) {
      window.Plotly.Plots.resize(plot);
    }
  }

  window.addEventListener("popstate", function () {
    setTimeout(resizeHistorial, 150);
  });

  document.addEventListener("click", function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest("a[href='/historial']") : null;
    if (a) {
      setTimeout(resizeHistorial, 200);
    }
  });
})();
