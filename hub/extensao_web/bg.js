/* Hub Web — tira a trava "não pode abrir dentro de outra página" (X-Frame-Options / CSP)
   SÓ dos sites abertos DENTRO do hub (quadros em abas do hub). Nada muda fora do hub.
   A visita sai deste computador, com a internet e os logins da própria pessoa. */
const HUB = "__HUB__";          // endereço do hub (preenchido no download)
const TIRAR = ["x-frame-options", "content-security-policy", "cross-origin-opener-policy",
  "cross-origin-embedder-policy", "cross-origin-resource-policy"].map((header) => ({ header, operation: "remove" }));
const abas = new Set();

function ehHub(url) { try { return new URL(url).host === HUB; } catch (_) { return false; } }

async function aplicar() {
  const regras = [{ id: 1, priority: 1, action: { type: "modifyHeaders", responseHeaders: TIRAR },
    condition: { resourceTypes: ["sub_frame"], initiatorDomains: [HUB.split(":")[0]] } }];
  if (abas.size) regras.push({ id: 2, priority: 1, action: { type: "modifyHeaders", responseHeaders: TIRAR },
    condition: { resourceTypes: ["sub_frame"], tabIds: [...abas] } });
  await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [1, 2], addRules: regras });
}
async function recontar() {
  abas.clear();
  for (const t of await chrome.tabs.query({})) if (t.url && ehHub(t.url)) abas.add(t.id);
  await aplicar();
}
chrome.tabs.onUpdated.addListener((id, mud, tab) => {
  const url = mud.url || tab.url; if (!url) return;
  const antes = abas.has(id);
  if (ehHub(url)) abas.add(id); else abas.delete(id);
  if (antes !== abas.has(id)) aplicar();
});
chrome.tabs.onRemoved.addListener((id) => { if (abas.delete(id)) aplicar(); });
chrome.runtime.onStartup.addListener(recontar);
chrome.runtime.onInstalled.addListener(recontar);
recontar();
