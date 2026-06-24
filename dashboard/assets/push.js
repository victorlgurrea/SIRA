(function () {
  let pushActive = false;

  function b64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
    return outputArray;
  }

  function setStatus(text, ok) {
    const el = document.getElementById("push-status");
    if (!el) return;
    el.textContent = text;
    el.style.color = ok ? "#22c55e" : "#94a3b8";
  }

  async function getApiBase() {
    const meta = document.getElementById("sira-meta");
    if (!meta || !meta.dataset.apiBase) throw new Error("API base no disponible");
    return meta.dataset.apiBase.replace(/\/+$/, "");
  }

  async function setupPush() {
    const button = document.getElementById("push-btn");
    if (!button) return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      button.disabled = true;
      setStatus("Push no soportado en este navegador", false);
      return;
    }

    async function registerOrUpdatePush() {
      const apiBase = await getApiBase();
      const swReg = await navigator.serviceWorker.register("/assets/sw.js");
      const keyRes = await fetch(apiBase + "/api/push/public-key");
      if (!keyRes.ok) throw new Error("No se pudo obtener VAPID public key");
      const keyData = await keyRes.json();
      const vapidKey = keyData.public_key;
      let sub = await swReg.pushManager.getSubscription();
      if (!sub) {
        sub = await swReg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: b64ToUint8Array(vapidKey),
        });
      }
      const provincia = document.getElementById("geo-provincia");
      const municipio = document.getElementById("geo-municipio");
      const localidad = document.getElementById("geo-localidad");
      const payload = {
        ...sub.toJSON(),
        provincia_id: provincia ? provincia.value : null,
        municipio_id: municipio ? municipio.value : null,
        localidad_id: localidad ? localidad.value : null,
        alertas: ["sismo"],
      };
      const saveRes = await fetch(apiBase + "/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!saveRes.ok) throw new Error("No se pudo guardar suscripción");
      const muniTxt = municipio && municipio.options && municipio.selectedIndex >= 0
        ? municipio.options[municipio.selectedIndex].text
        : "";
      setStatus(muniTxt ? `Push activo (${muniTxt})` : "Push activo", true);
      pushActive = true;
    }

    button.addEventListener("click", async function () {
      button.disabled = true;
      try {
        setStatus("Registrando push...", false);
        await registerOrUpdatePush();
      } catch (err) {
        console.error(err);
        setStatus("Error al activar push", false);
      } finally {
        button.disabled = false;
      }
    });

    // Si el usuario cambia la zona en el selector, actualiza automáticamente
    // la suscripción ya activa para notificar solo la zona actual.
    ["geo-provincia", "geo-municipio", "geo-localidad"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("change", async function () {
        if (!pushActive) return;
        try {
          await registerOrUpdatePush();
        } catch (err) {
          console.error(err);
          setStatus("Push activo, pero no se actualizó zona", false);
        }
      });
    });
  }

  window.addEventListener("load", setupPush);
})();
