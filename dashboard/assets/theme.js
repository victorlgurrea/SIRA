/** SIRA — modo claro / oscuro (localStorage + prefers-color-scheme) */
(function () {
  var KEY = "sira-theme";

  function preferred() {
    try {
      var saved = localStorage.getItem(KEY);
      if (saved === "light" || saved === "dark") return saved;
    } catch (e) { /* ignore */ }
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
    return "dark";
  }

  function metaColor(theme) {
    return theme === "light" ? "#f1f5f9" : "#0a1628";
  }

  function apply(theme) {
    var t = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    try {
      localStorage.setItem(KEY, t);
    } catch (e) { /* ignore */ }
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", metaColor(t));
    return t;
  }

  function toggle(current) {
    var next = current === "light" ? "dark" : "light";
    return apply(next);
  }

  window.siraTheme = { preferred: preferred, apply: apply, toggle: toggle, metaColor: metaColor };
  apply(preferred());
})();
