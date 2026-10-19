/* ═══════════════════════════════════════════════════════════════════════════
   aurora.js — Kit "Aurora Glass" · Wendley Desenvolvimento
   ───────────────────────────────────────────────────────────────────────────
   window.Aurora = {
     fundo()                      fundo aurora + constelação (leve quando embutido no hub)
     atomo(px, {mini})            HTML da marca (átomo W)
     ATOMO_SVG                    a marca em SVG estático (favicon)
     svg(nome) · orbe(ic, cor)    ícones de traço + ícone brilhante
     modal({...})                 popup de vidro  → {el, fechar}
     toast(html, botoes, opts)    aviso de vidro
     som() · notificar(t, c)      lembrete sonoro + notificação do navegador
     avisarHub(texto)             mostra o aviso também no túnel do hub
     Grade                        widgets que movem e redimensionam
   }
   ═══════════════════════════════════════════════════════════════════════════ */
(() => {
  "use strict";
  const embutido = new URLSearchParams(location.search).has("hub") || window.top !== window;

  /* ══════ API (sempre com o cookie de sessão) ══════ */
  async function api(url, { method = "GET", body } = {}) {
    const r = await fetch(url, { method, credentials: "same-origin", cache: "no-store",
      headers: body !== undefined ? { "Content-Type": "application/json" } : {}, body: body !== undefined ? JSON.stringify(body) : undefined });
    let d = null;
    try { d = await r.json(); } catch (_) {}
    if (!r.ok) { const e = new Error((d && d.detail) || ("HTTP " + r.status)); e.status = r.status; e.dados = d; throw e; }
    return d;
  }

  /* ══════ TEMA — calibração "debaixo d'água" (Configurações → Aparência) ══════
     Fica salvo no navegador (e na sua conta, quando há banco). Toda página do
     hub (túnel, módulos, login) lê a mesma chave e muda junto, ao vivo.     */
  const TEMA_CHAVE = "wd.tema.v1";
  const PRESETS = {
    abismo:   { nome: "Abismo dourado",   desc: "O original: ouro, violeta e ciano",  noite: "#05060a", aur: ["232,179,61", "139,92,246", "34,211,238", "251,113,133"], ouro: ["#e8b33d", "#f5d27a", "#a77a1c"] },
    oceano:   { nome: "Oceano profundo",  desc: "Azul e ciano, como mar aberto",      noite: "#030812", aur: ["34,211,238", "59,130,246", "16,185,129", "99,102,241"],   ouro: ["#38bdf8", "#bae6fd", "#0369a1"] },
    recife:   { nome: "Recife de coral",  desc: "Coral, turquesa e sol",              noite: "#07070c", aur: ["251,113,133", "45,212,191", "251,191,36", "168,85,247"], ouro: ["#fb923c", "#fed7aa", "#c2410c"] },
    lagoa:    { nome: "Lagoa esmeralda",  desc: "Verde-água e luz dourada",           noite: "#030a08", aur: ["52,211,153", "34,211,238", "163,230,53", "232,179,61"],   ouro: ["#34d399", "#a7f3d0", "#047857"] },
    ametista: { nome: "Ametista abissal", desc: "Violeta e magenta profundos",        noite: "#07040d", aur: ["168,85,247", "236,72,153", "99,102,241", "34,211,238"],   ouro: ["#c084fc", "#e9d5ff", "#7e22ce"] },
    polar:    { nome: "Meia-noite polar", desc: "Prata, gelo e azul",                 noite: "#04060a", aur: ["148,163,184", "96,165,250", "226,232,240", "34,211,238"], ouro: ["#cbd5e1", "#f1f5f9", "#64748b"] },
    // ── Águas claras: fundo claro (claro.css) ──
    areia:    { claro: true, nome: "Areia dourada",  desc: "Praia ao sol: areia, ouro e turquesa",  noite: "#f6f1e6", aur: ["232,179,61", "56,189,248", "251,146,60", "167,139,250"], ouro: ["#c48a12", "#e3a92e", "#8a5f08"] },
    rasas:    { claro: true, nome: "Águas rasas",    desc: "Piscina natural: ciano e azul-claro",   noite: "#eaf4f8", aur: ["34,211,238", "59,130,246", "45,212,191", "232,179,61"],  ouro: ["#0b8fb2", "#22b5d6", "#075e78"] },
    perola:   { claro: true, nome: "Pérola rosé",    desc: "Madrepérola: rosé, lilás e champanhe",  noite: "#f8f1f4", aur: ["244,114,182", "167,139,250", "251,191,36", "56,189,248"], ouro: ["#c03f78", "#e0659c", "#86214f"] },
    nevoa:    { claro: true, nome: "Névoa da manhã", desc: "Branco gelo, índigo suave e prata",     noite: "#eef1f7", aur: ["148,163,184", "99,102,241", "34,211,238", "232,179,61"],  ouro: ["#4c5bd4", "#6f7ce6", "#3237a6"] },
  };
  const TEMA_PADRAO = { preset: "abismo", prof: 0, aur: 0.55, vidro: 0.34, blur: 22, vel: 1, luz: 0, part: 1, grao: 0.06 };
  const hexRgb = (h) => { const m = h.replace("#", ""), n = parseInt(m.length === 3 ? m.split("").map((x) => x + x).join("") : m, 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(","); };
  function carregarTema() { try { return { ...TEMA_PADRAO, ...JSON.parse(localStorage.getItem(TEMA_CHAVE) || "{}") }; } catch (_) { return { ...TEMA_PADRAO }; } }
  function aplicarTema(t) {
    t = { ...TEMA_PADRAO, ...t };
    const p = PRESETS[t.preset] || PRESETS.abismo, r = document.documentElement.style;
    r.setProperty("--noite", p.noite);
    if (p.claro) document.documentElement.setAttribute("data-claro", ""); else document.documentElement.removeAttribute("data-claro");
    p.aur.forEach((c, i) => r.setProperty("--aur" + (i + 1), c));
    r.setProperty("--ouro", p.ouro[0]); r.setProperty("--ouro2", p.ouro[1]); r.setProperty("--ouro3", p.ouro[2]); r.setProperty("--ouro-rgb", hexRgb(p.ouro[0]));
    r.setProperty("--aur-op", t.aur);
    r.setProperty("--vidro-a", (0.02 + 0.16 * t.vidro).toFixed(3)); r.setProperty("--vidro-b", (0.005 + 0.06 * t.vidro).toFixed(3));
    r.setProperty("--vidro-blur", t.blur + "px"); r.setProperty("--vel", t.vel); r.setProperty("--causticas", t.luz);
    r.setProperty("--prof", t.prof); r.setProperty("--grao", t.grao); r.setProperty("--particulas", t.part);
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", p.noite);
    dispatchEvent(new CustomEvent("wd-tema", { detail: t }));
    return t;
  }
  function salvarTema(t, { conta = true } = {}) {
    t = { ...TEMA_PADRAO, ...t };
    try { localStorage.setItem(TEMA_CHAVE, JSON.stringify(t)); } catch (_) {}
    aplicarTema(t);
    if (conta) { clearTimeout(salvarTema._t); salvarTema._t = setTimeout(() => api("/api/eu/preferencias", { method: "PUT", body: { tema: t } }).catch(() => {}), 900); }
    return t;
  }
  /** Se a conta tem um tema salvo (outro computador), usa ele aqui também. */
  function temaDaConta(prefs) {
    const t = prefs && prefs.tema;
    if (t && JSON.stringify({ ...TEMA_PADRAO, ...t }) !== JSON.stringify(carregarTema())) salvarTema(t, { conta: false });
  }
  aplicarTema(carregarTema());
  addEventListener("storage", (e) => { if (e.key === TEMA_CHAVE) aplicarTema(carregarTema()); });
  const tema = { PRESETS, PADRAO: TEMA_PADRAO, carregar: carregarTema, aplicar: aplicarTema, salvar: salvarTema, daConta: temaDaConta };

  /* ══════ LUZ QUE ACOMPANHA O MOUSE (.wg e .luz) ══════ */
  let quadroLuz = 0;
  addEventListener("pointermove", (e) => {
    if (e.pointerType && e.pointerType !== "mouse") return;
    const alvos = [e.target.closest?.(".luz"), e.target.closest?.(".wg")].filter(Boolean);
    if (!alvos.length) return;
    cancelAnimationFrame(quadroLuz);
    quadroLuz = requestAnimationFrame(() => alvos.forEach((el) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", (e.clientX - r.left) + "px"); el.style.setProperty("--my", (e.clientY - r.top) + "px");
    }));
  }, { passive: true });
  const reduzido = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ══════ ÍCONES ══════ */
  const ICONES = {
    casa:'<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
    calendario:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M16 3v4M8 3v4M3 10h18"/><path d="M8 14h.01M12 14h.01M16 14h.01M8 17.5h.01M12 17.5h.01"/>',
    grafico:'<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 6-7"/><path d="M16 7h4v4"/>',
    usuarios:'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c2 .6 3.2 2.3 3.5 5.2"/>',
    usuario:'<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4 4-6 8-6s7.2 2 8 6"/>',
    dinheiro:'<rect x="2" y="6" width="20" height="12" rx="3"/><circle cx="12" cy="12" r="2.8"/><path d="M6 9.5v5M18 9.5v5"/>',
    ajustes:'<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    regua:'<path d="M3 16.5 16.5 3 21 7.5 7.5 21z"/><path d="M7.5 12l2 2M10.5 9l2 2M13.5 6l2 2"/>',
    tesoura:'<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
    caixa:'<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    escudo:'<path d="M12 3l8 3v6c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    raio:'<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    grade:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    camadas:'<path d="M12 3 2 8l10 5 10-5z"/><path d="M2 13l10 5 10-5"/><path d="M2 18l10 5 10-5" opacity=".5"/>',
    documento:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    mapa:'<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    mensagem:'<path d="M21 12a8 8 0 0 1-11.8 7L3 21l2-6.2A8 8 0 1 1 21 12z"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>',
    globo:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
    estrela:'<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    alvo:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    coracao:'<path d="M12 20s-7.5-4.6-9.2-9.4C1.6 7.2 3.8 4 7.2 4c2 0 3.6 1.1 4.8 2.8C13.2 5.1 14.8 4 16.8 4c3.4 0 5.6 3.2 4.4 6.6C19.5 15.4 12 20 12 20z"/>',
    relogio:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    pasta:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    codigo:'<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>',
    foguete:'<path d="M5 15c-1.5 1.5-2 4.5-2 6 1.5 0 4.5-.5 6-2"/><path d="M9 15l-3-3c1.5-5 5.5-9 12-9 0 6.5-4 10.5-9 12z"/><circle cx="14.5" cy="9.5" r="1.6"/>',
    sino:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    check:'<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    mais:'<path d="M12 5v14M5 12h14"/>',
    lixo:'<path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    lapis:'<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    copiar:'<rect x="8" y="8" width="13" height="13" rx="3"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
    repetir:'<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
    lista:'<path d="M9 6h12M9 12h12M9 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    kanban:'<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 3v18M15 3v18"/><path d="M5.5 7h1M11.5 7h1M17.5 7h1"/>',
    maximizar:'<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
    minimizar:'<path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/>',
    fechar:'<path d="M6 6l12 12M18 6 6 18"/>',
    busca:'<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    baixar:'<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
    subir:'<path d="M12 21V9M7 14l5-5 5 5M4 3h16"/>',
    reticencias:'<path d="M5 12h.01M12 12h.01M19 12h.01"/>',
    seta:'<path d="M5 12h14M13 6l6 6-6 6"/>',
    voltar:'<path d="M15 18l-6-6 6-6"/>',
    avancar:'<path d="M9 18l6-6-6-6"/>',
    adiar:'<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M5 3 2 6M19 3l3 3"/>',
    filtro:'<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
    widgets:'<rect x="3" y="3" width="8" height="10" rx="2"/><rect x="13" y="3" width="8" height="6" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/><rect x="3" y="15" width="8" height="6" rx="2"/>',
    cadeado:'<rect x="4" y="10" width="16" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    sair:'<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 17l5-5-5-5M15 12H4"/>',
    paleta:'<path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.6-.9 1.2-1.9-.5-1 .2-2.1 1.3-2.1H17a4 4 0 0 0 4-4c0-5.5-4-10-9-10z"/><circle cx="7.5" cy="11" r="1.2"/><circle cx="10" cy="7" r="1.2"/><circle cx="15" cy="7.5" r="1.2"/>',
    onda:'<path d="M2 12c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/><path d="M2 17c2-2 4-2 6 0s4 2 6 0 4-2 6 0" opacity=".6"/><path d="M2 7c2-2 4-2 6 0s4 2 6 0 4-2 6 0" opacity=".35"/>',
    onibus:'<rect x="4" y="3" width="16" height="15" rx="3"/><path d="M4 11h16M9 3v8M15 3v8"/><circle cx="8" cy="15" r=".8"/><circle cx="16" cy="15" r=".8"/><path d="M7 18v3M17 18v3"/>',
    atencao:'<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  };
  const svg = (nome) => `<svg viewBox="0 0 24 24" class="i" aria-hidden="true">${ICONES[nome] || ICONES.documento}</svg>`;
  const orbe = (icone, cor, extra = "") => {
    const k = String(icone || "").toLowerCase();
    return `<span class="orbe ${extra}" style="--c:${cor || "var(--ouro)"};--atraso:-${(Math.random() * 4).toFixed(1)}s">${ICONES[k] ? svg(k) : esc(icone)}</span>`;
  };

  /* ══════ MARCA ══════ */
  const atomo = (px = 44, { mini = px < 80 } = {}) =>
    `<span class="atomo${mini ? " mini" : ""}" style="--s:${px}px" aria-hidden="true"><span class="halo"></span>` +
    `<span class="anel r2"></span><span class="anel r1"></span><span class="anel r3"></span><span class="nucleo"><b>W</b></span></span>`;
  const ATOMO_SVG = "data:image/svg+xml," + encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><radialGradient id="n" cx=".32" cy=".28" r=".75"><stop offset="0" stop-color="#ffecb4"/><stop offset=".25" stop-color="#e8b33d"/><stop offset=".65" stop-color="#6b4c10"/><stop offset="1" stop-color="#120d04"/></radialGradient></defs>` +
    `<rect width="100" height="100" rx="24" fill="#05060a"/>` +
    `<g fill="none" stroke-width="3"><ellipse cx="50" cy="50" rx="44" ry="15" stroke="#f5d27a" transform="rotate(-25 50 50)"/><ellipse cx="50" cy="50" rx="44" ry="15" stroke="#8b5cf6" transform="rotate(65 50 50)"/><ellipse cx="50" cy="50" rx="40" ry="13" stroke="#22d3ee" stroke-dasharray="5 4" transform="rotate(20 50 50)"/></g>` +
    `<circle cx="50" cy="50" r="24" fill="url(#n)"/><text x="50" y="59" font-family="Arial" font-weight="800" font-size="26" text-anchor="middle" fill="#1a1206" opacity=".85">W</text></svg>`);

  /* ══════ FUNDO ══════ */
  function fundo() {
    if (embutido) document.body.classList.add("aur-embutido");
    const f = document.createElement("div");
    f.className = "aur-fundo";
    f.setAttribute("aria-hidden", "true");
    f.innerHTML = `<div class="bolha b1"></div><div class="bolha b2"></div><div class="bolha b3"></div><div class="bolha b4"></div><div class="raios"></div><div class="causticas"><i></i><i></i></div><div class="grade"></div>${embutido ? "" : "<canvas></canvas>"}<div class="prof"></div><div class="grao"></div><div class="vinheta"></div>`;
    document.body.prepend(f);
    const cv = f.querySelector("canvas");
    if (cv) constelacao(cv);
  }
  function constelacao(cv) {
    const cx = cv.getContext("2d");
    let W, H, pts = [], rato = { x: -999, y: -999 }, cores = [], linha = "232,179,61";
    const lerCores = () => {
      const cs = getComputedStyle(document.documentElement), v = (n, d) => (cs.getPropertyValue(n).trim() || d);
      linha = v("--ouro-rgb", "232,179,61");
      cores = [linha, v("--aur2", "167,139,250"), v("--aur3", "34,211,238"), "255,255,255"];
    };
    const medir = () => {
      lerCores();
      const dpr = Math.min(devicePixelRatio || 1, 2), dens = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--particulas")) || 0;
      W = innerWidth; H = innerHeight;
      cv.width = W * dpr; cv.height = H * dpr; cx.setTransform(dpr, 0, 0, dpr, 0, 0);
      pts = Array.from({ length: Math.round(Math.min(120, (W * H) / 17000) * dens) }, () => ({
        x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .22, vy: (Math.random() - .5) * .22,
        r: Math.random() * 1.5 + .4, c: cores[(Math.random() * 4) | 0], f: Math.random() * 6.3 }));
    };
    const desenhar = () => {
      cx.clearRect(0, 0, W, H);
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy; p.f += .02;
        if (p.x < -10) p.x = W + 10; if (p.x > W + 10) p.x = -10; if (p.y < -10) p.y = H + 10; if (p.y > H + 10) p.y = -10;
        const dx = p.x - rato.x, dy = p.y - rato.y, d = Math.hypot(dx, dy);
        if (d < 140 && d > 0) { p.x += dx / d * .6; p.y += dy / d * .6; }
      }
      for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i], b = pts[j], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < 120) { cx.strokeStyle = `rgba(${linha},${(1 - d / 120) * .12})`; cx.lineWidth = .6; cx.beginPath(); cx.moveTo(a.x, a.y); cx.lineTo(b.x, b.y); cx.stroke(); }
      }
      for (const p of pts) {
        cx.fillStyle = `rgba(${p.c},${.35 + Math.sin(p.f) * .3})`; cx.shadowColor = `rgba(${p.c},.9)`; cx.shadowBlur = 8;
        cx.beginPath(); cx.arc(p.x, p.y, p.r, 0, 6.283); cx.fill();
      }
      cx.shadowBlur = 0;
    };
    const laco = () => { if (!document.hidden) desenhar(); requestAnimationFrame(laco); };
    medir(); addEventListener("resize", medir); addEventListener("wd-tema", medir);
    addEventListener("pointermove", (e) => { rato.x = e.clientX; rato.y = e.clientY; }, { passive: true });
    reduzido ? desenhar() : laco();
  }

  /* ══════ POPUP DE VIDRO ══════ */
  const pilhaModais = [];   // só o popup do topo responde a Esc / Ctrl+Enter
  function confirmar(texto, { titulo = "Confirmar", rotulo = "Confirmar", perigo = false } = {}) {
    return new Promise((ok) => {
      let resp = false;
      modal({ titulo, icone: perigo ? "atencao" : "check", cor: perigo ? "var(--rosa)" : "", largura: 440,
        html: `<p style="margin:0;color:var(--txt2);line-height:1.6">${texto}</p>`,
        botoes: [{ rotulo: "Cancelar" }, { rotulo, classe: perigo ? "btn perigo" : "btn", principal: true, acao: () => { resp = true; } }],
        aoFechar: () => ok(resp) });
    });
  }
  function modal({ titulo = "", icone = "", cor = "", html = "", largura = 560, botoes = [], esquerda = [], aoAbrir, aoFechar } = {}) {
    const fundoEl = document.createElement("div");
    fundoEl.className = "aur-modal-fundo";
    const bt = (b, i, lado) => `<button type="button" class="${b.classe || "btn v"}" data-b="${lado}${i}">${b.icone ? svg(b.icone) : ""}${esc(b.rotulo)}</button>`;
    fundoEl.innerHTML = `<div class="aur-modal vidro vidro-borda-viva" role="dialog" aria-modal="true" aria-label="${esc(titulo)}" style="--larg:${largura}px">
      <div class="aur-modal-cab">${icone ? orbe(icone, cor) : ""}<h3>${esc(titulo)}</h3><button type="button" class="btn-ic" data-fechar aria-label="Fechar">${svg("fechar")}</button></div>
      <div class="aur-modal-corpo">${html}</div>
      ${botoes.length || esquerda.length ? `<div class="aur-modal-pe"><span class="esq">${esquerda.map((b, i) => bt(b, i, "e")).join("")}</span>${botoes.map((b, i) => bt(b, i, "d")).join("")}</div>` : ""}
    </div>`;
    document.body.appendChild(fundoEl);
    const caixa = fundoEl.querySelector(".aur-modal");
    let fechado = false;
    const fechar = () => {
      if (fechado) return; fechado = true;
      const i = pilhaModais.indexOf(fundoEl); if (i >= 0) pilhaModais.splice(i, 1);
      fundoEl.classList.remove("aberto");
      document.removeEventListener("keydown", tecla, true);
      setTimeout(() => fundoEl.remove(), 260);
      aoFechar && aoFechar();
    };
    const tecla = (e) => {
      if (pilhaModais[pilhaModais.length - 1] !== fundoEl) return;
      if (e.key === "Escape") { e.stopPropagation(); fechar(); }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { const p = botoes.findIndex((b) => b.principal); if (p >= 0) { e.preventDefault(); caixa.querySelector(`[data-b="d${p}"]`).click(); } }
    };
    pilhaModais.push(fundoEl);
    document.addEventListener("keydown", tecla, true);
    fundoEl.addEventListener("pointerdown", (e) => { if (e.target === fundoEl) fechar(); });
    caixa.querySelector("[data-fechar]").onclick = fechar;
    const ligar = (lista, lado) => lista.forEach((b, i) => {
      caixa.querySelector(`[data-b="${lado}${i}"]`).onclick = async () => { const r = b.acao ? await b.acao(caixa) : true; if (r !== false) fechar(); };
    });
    ligar(botoes, "d"); ligar(esquerda, "e");
    requestAnimationFrame(() => fundoEl.classList.add("aberto"));
    aoAbrir && aoAbrir(caixa);
    setTimeout(() => caixa.querySelector("[autofocus]")?.focus(), 60);
    return { el: caixa, fechar };
  }

  /* ══════ AVISOS ══════ */
  function toast(html, botoes = [], { cor = "", duracao = 5000 } = {}) {
    let box = document.querySelector(".aur-toasts");
    if (!box) { box = document.createElement("div"); box.className = "aur-toasts"; box.setAttribute("aria-live", "polite"); document.body.appendChild(box); }
    const t = document.createElement("div");
    t.className = "aur-toast vidro";
    if (cor) t.style.setProperty("--c", cor);
    t.innerHTML = `<span class="ponto"></span><div class="txt">${html}${botoes.length ? `<div class="bts">${botoes.map((b, i) => `<button type="button" class="btn ${i ? "v " : ""}p" data-i="${i}">${esc(b[0])}</button>`).join("")}</div>` : ""}</div>
      <button type="button" class="btn-ic p" aria-label="Fechar">${svg("fechar")}</button>`;
    const sair = () => { t.classList.add("sai"); setTimeout(() => t.remove(), 300); };
    t.querySelector(".btn-ic").onclick = sair;
    t.querySelectorAll("[data-i]").forEach((b) => (b.onclick = () => { botoes[+b.dataset.i][1](); sair(); }));
    box.appendChild(t);
    if (duracao) setTimeout(sair, duracao);
    return sair;
  }

  /* ══════ SOM + NOTIFICAÇÃO ══════ */
  let ctxSom;
  function som() {
    try {
      ctxSom = ctxSom || new (window.AudioContext || window.webkitAudioContext)();
      const t0 = ctxSom.currentTime;
      [[880, 0], [1320, .16]].forEach(([f, d]) => {
        const o = ctxSom.createOscillator(), g = ctxSom.createGain();
        o.type = "sine"; o.frequency.value = f;
        g.gain.setValueAtTime(0, t0 + d); g.gain.linearRampToValueAtTime(.18, t0 + d + .02); g.gain.exponentialRampToValueAtTime(.001, t0 + d + .5);
        o.connect(g).connect(ctxSom.destination); o.start(t0 + d); o.stop(t0 + d + .55);
      });
    } catch (_) {}
  }
  function notificar(titulo, corpo) {
    try { if ("Notification" in window && Notification.permission === "granted") new Notification(titulo, { body: corpo, icon: ATOMO_SVG, tag: titulo + corpo }); } catch (_) {}
  }
  function avisarHub(texto) { if (embutido) try { parent.postMessage({ hub: "aviso", texto }, "*"); } catch (_) {} }

  /* ══════ WIDGETS — GRADE (mover + redimensionar, com encaixe) ══════
     const g = new Aurora.Grade(areaEl, { colunas:12, linha:44, espaco:14, aoMudar(layout){} })
     g.adicionar({ id, x, y, w, h, minW, minH, el })   // el precisa ter .wg-cab e .wg-redim
     g.remover(id) · g.layout() · g.aplicar() · g.max(id)                                    */
  class Grade {
    constructor(area, { colunas = 12, linha = 44, espaco = 14, limiteUma = 760, aoMudar, travado = false } = {}) {
      Object.assign(this, { area, colunas, linha, espaco, limiteUma, aoMudar, travado, itens: [] });
      area.classList.add("wg-area");
      this.sombra = document.createElement("div");
      this.sombra.className = "wg-sombra";
      area.appendChild(this.sombra);
      new ResizeObserver(() => this.aplicar()).observe(area);
    }
    medir() {
      const W = this.area.clientWidth;
      this.uma = W < this.limiteUma;
      this.area.classList.toggle("uma", this.uma);
      this.ux = (W + this.espaco) / this.colunas;
      this.uy = this.linha + this.espaco;
    }
    geo(it) {
      return { left: it.x * this.ux, top: it.y * this.uy, width: it.w * this.ux - this.espaco, height: it.h * this.uy - this.espaco };
    }
    colide(a, b) { return a !== b && a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y; }
    resolver(fixo) {
      const outros = this.itens.filter((i) => i !== fixo).sort((a, b) => a.y - b.y || a.x - b.x);
      const postos = fixo ? [fixo] : [];
      for (const it of outros) {
        let mexeu = true;
        while (mexeu) { mexeu = false; for (const p of postos) if (this.colide(it, p)) { it.y = p.y + p.h; mexeu = true; } }
        postos.push(it);
      }
      for (const it of [...this.itens].sort((a, b) => a.y - b.y || a.x - b.x)) {
        if (it === fixo) continue;
        while (it.y > 0) { it.y--; if (this.itens.some((o) => this.colide(it, o))) { it.y++; break; } }
      }
    }
    aplicar(exceto) {
      this.medir();
      let alturaUma = 0, fundoMax = 0;
      const ord = [...this.itens].sort((a, b) => a.y - b.y || a.x - b.x);
      for (const it of ord) {
        if (it.el.classList.contains("max")) continue;
        let g = this.geo(it);
        if (this.uma) { g = { left: 0, top: alturaUma, width: this.area.clientWidth, height: (it.hUma || Math.max(it.h, it.minH || 3)) * this.uy - this.espaco }; alturaUma += g.height + this.espaco; }
        fundoMax = Math.max(fundoMax, g.top + g.height);
        if (it === exceto) continue;
        it.el.style.transform = `translate(${g.left}px,${g.top}px)`;
        it.el.style.width = g.width + "px";
        it.el.style.height = g.height + "px";
      }
      this.area.style.height = (fundoMax + this.espaco + (this.uma ? 0 : this.uy * 2)) + "px";
    }
    mostrarSombra(it) {
      const g = this.geo(it);
      Object.assign(this.sombra.style, { transform: `translate(${g.left}px,${g.top}px)`, width: g.width + "px", height: g.height + "px" });
      this.sombra.classList.add("on");
    }
    layout() { return this.itens.map(({ id, x, y, w, h }) => ({ id, x, y, w, h })); }
    travar(sim) { this.travado = !!sim; this.area.classList.toggle("travada", this.travado); }
    salvar() { this.aoMudar && this.aoMudar(this.layout()); }
    adicionar(def) {
      const it = { minW: 2, minH: 3, ...def };
      it.w = Math.min(Math.max(it.w, it.minW), this.colunas);
      it.x = Math.min(Math.max(0, it.x ?? 0), this.colunas - it.w);
      if (it.y == null) it.y = this.itens.reduce((m, o) => Math.max(m, o.y + o.h), 0);
      this.itens.push(it);
      this.area.appendChild(it.el);
      this.ligar(it);
      this.resolver(it);
      this.aplicar();
      return it;
    }
    remover(id) {
      const i = this.itens.findIndex((x) => x.id === id);
      if (i < 0) return;
      const [it] = this.itens.splice(i, 1);
      it.el.style.opacity = "0";
      setTimeout(() => it.el.remove(), 250);
      this.resolver(null); this.aplicar(); this.salvar();
    }
    max(id) {
      const it = this.itens.find((x) => x.id === id);
      if (!it) return;
      const on = !it.el.classList.contains("max");
      it.el.classList.toggle("max", on);
      document.body.style.overflow = on ? "hidden" : "";
      if (!on) this.aplicar();
      return on;
    }
    ligar(it) {
      const cab = it.el.querySelector(".wg-cab"), redim = it.el.querySelector(".wg-redim");
      const inicio = (e, modo) => {
        if (this.travado || this.uma || it.el.classList.contains("max") || e.button > 0) return;
        if (modo === "mover" && e.target.closest("button,input,select,textarea,a,label")) return;
        e.preventDefault();
        const g = this.geo(it), base = this.itens.map((o) => ({ o, x: o.x, y: o.y }));
        const s = { px: e.clientX, py: e.clientY, g, w: it.w, h: it.h };
        const alvo = e.currentTarget;
        alvo.setPointerCapture(e.pointerId);
        it.el.classList.add(modo === "mover" ? "arrastando" : "redimensionando");
        this.mostrarSombra(it);
        let quadro = 0, ultimo = null;
        const mover = (ev) => { ultimo = ev; cancelAnimationFrame(quadro); quadro = requestAnimationFrame(processar); };
        const processar = () => {
          {
            if (!ultimo) return;
            const ev = ultimo; ultimo = null;
            const dx = ev.clientX - s.px, dy = ev.clientY - s.py;
            let nx = it.x, ny = it.y, nw = it.w, nh = it.h;
            if (modo === "mover") {
              it.el.style.transform = `translate(${s.g.left + dx}px,${s.g.top + dy}px)`;
              nx = Math.min(Math.max(0, Math.round((s.g.left + dx) / this.ux)), this.colunas - it.w);
              ny = Math.max(0, Math.round((s.g.top + dy) / this.uy));
            } else {
              const largura = Math.max(120, s.g.width + dx), altura = Math.max(100, s.g.height + dy);
              it.el.style.width = largura + "px"; it.el.style.height = altura + "px";
              nw = Math.min(Math.max(it.minW, Math.round((largura + this.espaco) / this.ux)), this.colunas - it.x);
              nh = Math.max(it.minH, Math.round((altura + this.espaco) / this.uy));
            }
            if (nx !== it.x || ny !== it.y || nw !== it.w || nh !== it.h) {
              base.forEach((b) => { if (b.o !== it) { b.o.x = b.x; b.o.y = b.y; } });
              Object.assign(it, { x: nx, y: ny, w: nw, h: nh });
              this.resolver(it);
              this.aplicar(it);
              this.mostrarSombra(it);
            }
          }
        };
        const fim = () => {
          cancelAnimationFrame(quadro);
          processar();
          alvo.removeEventListener("pointermove", mover);
          alvo.removeEventListener("pointerup", fim);
          alvo.removeEventListener("pointercancel", fim);
          it.el.classList.remove("arrastando", "redimensionando");
          this.sombra.classList.remove("on");
          this.resolver(null);
          this.aplicar();
          this.salvar();
          it.el.dispatchEvent(new CustomEvent("wg-mudou", { bubbles: true }));
        };
        alvo.addEventListener("pointermove", mover);
        alvo.addEventListener("pointerup", fim);
        alvo.addEventListener("pointercancel", fim);
      };
      cab && cab.addEventListener("pointerdown", (e) => inicio(e, "mover"));
      redim && redim.addEventListener("pointerdown", (e) => inicio(e, "redim"));
    }
  }

  const modalAberto = () => pilhaModais.length > 0;

  /* ══════ PERMISSÕES DO USUÁRIO NO MÓDULO ══════
     const P = await Aurora.permissoes.carregar("lila")
     P.pode("excluir") · P.nivel("titulo") → "editar" | "ver" | "oculto"
     Administrador: "Modo permissões" (Configurações) mostra um escudo em cada
     elemento com data-perm="campo:xxx" | "acao:yyy" — clique para liberar ou
     bloquear aquele ponto para cada usuário.                                */
  const MODO_CHAVE = "wd.modoPerm";
  const iniciais = (n) => String(n || "?").trim().split(/\s+/).filter(Boolean).map((x) => x[0]).slice(0, 2).join("").toUpperCase() || "?";
  const permissoes = {
    estado: null, modulo: "",
    async carregar(modulo) {
      this.modulo = modulo;
      try { this.estado = await api("/api/eu?modulo=" + encodeURIComponent(modulo)); }
      catch (e) {
        if (e.status === 401) { const w = window.top || window; w.location.href = "/login?volta=" + encodeURIComponent(w.location.pathname + w.location.hash); }
        throw e;
      }
      temaDaConta(this.estado.preferencias);
      if (this.admin) {
        this._modo(localStorage.getItem(MODO_CHAVE) === "1");
        addEventListener("storage", (e) => { if (e.key === MODO_CHAVE) this._modo(e.newValue === "1"); });
      }
      return this.estado;
    },
    get usuario() { return this.estado?.usuario || null; },
    get admin() { return !!this.estado?.usuario?.admin; },
    pode(a) { return !!this.estado?.perm?.acoes?.[a]; },
    nivel(c) { return this.estado?.perm?.campos?.[c] || "editar"; },
    _modo(on) {
      document.body.classList.toggle("modo-permissoes", on);
      clearInterval(this._iv);
      this._camada?.remove(); this._faixa?.remove(); this._camada = null;
      if (!on) return;
      this._camada = document.createElement("div"); this._camada.className = "perm-camada";
      this._faixa = document.createElement("div"); this._faixa.className = "perm-faixa";
      this._faixa.innerHTML = `${svg("escudo")} Modo permissões — clique num escudo para liberar ou bloquear <button type="button">Sair</button>`;
      this._faixa.querySelector("button").onclick = () => { try { localStorage.setItem(MODO_CHAVE, "0"); } catch (_) {} this._modo(false); };
      document.body.append(this._camada, this._faixa);
      const botoes = new Map();
      const tick = () => {
        if (!this._camada) return;
        const topo = pilhaModais[pilhaModais.length - 1], vistos = new Set();
        document.querySelectorAll("[data-perm]").forEach((el) => {
          if (topo && !topo.contains(el)) return;
          const r = el.getBoundingClientRect();
          if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight) return;
          let b = botoes.get(el);
          if (!b) {
            const [tipo] = el.dataset.perm.split(":");
            b = document.createElement("button"); b.type = "button"; b.className = "perm-escudo" + (tipo === "acao" ? " acao" : "");
            b.innerHTML = svg(tipo === "acao" ? "raio" : "escudo");
            b.onclick = (ev) => { ev.stopPropagation(); this.editar(el.dataset.perm); };
            this._camada.appendChild(b); botoes.set(el, b);
          }
          const [tipo, k] = el.dataset.perm.split(":"), esq = this.estado.esquema || {};
          b.title = (tipo === "acao" ? "Ação: " : "Campo: ") + (((tipo === "acao" ? esq.acoes : esq.campos) || {})[k] || k);
          b.style.left = Math.min(innerWidth - 28, Math.max(4, r.right - 14)) + "px";
          b.style.top = Math.max(4, r.top - 10) + "px";
          vistos.add(el);
        });
        botoes.forEach((b, el) => { if (!vistos.has(el)) { b.remove(); botoes.delete(el); } });
      };
      tick(); this._iv = setInterval(tick, 200);
    },
    async editar(chave) {
      const [tipo, k] = chave.split(":"), esq = this.estado.esquema || {};
      const rot = ((tipo === "acao" ? esq.acoes : esq.campos) || {})[k] || k;
      let lista;
      try { lista = (await api("/api/admin/usuarios")).usuarios.filter((u) => !u.admin); }
      catch (e) { toast("Não consegui carregar os usuários: " + esc(e.message), [], { cor: "var(--rosa)" }); return; }
      if (!lista.length) { toast("Ainda não há usuários (além de administradores). Crie em ⚙ Configurações → Usuários.", [], { cor: "var(--violeta)", duracao: 7000 }); return; }
      const mod = this.modulo;
      const perm = (u) => (u.modulos || {})[mod] || {};
      const opcoes = tipo === "acao" ? [["1", "Permitir", "#34d399"], ["0", "Negar", "#fb7185"]] : [["editar", "Editar", "#34d399"], ["ver", "Só ver", "#60a5fa"], ["oculto", "Oculto", "#fb7185"]];
      const escolha = {};
      lista.forEach((u) => { escolha[u.login] = tipo === "acao" ? ((perm(u).acoes || {})[k] ? "1" : "0") : ((perm(u).campos || {})[k] || "editar"); });
      const seg = (login) => `<div class="seg" data-u="${esc(login)}">${opcoes.map(([v, r, c]) => `<button type="button" data-v="${v}" style="--c:${c}" class="${escolha[login] === v ? "ativo" : ""}">${r}</button>`).join("")}</div>`;
      modal({
        titulo: (tipo === "acao" ? "Ação · " : "Campo · ") + rot, icone: tipo === "acao" ? "raio" : "escudo", largura: 640,
        html: `<p style="margin:0 0 14px;color:var(--txt2);font-size:.84rem;line-height:1.6">${tipo === "acao" ? `Quem pode <b>${esc(rot)}</b>` : `O que cada pessoa pode fazer com o campo <b>${esc(rot)}</b>`} neste módulo.
            Vale a partir do próximo carregamento da pessoa e é conferido no servidor.</p>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:.75rem;color:var(--txt3)">Todos:
            ${opcoes.map(([v, r, c]) => `<button type="button" class="chip" data-todos="${v}" style="--c:${c}">${r}</button>`).join("")}</div>
          ${lista.map((u) => `<div class="perm-linha"><span class="av">${iniciais(u.nome)}</span><div><b>${esc(u.nome)}</b><small>@${esc(u.login)}${k !== "acessar" && !(perm(u).acoes || {}).acessar ? " · ainda sem acesso ao módulo" : ""}${u.ativo ? "" : " · inativo"}</small></div>${seg(u.login)}</div>`).join("")}`,
        botoes: [{ rotulo: "Cancelar" }, { rotulo: "Salvar", classe: "btn", icone: "check", principal: true, acao: async () => {
          const valores = {};
          Object.entries(escolha).forEach(([l, v]) => { valores[l] = tipo === "acao" ? v === "1" : v; });
          try { await api("/api/admin/permissao", { method: "PUT", body: { modulo: mod, tipo, chave: k, valores } }); toast(`✓ <b>${esc(rot)}</b> atualizado para ${lista.length} usuário(s).`, [], { cor: "var(--verde)" }); }
          catch (e) { toast("Não salvou: " + esc(e.message), [], { cor: "var(--rosa)" }); return false; }
        } }],
        aoAbrir(cx) {
          cx.addEventListener("click", (ev) => {
            const b = ev.target.closest(".seg[data-u] button");
            if (b) { escolha[b.parentElement.dataset.u] = b.dataset.v; b.parentElement.querySelectorAll("button").forEach((x) => x.classList.toggle("ativo", x === b)); }
            const t = ev.target.closest("[data-todos]");
            if (t) { Object.keys(escolha).forEach((l) => (escolha[l] = t.dataset.todos)); cx.querySelectorAll(".seg[data-u] button").forEach((x) => x.classList.toggle("ativo", x.dataset.v === t.dataset.todos)); }
          });
        },
      });
    },
  };
  window.Aurora = { embutido, esc, api, tema, permissoes, iniciais, ICONES, svg, orbe, atomo, ATOMO_SVG, fundo, modal, modalAberto, confirmar, toast, som, notificar, avisarHub, Grade };
})();
