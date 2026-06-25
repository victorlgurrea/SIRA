(function () {
  let pushActive = false;
  let pushBound = false;

  const API_TIMEOUT_MS = 90000;
  const SUBSCRIBE_TIMEOUT_MS = 45000;

  function b64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
    return outputArray;
  }

  function formatError(err) {
    if (!err) return "Error al activar push";
    const name = err.name ? err.name + ": " : "";
    const msg = err.message || String(err);
    const full = (name + msg).trim();
    if (!full) return "Error al activar push";
    return full.length > 110 ? full.slice(0, 107) + "…" : full;
  }

  function setStatus(text, ok) {
    const el = document.getElementById("push-status");
    if (!el) return;
    el.textContent = text;
    el.style.color = ok ? "#22c55e" : "#94a3b8";
  }

  function withTimeout(promise, ms, message) {
    return new Promise(function (resolve, reject) {
      const timer = window.setTimeout(function () {
        reject(new Error(message));
      }, ms);
      promise.then(
        function (value) {
          window.clearTimeout(timer);
          resolve(value);
        },
        function (err) {
          window.clearTimeout(timer);
          reject(err);
        }
      );
    });
  }

  async function fetchJson(url, options) {
    const res = await withTimeout(
      fetch(url, options),
      API_TIMEOUT_MS,
      "La API tarda demasiado (plan free de Render). Espera 1 min y reintenta."
    );
    if (!res.ok) {
      throw new Error("HTTP " + res.status + " en " + url);
    }
    return res.json();
  }

  async function getApiBase() {
    const meta = document.getElementById("sira-meta");
    if (!meta || !meta.dataset.apiBase) throw new Error("API base no disponible");
    return meta.dataset.apiBase.replace(/\/+$/, "");
  }

  function getGeoPayload() {
    const el = document.getElementById("push-geo");
    if (!el) return { provincia_id: null, municipio_id: null, localidad_id: null, municipio: "" };
    return {
      provincia_id: el.dataset.provinciaId || null,
      municipio_id: el.dataset.municipioId || null,
      localidad_id: el.dataset.localidadId || null,
      municipio: el.dataset.municipio || "",
    };
  }

  async function ensureServiceWorker() {
    const regs = await navigator.serviceWorker.getRegistrations();
    await Promise.all(
      regs
        .filter(function (reg) {
          return reg.scope.includes("/assets/");
        })
        .map(function (reg) {
          return reg.unregister();
        })
    );
    const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
    if (!reg.active) {
      throw new Error("Service worker no activo tras el registro");
    }
    return reg;
  }

  async function ensureNotificationPermission() {
    if (!("Notification" in window)) {
      throw new Error("Este navegador no expone Notification API");
    }
    if (Notification.permission === "granted") return;
    if (Notification.permission === "denied") {
      throw new Error("Notificaciones bloqueadas. Actívalas en ajustes del navegador.");
    }
    setStatus("Acepta el permiso de notificaciones…", false);
    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      throw new Error("Permiso de notificaciones denegado");
    }
  }

  async function subscribePush(swReg, vapidKey) {
    const keyBytes = b64ToUint8Array(vapidKey);
    if (keyBytes.length !== 65) {
      throw new Error("Clave VAPID inválida (se esperaban 65 bytes)");
    }

    let sub = await swReg.pushManager.getSubscription();
    if (sub) {
      try {
        await sub.unsubscribe();
      } catch (e) {
        console.warn("No se pudo limpiar suscripción previa", e);
      }
      sub = null;
    }

    return withTimeout(
      swReg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes,
      }),
      SUBSCRIBE_TIMEOUT_MS,
      "Tiempo agotado al suscribir push"
    );
  }

  async function setupPush() {
    const button = document.getElementById("push-btn");
    if (!button) return false;
    if (pushBound) return true;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      button.disabled = true;
      setStatus("Push no soportado en este navegador", false);
      return true;
    }

    async function registerOrUpdatePush(skipPermission) {
      if (!skipPermission) {
        await ensureNotificationPermission();
      }

      setStatus("Conectando con API…", false);
      const apiBase = await getApiBase();
      const keyData = await fetchJson(apiBase + "/api/push/public-key");
      const vapidKey = keyData.public_key;
      if (!vapidKey) throw new Error("VAPID public key vacía");

      setStatus("Preparando service worker…", false);
      const swReg = await ensureServiceWorker();

      setStatus("Registrando push…", false);
      const sub = await subscribePush(swReg, vapidKey);

      const geo = getGeoPayload();
      const payload = Object.assign({}, sub.toJSON(), {
        provincia_id: geo.provincia_id,
        municipio_id: geo.municipio_id,
        localidad_id: geo.localidad_id,
        alertas: ["sismo", "meteo"],
      });

      setStatus("Guardando suscripción…", false);
      await fetchJson(apiBase + "/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const muniTxt = geo.municipio;
      setStatus(muniTxt ? "Push activo (" + muniTxt + ")" : "Push activo", true);
      pushActive = true;
    }

    button.addEventListener("click", async function () {
      button.disabled = true;
      try {
        // El permiso debe pedirse en el primer await del clic (gesto de usuario).
        setStatus("Solicitando permiso…", false);
        await ensureNotificationPermission();
        await registerOrUpdatePush(true);
      } catch (err) {
        console.error(err);
        setStatus(formatError(err), false);
      } finally {
        button.disabled = false;
      }
    });

    const geoEl = document.getElementById("push-geo");
    if (geoEl) {
      geoEl.addEventListener("sira-geo-changed", async function () {
        if (!pushActive) return;
        try {
          await registerOrUpdatePush(true);
        } catch (err) {
          console.error(err);
          setStatus("Push activo, pero no se actualizó zona", false);
        }
      });
    }

    pushBound = true;
    return true;
  }

  function bootPush(retries) {
    setupPush().then(function (ok) {
      if (ok) return;
      if (retries <= 0) return;
      window.setTimeout(function () {
        bootPush(retries - 1);
      }, 600);
    });
  }

  window.addEventListener("load", function () {
    bootPush(20);
  });
})();
