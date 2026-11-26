/* hub/static/chatfmt.js — mensagens das conversas com EMOJI, *NEGRITO*, LINKS e ANEXOS
   Usado no CX (Caixa), no WROUTER (motorista e cliente), no app do cliente e no app do motorista.
   • ChatFmt.fmt(texto)            → HTML seguro: *negrito*, links clicáveis, quebras de linha
   • ChatFmt.anexos(lista, url)    → miniaturas/links dos anexos de uma mensagem (url(id) devolve o endereço)
   • ChatFmt.barra(textarea, opts) → barra 😊 · B · 📎 junto da caixa; .pegar() devolve os anexos e limpa
   Limites dos anexos: imagem ou PDF, até 650 KB cada (fotos são reduzidas aqui antes de enviar), até 3 por mensagem. */
(function () {
  const MAX = 650 * 1024, MAX_N = 3, TIPOS = ["image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"];
  const EMOJIS = "😀 😄 😊 🙂 😉 😍 🙏 👍 👎 👏 🙌 💪 👋 🤝 ✅ ❌ ⚠️ ❗ ❓ ⏰ ⏳ 📍 🏠 🚚 📦 🛏️ 🔑 📞 📱 💬 📝 📎 📄 📷 💳 💰 🎁 ⭐ 🔥 🎉 ❤️ 😅 😢 😡 🤔 👀 🙋".split(" ");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function fmt(texto) {
    let h = esc(texto);
    // links (http/https e www.) — abrem em outra aba, sem passar a página de origem
    h = h.replace(/(^|[\s(])((?:https?:\/\/|www\.)[^\s<]+[^\s<.,;:!?)\]])/gi, (m, pre, url) => {
      const href = /^www\./i.test(url) ? "https://" + url : url;
      return `${pre}<a href="${href}" target="_blank" rel="noopener noreferrer" data-cf-link>${url}</a>`;
    });
    // *negrito* (como no WhatsApp)
    h = h.replace(/(^|[\s>(])\*([^*\n<>]{1,300}?)\*(?=$|[\s<.,;:!?)])/g, "$1<b>$2</b>");
    return h;   // as caixas de conversa já usam white-space:pre-wrap (as quebras de linha aparecem sozinhas)
  }

  function kb(n) { return n >= 1024 * 1024 ? (n / 1048576).toFixed(1).replace(".", ",") + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }

  function anexos(lista, url) {
    if (!lista || !lista.length) return "";
    return `<span class="cf-anx">${lista.map((a) => {
      const u = esc(url(a.id));
      return a.tipo && a.tipo.startsWith("image/")
        ? `<a href="${u}" target="_blank" rel="noopener" class="cf-img" title="${esc(a.nome)}"><img src="${u}" alt="${esc(a.nome)}" loading="lazy"></a>`
        : `<a href="${u}" target="_blank" rel="noopener" class="cf-doc">📄 ${esc(a.nome)} <small>${a.tam ? kb(a.tam) : ""}</small></a>`;
    }).join("")}</span>`;
  }

  // ── reduz a foto antes de enviar (lado maior 1600 px, JPEG) ──
  function reduzir(arq) {
    return new Promise((ok, erro) => {
      const img = new Image(), u = URL.createObjectURL(arq);
      img.onload = () => {
        const k = Math.min(1, 1600 / Math.max(img.width, img.height)), c = document.createElement("canvas");
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        const x = c.getContext("2d"); x.fillStyle = "#fff"; x.fillRect(0, 0, c.width, c.height); x.drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(u);
        let q = 0.82, d = c.toDataURL("image/jpeg", q);
        while (d.length * 0.75 > MAX && q > 0.4) { q -= 0.12; d = c.toDataURL("image/jpeg", q); }
        ok({ nome: arq.name.replace(/\.[^.]+$/, "") + ".jpg", tipo: "image/jpeg", dados: d, tam: Math.round(d.length * 0.75) });
      };
      img.onerror = () => { URL.revokeObjectURL(u); erro(new Error("Não consegui abrir esta imagem.")); };
      img.src = u;
    });
  }
  function lerArq(arq) {
    return new Promise((ok, erro) => { const r = new FileReader(); r.onload = () => ok({ nome: arq.name, tipo: arq.type, dados: r.result, tam: arq.size }); r.onerror = () => erro(new Error("Não consegui ler o arquivo.")); r.readAsDataURL(arq); });
  }

  let css = false;
  function estilo() {
    if (css) return; css = true;
    const s = document.createElement("style");
    s.textContent = `.cf-barra{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin:4px 0;position:relative}
.cf-barra .cf-b{border:1px solid rgba(127,127,127,.3);background:rgba(127,127,127,.08);color:inherit;border-radius:8px;padding:3px 8px;font:inherit;font-size:.82rem;cursor:pointer;line-height:1.4}
.cf-barra .cf-b:hover{background:rgba(127,127,127,.18)}
.cf-barra .cf-dica{font-size:.68rem;opacity:.6;margin-left:4px}
.cf-emo{position:absolute;bottom:calc(100% + 6px);left:0;z-index:50;display:grid;grid-template-columns:repeat(10,1fr);gap:2px;padding:8px;border-radius:12px;background:#111827;border:1px solid rgba(255,255,255,.15);box-shadow:0 12px 30px rgba(0,0,0,.4);width:300px}
html[data-claro] .cf-emo{background:#fff;border-color:rgba(0,0,0,.15)}
.cf-emo button{border:0;background:transparent;font-size:1.15rem;cursor:pointer;border-radius:6px;padding:2px}
.cf-emo button:hover{background:rgba(127,127,127,.2)}
.cf-pend{display:flex;gap:6px;flex-wrap:wrap;width:100%}
.cf-pend span{display:inline-flex;align-items:center;gap:4px;font-size:.75rem;border:1px dashed rgba(127,127,127,.5);border-radius:8px;padding:2px 6px}
.cf-pend img{width:28px;height:28px;object-fit:cover;border-radius:4px}
.cf-pend b{cursor:pointer;opacity:.7}
a[data-cf-link]{color:inherit!important;text-decoration:underline;font-weight:600;word-break:break-all}
.cf-anx{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.cf-anx .cf-img img{width:120px;max-height:120px;object-fit:cover;border-radius:8px;display:block}
.cf-anx .cf-doc{display:inline-flex;gap:4px;align-items:center;padding:4px 8px;border-radius:8px;background:rgba(127,127,127,.15);color:inherit;text-decoration:none;font-size:.82rem}
.cf-anx .cf-doc small{opacity:.7}`;
    document.head.appendChild(s);
  }

  const PEND = {};   // anexos escolhidos e ainda não enviados, por caixa de texto (sobrevivem ao redesenho da tela)
  function barra(ta, opts = {}) {
    if (!ta) return { pegar: () => [], limpar: () => {}, tem: () => false };
    estilo();
    const chave = opts.chave || ta.id || "txt";
    PEND[chave] = PEND[chave] || [];
    const ancora = opts.junto || ta;   // a barra vai logo depois deste elemento (ex.: a linha campo + botão Enviar)
    let b = ancora.parentElement.querySelector(`.cf-barra[data-cf="${chave}"]`);
    if (!b) {
      b = document.createElement("div"); b.className = "cf-barra"; b.dataset.cf = chave;
      b.innerHTML = `<button type="button" class="cf-b" data-cf-emo title="Emoji">😊</button><button type="button" class="cf-b" data-cf-neg title="Negrito (*texto*)"><b>B</b></button>${opts.anexo === false ? "" : `<button type="button" class="cf-b" data-cf-anx title="Anexar imagem ou PDF (até 650 KB, máx. 3)">📎</button><input type="file" hidden multiple accept="image/*,application/pdf">`}<span class="cf-dica">*negrito* · links ficam clicáveis</span><div class="cf-pend"></div>`;
      ancora.insertAdjacentElement(opts.antes ? "beforebegin" : "afterend", b);
    }
    const pend = b.querySelector(".cf-pend");
    const desenhar = () => { pend.innerHTML = PEND[chave].map((a, i) => `<span>${a.tipo.startsWith("image/") ? `<img src="${a.dados}" alt="">` : "📄"}${esc(a.nome)} <small>${kb(a.tam)}</small><b data-cf-x="${i}" title="Tirar">×</b></span>`).join(""); };
    desenhar();
    const inserir = (t) => { const i = ta.selectionStart ?? ta.value.length, f = ta.selectionEnd ?? i; ta.value = ta.value.slice(0, i) + t + ta.value.slice(f); ta.focus(); ta.selectionStart = ta.selectionEnd = i + t.length; ta.dispatchEvent(new Event("input", { bubbles: true })); };
    b.querySelector("[data-cf-neg]").onclick = () => {
      const i = ta.selectionStart ?? 0, f = ta.selectionEnd ?? 0, sel = ta.value.slice(i, f) || "texto";
      ta.value = ta.value.slice(0, i) + `*${sel}*` + ta.value.slice(f); ta.focus(); ta.selectionStart = i + 1; ta.selectionEnd = i + 1 + sel.length;
    };
    b.querySelector("[data-cf-emo]").onclick = (ev) => {
      ev.stopPropagation();
      const ja = b.querySelector(".cf-emo"); if (ja) { ja.remove(); return; }
      const p = document.createElement("div"); p.className = "cf-emo";
      p.innerHTML = EMOJIS.map((e) => `<button type="button">${e}</button>`).join("");
      p.onclick = (e) => { const x = e.target.closest("button"); if (x) { inserir(x.textContent); p.remove(); } };
      b.appendChild(p);
      setTimeout(() => document.addEventListener("click", function f(e) { if (!p.contains(e.target)) { p.remove(); document.removeEventListener("click", f); } }), 0);
    };
    const fi = b.querySelector("input[type=file]"), ba = b.querySelector("[data-cf-anx]");
    if (ba && fi) {
      ba.onclick = () => fi.click();
      fi.onchange = async () => {
        for (const arq of [...fi.files]) {
          if (PEND[chave].length >= MAX_N) { aviso(`No máximo ${MAX_N} anexos por mensagem.`); break; }
          if (!TIPOS.includes(arq.type) && !arq.type.startsWith("image/")) { aviso("Envie imagem (JPG, PNG, WEBP, GIF) ou PDF."); continue; }
          try {
            const a = arq.type.startsWith("image/") && arq.type !== "image/gif" ? await reduzir(arq) : await lerArq(arq);
            if (a.tam > MAX) { aviso(`"${arq.name}" passa de 650 KB. Envie um arquivo menor.`); continue; }
            PEND[chave].push(a);
          } catch (e) { aviso(e.message); }
        }
        fi.value = ""; desenhar(); ta.focus();
      };
      pend.onclick = (e) => { const x = e.target.closest("[data-cf-x]"); if (x) { PEND[chave].splice(+x.dataset.cfX, 1); desenhar(); } };
    }
    function aviso(t) { if (window.Aurora && Aurora.toast) Aurora.toast(t, [], { cor: "var(--rosa)" }); else alert(t); }
    return {
      tem: () => PEND[chave].length > 0,
      pegar: () => PEND[chave].map((a) => ({ nome: a.nome, tipo: a.tipo, dados: a.dados })),
      limpar: () => { PEND[chave] = []; desenhar(); },
    };
  }

  window.ChatFmt = { fmt, anexos, barra, esc, MAX, MAX_N };
})();
