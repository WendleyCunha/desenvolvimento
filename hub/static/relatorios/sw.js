/* sw.js — deixa o hub instalável como app (celular e computador).
   Não guarda tela nem dado de ninguém: só o ícone, para mostrar um aviso
   quando abrir sem sinal. Servido em /relatorios/sw.js (escopo só do app Relatórios). */
const CACHE = "wd-rel-v3";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["/static/app/icone-192.png"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("wd-rel") && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request).catch(() => new Response(
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f1e6;color:#162033;font:15px Inter,system-ui,sans-serif;text-align:center;padding:24px">' +
    '<div><img src="/static/app/icone-192.png" width="96" height="96" style="border-radius:24px"><h2 style="font-weight:600;margin:16px 0 6px">Sem conexão</h2>' +
    '<p style="color:#475369">Confira o sinal e tente de novo.</p><button onclick="location.reload()" style="margin-top:10px;padding:10px 18px;border-radius:12px;border:1px solid #c48a12;background:transparent;color:#8a5f08;font:inherit">Tentar de novo</button></div>',
    { headers: { "Content-Type": "text/html; charset=utf-8" } })));
});

/* Lembrete do relatório: notificação do sistema (Android, Windows, Mac, iPhone com o app instalado) */
/* recibo: o aparelho avisa o Secretário que o lembrete CHEGOU e quando a pessoa ABRIU (só o id do lembrete) */
function recibo(id, ev) {
  if (!id) return Promise.resolve();
  const base = new URL(self.registration.scope).pathname.replace(/\/relatorios\/?$/, "");
  return fetch(base + "/api/relatorios-publico/lembretes/recibo", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, ev }), keepalive: true }).catch(() => {});
}
self.addEventListener("push", (e) => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch (_) { d = { titulo: "Relatório", texto: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.titulo || "Relatório de serviço", {
    body: d.texto || "", tag: d.tag || undefined, renotify: true, requireInteraction: true,
    icon: "/static/app/icone-192.png", badge: "/static/app/icone-192.png", data: { url: d.url || self.registration.scope, id: d.id || "" } })
    .then(() => recibo(d.id, "chegou")));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || self.registration.scope;
  recibo(e.notification.data && e.notification.data.id, "abriu");
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((ws) => {
    const w = ws.find((x) => x.url.startsWith(self.registration.scope));
    return w ? w.focus() : self.clients.openWindow(url);
  }));
});
