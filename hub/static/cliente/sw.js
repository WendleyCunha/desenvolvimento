/* sw.js — app do cliente (/cliente/) abre SEM INTERNET.
   Guarda só a "casca" do app (a página, o kit visual Aurora e os ícones).
   Os dados do cliente NÃO passam por aqui: o próprio app guarda o último
   carregamento e a fila de envios no aparelho (localStorage) e reenvia
   sozinho quando a internet volta. Escopo: só /cliente/. */
const CACHE = "wd-cli-v2";
const CASCA = ["/cliente/", "/static/aurora.css?v=3", "/static/claro.css?v=1", "/static/aurora.js?v=3",
  "/static/app/icone-192.png", "/static/app/icone-512.png", "/static/app/icone-180.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => Promise.all(CASCA.map((u) => c.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k.startsWith("wd-cli") && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;   // API: sempre na rede
  if (r.mode === "navigate") {   // a página: rede primeiro (sempre a versão nova); sem rede, a guardada
    e.respondWith(fetch(r).then((resp) => { const cp = resp.clone(); if (resp.ok) caches.open(CACHE).then((c) => c.put("/cliente/", cp)); return resp; })
      .catch(() => caches.match("/cliente/")));
    return;
  }
  if (CASCA.includes(u.pathname + u.search)) {   // kit visual e ícones: o guardado na hora, atualiza por trás
    e.respondWith(caches.match(r).then((guardado) => {
      const rede = fetch(r).then((resp) => { if (resp.ok) { const cp = resp.clone(); caches.open(CACHE).then((c) => c.put(r, cp)); } return resp; }).catch(() => guardado);
      return guardado || rede;
    }));
  }
});
