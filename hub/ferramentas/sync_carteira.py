"""
sync_carteira.py — gera hub/modulos/carteira.html a partir da Carteira do PQI.

A tela da Carteira é a MESMA do PQI (mesmas regras, mesma lógica, mesmos
dados): este script só troca o visual para o padrão Aurora do hub e faz as
chamadas passarem pela ponte (/pqi/api/... → pqi_ponte.py → PQI).

Quando a Carteira mudar no PQI, rode de novo:
    python hub/ferramentas/sync_carteira.py  <pasta do repositório PQI>
(gera hub/modulos/carteira.html e hub/static/pqi-acesso.js)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]

META = """<meta name="hub-icone" content="caixa">
<meta name="hub-cor" content="#60a5fa">
<meta name="hub-grupo" content="Operação">
<meta name="hub-ordem" content="3">
<meta name="hub-descricao" content="Carteira de Encomendas do PQI — os mesmos dados, ao vivo: a equipe trabalha no PQI e você aqui.">
<script type="application/json" id="hub-permissoes">
{"acoes": {"acessar": "Abrir a Carteira (cada pessoa entra com o próprio usuário do PQI; as permissões de aba são as do PQI)"}, "campos": {}}
</script>
<meta name="theme-color" content="#05060a">
<link rel="icon" href="data:,">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/aurora.css?v=3">"""

# Paleta do hub (escuro = padrão; claro quando o tema escolhido em Aparência é claro)
PALETA = """:root{
  --paper:#0b0d14; --sheet:rgba(20,24,35,.88); --ink:#eef0f5; --ink-2:#b3b9c7; --ink-3:#7f879a;
  --rule:rgba(255,255,255,.10); --rule-2:rgba(255,255,255,.05); --steel:var(--ouro,#e8b33d); --steel-soft:rgba(var(--ouro-rgb,232,179,61),.14);
  --amber:#fb923c; --amber-soft:rgba(251,146,60,.15); --ok:#34d399; --ok-soft:rgba(52,211,153,.13); --bad:#fb7185; --bad-soft:rgba(251,113,133,.14);
  --prog:#60a5fa; --prog-soft:rgba(96,165,250,.14); --block:#a78bfa; --block-soft:rgba(167,139,250,.15); --idle:#8a93a3; --idle-soft:rgba(255,255,255,.06);
  --solido:#11141d;
  box-sizing:border-box; padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
html[data-claro]{
  --paper:#f4f6f9; --sheet:rgba(255,255,255,.86); --ink:#162033; --ink-2:#475369; --ink-3:#7b8598;
  --rule:rgba(22,32,51,.13); --rule-2:rgba(22,32,51,.06); --steel-soft:rgba(var(--ouro-rgb,232,179,61),.16);
  --amber:#c2710c; --amber-soft:#fbefd9; --ok:#0f9f6e; --ok-soft:#e1f2e7; --bad:#d23a55; --bad-soft:#f9e2e6;
  --prog:#2f6fe0; --prog-soft:#e1ebf8; --block:#6d48e0; --block-soft:#eee7f8; --idle:#8a93a3; --idle-soft:#eef0f3;
  --solido:#ffffff;
}"""

EXTRA_CSS = """<style>
/* ═══ Visual do hub (Aurora) por cima da Carteira do PQI ═══ */
body{background:var(--noite,#05060a);font-family:var(--sans)}
.wrap,.bar{position:relative;z-index:1}
.bar{background:color-mix(in srgb,var(--solido) 72%,transparent);backdrop-filter:saturate(160%) blur(18px);-webkit-backdrop-filter:saturate(160%) blur(18px);border-bottom:1px solid var(--rule)}
.box,.tbl-wrap,.filtros,.kpi,.setor-card,.sit-card,.tri-kpi,.etapa-b,.card-cx,.fbar,.mainnav,.side-rg,.lembrete,.est-item,.pg-col,.rs-area,.mot-card,.doc-head,.tri-prog,.fx-card{
  backdrop-filter:saturate(150%) blur(16px);-webkit-backdrop-filter:saturate(150%) blur(16px)}
.box,.tbl-wrap,.kpi,.setor-card,.sit-card,.doc-head,.mainnav,.side-rg{border-radius:16px}
button.primary,.mainnav button[aria-selected="true"]{background:var(--grad-ouro,var(--steel));border-color:transparent;color:#1a1206;font-weight:650}
button,.btn{border-radius:10px}
input,select,textarea{background:color-mix(in srgb,var(--solido) 70%,transparent);border-radius:10px}
dialog,.pop-caixa,#popTrf .trf-caixa{background:var(--solido);color:var(--ink)}
dialog .acts,.pp-conf{background:var(--solido)}
th{background:color-mix(in srgb,var(--solido) 94%,var(--ink) 6%)}
.toast{background:var(--solido);color:var(--ink);border:1px solid var(--rule);border-left:4px solid var(--steel)}
.kpi-lead{background:var(--grad-ouro,var(--steel));color:#1a1206} .kpi-lead > span,.kpi-lead small{color:rgba(26,18,6,.75)}
.side-btn .n{color:#1a1206}
section > header{border-bottom-color:color-mix(in srgb,var(--steel) 55%,transparent)}
.hub-marca{display:flex;align-items:center;gap:10px;margin-right:8px}
.hub-marca b{display:block;font:700 1rem var(--titulo)} .hub-marca small{display:block;font-size:.55rem;letter-spacing:2px;text-transform:uppercase;font-weight:700;color:var(--steel)}
.hub-pqi{font-size:12px;color:var(--ink-3);display:flex;align-items:center;gap:6px}
.hub-pqi a{color:var(--ink-3)}
.hub-gate{max-width:440px;margin:8vh auto;padding:26px 28px;border-radius:22px;background:var(--sheet);border:1px solid var(--rule);backdrop-filter:blur(18px)}
.hub-gate h2{margin:12px 0 6px;font:700 1.3rem var(--titulo)} .hub-gate p{color:var(--ink-3);font-size:14px;margin:0 0 14px}
.hub-gate label{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-2);margin-bottom:10px}
.hub-gate .erro{color:var(--bad);font-size:13px;min-height:18px}
</style>"""

PORTEIRO_JS = """<script src="/static/aurora.js?v=3"></script>
<script>
/* ═══ hub: fundo Aurora + porteiro da ponte com o PQI ═══ */
Aurora.fundo();
(() => { const m = document.getElementById("hubLogo"); if (m) m.outerHTML = Aurora.orbe("caixa", "#60a5fa"); })();
window.hubPqi = async function (iniciar) {
  let st = null;
  try { st = await Aurora.api("/api/pqi/status"); } catch (e) { document.getElementById("root").innerHTML = '<div class="conflito">' + Aurora.esc(e.message) + "</div>"; return; }
  if (st.conectado) {
    const el = document.getElementById("hubPqi");
    el.innerHTML = "PQI: <b>" + Aurora.esc(st.nome || st.email) + "</b> · <a href=\\"#\\" id=\\"hubSair\\">desconectar</a>";
    document.getElementById("hubSair").onclick = async (ev) => { ev.preventDefault();
      if (!(await Aurora.confirmar("Desconectar do PQI neste hub? A sessão lá também é encerrada.", { rotulo: "Desconectar" }))) return;
      await Aurora.api("/api/pqi/desconectar", { method: "POST" }).catch(() => {}); location.reload(); };
    return iniciar();
  }
  document.getElementById("menu").hidden = true;
  document.getElementById("whoTxt").textContent = "Não conectado ao PQI";
  document.getElementById("root").innerHTML = `<div class="hub-gate">${Aurora.orbe("caixa", "#60a5fa")}
    <h2>Conectar ao PQI</h2><p>A Carteira daqui é a mesma do PQI, ao vivo. Entre com o <b>seu usuário do PQI</b> — o que você fizer aqui aparece lá com o seu nome. A senha não fica guardada no hub.</p>
    <form id="hubForm"><label>E-mail do PQI<input id="hubEmail" type="email" autocomplete="username" required></label>
    <label>Senha do PQI<input id="hubSenha" type="password" autocomplete="current-password" required></label>
    <div class="erro" id="hubErro"></div><button type="submit" class="primary" id="hubBt">Conectar</button></form></div>`;
  document.getElementById("hubForm").onsubmit = async (ev) => {
    ev.preventDefault(); const bt = document.getElementById("hubBt"); bt.disabled = true; bt.textContent = "Conectando… (o PQI pode levar 1 min para acordar)";
    try { await Aurora.api("/api/pqi/conectar", { method: "POST", body: { email: document.getElementById("hubEmail").value, senha: document.getElementById("hubSenha").value } }); location.reload(); }
    catch (e) { document.getElementById("hubErro").textContent = e.message; bt.disabled = false; bt.textContent = "Conectar"; }
  };
};
</script>"""


def gerar(pqi: Path) -> None:
    src = (pqi / "carteira.html").read_text(encoding="utf-8")
    h = src

    # 1) cabeçalho: título, fontes, metas do hub, kit Aurora, acesso pela ponte
    h = re.sub(r"<title>.*?</title>", "<title>Carteira</title>", h, count=1)
    h = re.sub(r'<link rel="preconnect" href="https://fonts.googleapis.com">\s*<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\s*<link href="https://fonts.googleapis.com/css2\?family=IBM[^"]*" rel="stylesheet">',
               META.replace("\\", "\\\\"), h, count=1)
    h = h.replace('<script src="/pqi-acesso.js" data-modulo="carteira"></script>',
                  '<!-- gerado por hub/ferramentas/sync_carteira.py a partir do PQI — não edite à mão -->\n<script src="/static/pqi-acesso.js?v=1" data-modulo="carteira"></script>', 1)

    # 2) paleta: troca os blocos :root / tema escuro do PQI pela paleta do hub
    ini = h.index(":root{")
    fim = h.index("html{scroll-padding-top")
    h = h[:ini] + PALETA + "\n" + h[fim:]
    h = h.replace('"IBM Plex Sans Condensed","Arial Narrow","IBM Plex Sans",system-ui,sans-serif', "var(--titulo)")
    h = h.replace('"IBM Plex Sans Condensed"', "'Space Grotesk'").replace('"IBM Plex Sans"', "'Inter'")
    h = h.replace("</style>\n</head>", "</style>\n" + EXTRA_CSS + "\n</head>", 1)

    # 3) barra do topo com a marca do hub e o estado da conexão com o PQI
    h = h.replace('<div class="bar"><div class="bar-in">',
                  '<div class="bar"><div class="bar-in">\n  <span class="hub-marca"><span id="hubLogo"></span><span><b>Carteira</b><small>PQI · ao vivo</small></span></span>', 1)
    h = h.replace('<span class="who" id="who">', '<span class="hub-pqi" id="hubPqi"></span>\n  <span class="who" id="who">', 1)

    # 4) chamadas: tudo pela ponte /pqi/api
    for a, b in (('"/api/carteira"', '"/pqi/api/carteira"'), ('"/api/auth/me"', '"/pqi/api/auth/me"'), ('"/api/base/cadastros"', '"/pqi/api/base/cadastros"')):
        if a not in h:
            raise SystemExit(f"não achei {a} na carteira do PQI — confira o script")
        h = h.replace(a, b)
    h = h.replace("<b>Sua sessão expirou.</b> Entre de novo pelo Painel. <a href=\"/\" target=\"_top\">Ir para o Painel</a>",
                  "<b>A conexão com o PQI caiu.</b> <a href=\"#\" onclick=\"location.reload();return false\">Conectar de novo</a>")

    # 5) porteiro: só inicia depois de conferir a conexão com o PQI
    h = h.replace('<script>\n\'use strict\';', PORTEIRO_JS + "\n<script>\n'use strict';", 1)
    if "\niniciar();\n</script>" not in h:
        raise SystemExit("não achei a chamada iniciar() no fim da carteira do PQI")
    h = h.replace("\niniciar();\n</script>", "\nhubPqi(iniciar);\n</script>", 1)

    (HUB / "modulos" / "carteira.html").write_text(h, encoding="utf-8")

    # pqi-acesso.js pela ponte
    js = (pqi / "pqi-acesso.js").read_text(encoding="utf-8")
    js = js.replace('fetchOriginal("/api/auth/me"', 'fetchOriginal("/pqi/api/auth/me"')
    js = js.replace('return u.indexOf("/api/") === 0 || u.indexOf(location.origin + "/api/") === 0;',
                    'return /^\\/(pqi\\/)?api\\//.test(u) || u.indexOf(location.origin + "/pqi/api/") === 0;')
    js = js.replace('alvo.indexOf("/api/auth/") < 0', 'alvo.indexOf("/api/auth/") < 0 && alvo.indexOf("/api/pqi/") < 0')
    (HUB / "static" / "pqi-acesso.js").write_text("/* cópia do PQI ajustada para a ponte do hub — gerada por hub/ferramentas/sync_carteira.py */\n" + js, encoding="utf-8")
    print("ok:", HUB / "modulos" / "carteira.html")


if __name__ == "__main__":
    gerar(Path(sys.argv[1] if len(sys.argv) > 1 else "../PQI"))
