self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = {};
  }
  const title = data.title || "SIRA";
  const options = {
    body: data.body || "Nueva alerta",
    icon: data.icon || "/assets/logo-sira_4.png?v=8",
    badge: data.badge || "/assets/logo-sira_4.png?v=8",
    tag: data.tag || "sira-alerta",
    data: { url: data.url || "/" },
    renotify: Boolean(data.renotify),
  };
  event.waitUntil(
    (async () => {
      await self.registration.showNotification(title, options);
      const allClients = await clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of allClients) {
        client.postMessage({
          type: "SIRA_PUSH_RECEIVED",
          at: Date.now(),
          tag: options.tag || "sira-alerta",
        });
      }
      try {
        const bc = new BroadcastChannel("sira-push");
        bc.postMessage({ type: "SIRA_PUSH_RECEIVED", at: Date.now(), tag: options.tag || "sira-alerta" });
        bc.close();
      } catch (e) {}
    })()
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification && event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(clients.openWindow(url));
});
