/* sw.js — deixa o hub instalável como app (celular e computador).
   Não guarda tela nem dado de ninguém: só o ícone, para mostrar um aviso
   quando abrir sem sinal. Servido em /sw.js para valer no site inteiro. */
const CACHE = "wd-app-v1";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["/static/app/icone-192.png"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("wd-app") && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request).catch(() => new Response(
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#05060a;color:#eef0f5;font:15px Inter,system-ui,sans-serif;text-align:center;padding:24px">' +
    '<div><img src="/static/app/icone-192.png" width="96" height="96" style="border-radius:24px"><h2 style="font-weight:600;margin:16px 0 6px">Sem conexão</h2>' +
    '<p style="color:#a3a9b8">Confira o sinal e tente de novo.</p><button onclick="location.reload()" style="margin-top:10px;padding:10px 18px;border-radius:12px;border:1px solid #e8b33d;background:transparent;color:#f5d27a;font:inherit">Tentar de novo</button></div>',
    { headers: { "Content-Type": "text/html; charset=utf-8" } })));
});
