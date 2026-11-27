/* sw.js — link de atendimento (/atendimento/): só NOTIFICAÇÕES (a central chamando o cliente).
   Não guarda nada offline. Ao tocar no aviso, abre (ou traz para frente) a conversa. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("push", (e) => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch (_) { d = { titulo: "Atendimento", texto: e.data ? e.data.text() : "" }; }
  /* chamada da central: limpa o aviso anterior da central e mostra o novo (caminho livre, toca de novo) */
  const limpar = String(d.tag || "").startsWith("central-")
    ? self.registration.getNotifications().then((ns) => ns.filter((n) => String(n.tag || "").startsWith("central-")).forEach((n) => n.close())).catch(() => {})
    : Promise.resolve();
  e.waitUntil(limpar.then(() => self.registration.showNotification(d.titulo || "Atendimento", {
    body: d.texto || "", tag: d.tag || undefined, renotify: !!d.tag, requireInteraction: String(d.tag || "").startsWith("central-"), vibrate: [180, 80, 180],
    icon: "/static/app/icone-192.png", badge: "/static/app/icone-192.png", data: { url: d.url || self.registration.scope } })));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || self.registration.scope;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((ws) => {
    if (new URL(url, self.location.origin).pathname.indexOf("/atendimento") < 0) return self.clients.openWindow(url);   // ex.: pesquisa CSAT/NPS
    const w = ws.find((x) => new URL(x.url).pathname.indexOf("/atendimento") >= 0);
    if (w) return w.focus();
    return self.clients.openWindow(url);
  }));
});
