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
    icon: data.icon || "/assets/logo-sira.png?v=8",
    badge: data.badge || "/assets/logo-sira.png?v=8",
    tag: data.tag || "sira-alerta",
    data: { url: data.url || "/" },
    renotify: Boolean(data.renotify),
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification && event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(clients.openWindow(url));
});
