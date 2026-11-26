/* Hub Web — YouTube aberto DENTRO do módulo Web do hub (só quando o quadro é do hub).
   O site completo do YouTube num quadro trava ao tocar vídeo. Aqui ele vira só "vitrine":
   ao escolher um vídeo, o hub abre o PLAYER OFICIAL (embed), que toca inteiro. */
(function () {
  var HUB = "__ESQUEMA__://__HUB__";
  if (window.top === window) return;
  var anc = (location.ancestorOrigins && location.ancestorOrigins[0]) || "";
  if (anc !== HUB) return;   // fora do hub: não faz nada
  var VIDEO = /^\/(watch|shorts\/|live\/)/;
  var enviado = "";
  function abrir(u) {
    if (!u || u === enviado) return;
    enviado = u;
    try { parent.postMessage({ hubWeb: "abrir", url: u }, HUB); } catch (_) {}
  }
  // 1) clique num vídeo → abre o player oficial (antes do YouTube trocar a página)
  document.addEventListener("click", function (e) {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null; if (!a) return;
    var u; try { u = new URL(a.getAttribute("href"), location.href); } catch (_) { return; }
    if (!/(^|\.)youtube\.com$/.test(u.hostname) || !VIDEO.test(u.pathname)) return;
    e.preventDefault(); e.stopImmediatePropagation(); abrir(u.href);
  }, true);
  // 2) se mesmo assim a página foi para um vídeo (teclado, prévia, link interno) → idem
  setInterval(function () { if (VIDEO.test(location.pathname)) abrir(location.href); }, 400);
  // 3) prévias que tocam sozinhas ao passar o mouse (também derrubam o quadro): pausa
  document.addEventListener("play", function (e) { var v = e.target; if (v && v.tagName === "VIDEO") { try { v.pause(); v.muted = true; } catch (_) {} } }, true);
})();
