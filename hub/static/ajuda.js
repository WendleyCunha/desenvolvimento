/* ajuda.js — PEDIDOS DE AJUDA em balão de chat, no topo do hub (como o Agente)
 *
 * Quando alguém pede ajuda ao MEU setor (botão "Pedir ajuda" no Atendimento), abre na hora um balão
 * de chat: dá para responder ali mesmo, conversar e encerrar. Quem pediu recebe as respostas no mesmo balão.
 * Cada setor vê só o que pediram a ele e o que ele pediu (regra no servidor: tickets.py › /api/tickets/ajuda).
 * A lista completa fica no Atendimento › aba "Pedidos de ajuda".
 * 💬 Conversar com a equipe: chat direto com um colega online, SEM cliente (servidor: /api/tickets/conversa).
 * Visual: kit Aurora Glass do hub (variáveis --txt, --vidro, --violeta… e o tema claro de claro.css).
 */
(function () {
  'use strict';
  if (window.AjudaHub) return;

  const CSS = `
.aj-btn{position:relative;height:38px;width:38px;display:flex;align-items:center;justify-content:center;padding:0;border-radius:12px;cursor:pointer;
  font-size:17px;color:var(--txt);border:1px solid var(--vidro-borda);background:rgba(255,255,255,.03);transition:transform .3s var(--mola),box-shadow .3s}
.aj-btn:hover{transform:translateY(-1px);box-shadow:0 0 22px -6px rgba(139,92,246,.8)}
.aj-btn.aberto{box-shadow:0 0 0 3px rgba(139,92,246,.28)}
.aj-btn.tem{animation:ajPulso 1.6s ease-in-out infinite}
@keyframes ajPulso{0%,100%{box-shadow:0 0 0 0 rgba(139,92,246,.55)}50%{box-shadow:0 0 0 7px rgba(139,92,246,0)}}
.aj-n{position:absolute;top:-6px;right:-6px;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:var(--violeta,#8b5cf6);color:#fff;
  font:700 10.5px var(--sans,Inter),sans-serif;display:none;align-items:center;justify-content:center;z-index:2}
.aj-pop{position:fixed;z-index:9001;right:14px;width:420px;max-width:calc(100vw - 20px);border-radius:var(--raio,22px);overflow:hidden;display:flex;flex-direction:column;
  color:var(--txt);font:14px var(--sans,Inter),sans-serif;
  background:linear-gradient(160deg,rgba(255,255,255,calc(var(--vidro-a,.075) + .03)),rgba(255,255,255,var(--vidro-b,.02))),color-mix(in srgb,var(--noite2) 86%,transparent);
  backdrop-filter:var(--blur,saturate(160%) blur(22px));-webkit-backdrop-filter:var(--blur,saturate(160%) blur(22px));
  border:1px solid var(--vidro-borda-forte,rgba(255,255,255,.16));box-shadow:0 40px 90px -30px rgba(0,0,0,.75),0 0 0 1px rgba(139,92,246,.22);
  transform-origin:top right;transform:scale(.92) translateY(-8px);opacity:0;pointer-events:none;transition:transform .35s var(--mola),opacity .2s}
.aj-pop.aberto{transform:none;opacity:1;pointer-events:auto}
.aj-cab{display:flex;align-items:center;gap:10px;padding:12px 12px 10px;border-bottom:1px solid var(--vidro-borda)}
.aj-av{width:36px;height:36px;border-radius:12px;display:grid;place-items:center;flex:none;font-size:18px;background:linear-gradient(135deg,#8b5cf6,#60a5fa);box-shadow:0 0 18px rgba(139,92,246,.55)}
.aj-cab .t{flex:1;min-width:0}.aj-cab b{display:block;font:700 15px var(--titulo)}.aj-cab small{font-size:11.5px;color:var(--txt2)}
.aj-ib{width:32px;height:32px;border-radius:10px;border:1px solid var(--vidro-borda);background:rgba(255,255,255,.04);color:var(--txt);cursor:pointer;flex:none}
.aj-ib:hover{border-color:var(--violeta,#8b5cf6)}
.aj-corpo{flex:1;min-height:0;overflow:auto;padding:10px 12px;display:flex;flex-direction:column;gap:8px}
.aj-it{display:block;width:100%;text-align:left;border:1px solid var(--vidro-borda);border-left:3px solid var(--c);border-radius:12px;padding:9px 10px;background:rgba(255,255,255,.03);color:var(--txt);cursor:pointer;font:inherit}
.aj-it:hover{background:rgba(255,255,255,.07)}
.aj-it .l1{display:flex;gap:6px;align-items:center;font-size:12.5px}.aj-it .l1 b{font-size:13px}
.aj-it .l2{display:block;font-size:12px;color:var(--txt2);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.aj-it.novo{box-shadow:0 0 0 1px rgba(139,92,246,.6),0 0 18px -6px rgba(139,92,246,.9)}
.aj-tag{font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:20px;background:color-mix(in srgb,var(--c) 22%,transparent);color:var(--c);margin-left:auto;white-space:nowrap}
.aj-sec{font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--txt3,var(--txt2));font-weight:700;margin-top:4px}
.aj-ctx{font-size:12px;color:var(--txt2);padding:8px 12px;border-bottom:1px solid var(--vidro-borda)}
.aj-m{max-width:84%;padding:8px 11px;border-radius:14px;font-size:13.5px;line-height:1.45;white-space:pre-wrap;word-break:break-word;background:rgba(139,92,246,.16);border:1px solid rgba(139,92,246,.3);align-self:flex-start}
.aj-m.eu{align-self:flex-end;background:rgba(96,165,250,.16);border-color:rgba(96,165,250,.35)}
.aj-m .q{display:block;font-size:10.5px;color:var(--txt2);margin-bottom:3px}
.aj-m.fim{border-color:rgba(52,211,153,.5);background:rgba(52,211,153,.14)}
.aj-pe{border-top:1px solid var(--vidro-borda);padding:10px 12px;display:flex;flex-direction:column;gap:7px}
.aj-pe textarea{width:100%;min-height:58px;max-height:160px;resize:vertical;border-radius:12px;border:1px solid var(--vidro-borda);background:rgba(0,0,0,.18);color:var(--txt);padding:8px 10px;font:inherit}
html[data-claro] .aj-pe textarea{background:rgba(255,255,255,.7)}
.aj-bts{display:flex;gap:6px;flex-wrap:wrap}
.aj-b{border:1px solid var(--vidro-borda);border-radius:10px;padding:7px 11px;background:rgba(255,255,255,.05);color:var(--txt);cursor:pointer;font:600 12.5px var(--sans,Inter),sans-serif}
.aj-b.p{background:linear-gradient(135deg,#8b5cf6,#6d5df6);border-color:transparent;color:#fff}
.aj-b.ok{border-color:rgba(52,211,153,.6);color:var(--verde,#34d399)}
.aj-b:disabled{opacity:.5;cursor:wait}
.aj-vazio{text-align:center;color:var(--txt2);font-size:13px;padding:26px 10px}
.aj-pes{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:1px solid var(--vidro-borda);border-radius:12px;padding:8px 10px;background:rgba(255,255,255,.03);color:var(--txt);cursor:pointer;font:inherit}
.aj-pes:hover{background:rgba(255,255,255,.07);border-color:var(--violeta,#8b5cf6)}
.aj-pes .ini{position:relative;width:32px;height:32px;border-radius:11px;display:grid;place-items:center;flex:none;font:700 12px var(--titulo);background:linear-gradient(135deg,rgba(139,92,246,.35),rgba(96,165,250,.3))}
.aj-pes .ini i{position:absolute;right:-3px;bottom:-3px;width:10px;height:10px;border-radius:50%;background:#6b7183;border:2px solid var(--noite2)}.aj-pes .ini i.on{background:var(--verde,#34d399);box-shadow:0 0 8px var(--verde,#34d399)}
.aj-pes .tx{flex:1;min-width:0}.aj-pes .tx b{display:block;font-size:13px}.aj-pes .tx small{display:block;font-size:11.5px;color:var(--txt2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.aj-pes.novo{box-shadow:0 0 0 1px rgba(139,92,246,.6),0 0 18px -6px rgba(139,92,246,.9)}
.aj-ib.dm{width:auto;padding:0 10px;font:600 12px var(--sans,Inter),sans-serif;display:flex;align-items:center;gap:5px}
.aj-toast{position:fixed;z-index:9002;right:18px;bottom:18px;padding:9px 14px;border-radius:12px;background:var(--noite2);border:1px solid var(--vidro-borda);color:var(--txt);font-size:13px;opacity:0;transform:translateY(8px);transition:.25s;pointer-events:none}
.aj-toast.on{opacity:1;transform:none}`;

  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const dh = s => { s = String(s || ''); return s.length >= 16 ? `${s.slice(8, 10)}/${s.slice(5, 7)} ${s.slice(11, 16)}` : ''; };
  const CHAVE = 'wd.ajuda.visto';
  const lerVisto = () => { try { return JSON.parse(localStorage.getItem(CHAVE) || '{}') || {}; } catch (_) { return {}; } };
  const gravarVisto = v => { try { localStorage.setItem(CHAVE, JSON.stringify(v)); } catch (_) {} };

  let BTN = null, POP = null, TOAST = null, D = null, SEL = null, primeira = true, desligado = false, ocupado = false;
  const DMS = {};   // conversas diretas já abertas: usuario → {mensagens, ultima_em}
  const ini = n => esc(String(n || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase());
  const dmNaoLida = c => c.ultimo_de !== D.eu.usuario && String(c.ultima_em || '') > String(lerVisto()['dm:' + c.com] || '');

  async function api(url, corpo) {
    const op = { method: corpo ? 'POST' : 'GET', headers: { Accept: 'application/json' }, cache: 'no-store', credentials: 'same-origin' };
    if (corpo) { op.headers['Content-Type'] = 'application/json'; op.body = JSON.stringify(corpo); }
    const r = await fetch('/api/tickets' + url, op);
    let j = null; try { j = await r.json(); } catch (_) {}
    if (!r.ok) { const e = new Error((j && j.detail) || ('Erro ' + r.status)); e.status = r.status; throw e; }
    return j;
  }
  function toast(m) { TOAST.textContent = m; TOAST.classList.add('on'); clearTimeout(TOAST._t); TOAST._t = setTimeout(() => TOAST.classList.remove('on'), 2600); }

  /* não lido = a última fala é de outra pessoa e chegou depois da última vez que eu abri */
  const naoLido = v => v.status === 'aberto' && v.ultimo_de !== D.eu.usuario && String(v.ultima_em || '') > String(lerVisto()[v.id] || '');
  function marcarVisto(v) { const vs = lerVisto(); vs[v.id] = v.ultima_em; gravarVisto(vs); }

  function montar() {
    if (BTN) return;
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    BTN = document.createElement('button');
    BTN.type = 'button'; BTN.className = 'aj-btn'; BTN.title = 'Pedidos de ajuda do seu setor';
    BTN.innerHTML = '🤝<span class="aj-n">0</span>';
    const dir = document.querySelector('.topo .topo-acoes'), antes = document.getElementById('btnConfig');
    if (dir) dir.insertBefore(BTN, antes && antes.parentNode === dir ? antes : dir.firstChild);
    BTN.addEventListener('click', () => (POP.classList.contains('aberto') ? fechar() : abrir()));
    POP = document.createElement('section');
    POP.className = 'aj-pop'; POP.setAttribute('role', 'dialog'); POP.setAttribute('aria-label', 'Pedidos de ajuda');
    document.body.appendChild(POP);
    TOAST = document.createElement('div'); TOAST.className = 'aj-toast'; document.body.appendChild(TOAST);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && POP.classList.contains('aberto')) fechar(); });
    addEventListener('resize', posicionar);
  }
  function posicionar() {
    const nav = document.querySelector('.topo'), base = nav ? nav.getBoundingClientRect().bottom : 72;
    POP.style.top = (base + 8) + 'px';
    POP.style.height = `min(600px, calc(100vh - ${base + 20}px))`;
  }
  function abrir(v) { if (v !== undefined) SEL = v ? v.id : null; posicionar(); render(); POP.classList.add('aberto'); BTN.classList.add('aberto'); }
  function fechar() { POP.classList.remove('aberto'); BTN.classList.remove('aberto'); SEL = null; }

  function contador() {
    const n = D.pedidos.filter(v => naoLido(v) || (v.papel === 'recebido' && v.status === 'aberto' && !lerVisto()[v.id])).length
      + (D.conversas || []).filter(dmNaoLida).length;
    const el = BTN.querySelector('.aj-n'); el.textContent = n; el.style.display = n ? 'flex' : 'none';
    BTN.classList.toggle('tem', n > 0);
    BTN.title = n ? `Pedidos de ajuda — ${n} esperando você` : `Pedidos de ajuda${D.setor ? ' · ' + D.setor : ''}`;
  }

  function render() {
    if (!D) return;
    const v = SEL && D.pedidos.find(x => x.id === SEL);
    const cab = (t, s, voltar, extra = '') => `<div class="aj-cab">${voltar ? '<button type="button" class="aj-ib" data-voltar title="Voltar à lista">←</button>' : '<div class="aj-av">🤝</div>'}
      <div class="t"><b>${esc(t)}</b><small>${esc(s)}</small></div>${extra}<button type="button" class="aj-ib" data-fechar title="Fechar (Esc)">✕</button></div>`;
    const on = D.online || [], conv = D.conversas || [];
    const pessoa = (u, sub, novo) => `<button type="button" class="aj-pes${novo ? ' novo' : ''}" data-dm="${esc(u.usuario || u.com)}"><span class="ini">${ini(u.nome)}<i class="${u.online !== false ? 'on' : ''}"></i></span><span class="tx"><b>${esc(u.nome)}</b><small>${esc(sub)}</small></span>${novo ? '<span class="aj-tag" style="--c:var(--violeta,#8b5cf6)">novo</span>' : ''}</button>`;
    if (SEL === '@pessoas') {   // quem está online agora — meu setor primeiro
      const meu = D.eu.depto || '', ord = on.slice().sort((a, b) => (b.depto === meu) - (a.depto === meu));
      POP.innerHTML = cab('Conversar com a equipe', `${on.length} pessoa(s) online · sem vincular cliente`, true)
        + `<div class="aj-corpo">${ord.length ? `<div class="aj-sec">Online agora</div>${ord.map(u => pessoa(u, (u.depto || 'sem setor') + (u.depto && u.depto === meu ? ' · seu setor' : ''))).join('')}` : '<div class="aj-vazio">Ninguém mais online agora.</div>'}
          ${conv.filter(c => !c.online).length ? `<div class="aj-sec">Conversas recentes</div>${conv.filter(c => !c.online).slice(0, 8).map(c => pessoa(c, 'offline · ' + (c.texto || ''))).join('')}` : ''}</div>`;
    } else if (SEL && SEL.startsWith('dm:')) {   // chat direto com um colega
      const com = SEL.slice(3), info = on.find(x => x.usuario === com) || conv.find(x => x.com === com) || { nome: com }, dm = DMS[com] || { mensagens: [] }, eu = D.eu.usuario;
      const ligado = !!on.find(x => x.usuario === com);
      POP.innerHTML = cab(info.nome, `${info.depto || 'sem setor'} · ${ligado ? '● online' : 'offline — recebe quando abrir o hub'}`, true)
        + `<div class="aj-corpo" id="ajConv">${dm.mensagens.length ? dm.mensagens.map(m => `<div class="aj-m${m.de === eu ? ' eu' : ''}"><span class="q">${esc(m.nome || '')} · ${dh(m.em)}</span>${esc(m.texto)}</div>`).join('') : `<div class="aj-vazio">Comece a conversa com ${esc(String(info.nome).split(' ')[0])}. 👋<br><small>Conversa direta, sem cliente.</small></div>`}</div>
        <div class="aj-pe"><textarea id="ajTxt" placeholder="Mensagem para ${esc(String(info.nome).split(' ')[0])}… (Enter envia · Shift+Enter quebra a linha)"></textarea><div class="aj-bts"><button type="button" class="aj-b p" data-envdm>Enviar</button></div></div>`;
      const c = POP.querySelector('#ajConv'); c.scrollTop = c.scrollHeight;
      const ce = conv.find(x => x.com === com); if (ce) { const vs = lerVisto(); vs['dm:' + com] = ce.ultima_em; gravarVisto(vs); contador(); }
      const tx = POP.querySelector('#ajTxt');
      tx.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviarDM(com); } }); setTimeout(() => tx.focus(), 120);
      POP.querySelector('[data-envdm]').onclick = () => enviarDM(com);
    } else if (!v) {
      const ab = D.pedidos.filter(x => x.status === 'aberto'), rec = ab.filter(x => x.papel === 'recebido'), env = ab.filter(x => x.papel === 'enviado');
      const it = x => { const ult = x.conversa[x.conversa.length - 1], cor = x.papel === 'recebido' ? 'var(--violeta,#8b5cf6)' : 'var(--azul,#60a5fa)';
        return `<button type="button" class="aj-it${naoLido(x) ? ' novo' : ''}" data-v="${esc(x.id)}" style="--c:${cor}"><span class="l1"><b>${esc(x.setor_origem)} → ${esc(x.setor_destino)}</b><span class="aj-tag">${naoLido(x) ? 'novo' : dh(x.ultima_em)}</span></span>
          <span class="l2">${esc(x.cliente_nome || '')} · ${esc(x.assunto || '')}</span><span class="l2">💬 ${esc(ult.nome || '')}: ${esc(ult.texto || '')}</span></button>`; };
      const dmBt = `<button type="button" class="aj-ib dm" data-pessoas title="Conversar com quem está online — sem vincular cliente">💬 <span>${on.length}</span></button>`;
      POP.innerHTML = cab('Pedidos de ajuda', D.setor ? `setor ${D.setor} · ${rec.length} para você · ${env.length} pedidos por vocês` : 'seu usuário está sem setor no Atendimento', false, dmBt)
        + `<div class="aj-corpo">${conv.length ? `<div class="aj-sec">Conversas com a equipe</div>${conv.slice(0, 5).map(c => pessoa(c, (dmNaoLida(c) ? '' : (c.ultimo_de === D.eu.usuario ? 'você: ' : '')) + (c.texto || ''), dmNaoLida(c))).join('')}` : ''}${rec.length ? `<div class="aj-sec">Pediram ao seu setor</div>${rec.map(it).join('')}` : ''}${env.length ? `<div class="aj-sec">Seu setor pediu</div>${env.map(it).join('')}` : ''}
          ${!ab.length ? `<div class="aj-vazio">Nenhum pedido de ajuda aberto agora. 🎉${on.length ? `<br><small>${on.length} colega(s) online — toque em 💬 para conversar.</small>` : ''}</div>` : ''}</div>
          <div class="aj-pe"><div class="aj-bts"><button type="button" class="aj-b" data-todos>Ver todos no Atendimento ↗</button></div></div>`;
    } else {
      const eu = D.eu.usuario, aberto = v.status === 'aberto';
      POP.innerHTML = cab(`${v.setor_origem} → ${v.setor_destino}`, `${v.cliente_nome || ''} · ${v.cliente_codigo || ''}`, true)
        + `<div class="aj-ctx">${esc(v.assunto || 'Atendimento')} · pedido por <b>${esc(v.solicitado_por_nome || '')}</b> em ${dh(v.solicitado_em)}</div>
        <div class="aj-corpo" id="ajConv">${v.conversa.map(m => `<div class="aj-m${m.de === eu ? ' eu' : ''}${m.encerrou ? ' fim' : ''}"><span class="q"><b>${esc(m.setor || '—')}</b> · ${esc(m.nome || '')} · ${dh(m.em)}${m.encerrou ? ' · ✅ encerrou' : ''}</span>${esc(m.texto)}</div>`).join('')}</div>
        <div class="aj-pe">${aberto ? `<textarea id="ajTxt" placeholder="Escreva no chat… (Enter envia · Shift+Enter quebra a linha)"></textarea>` : '<div class="aj-vazio" style="padding:4px">✅ Pedido encerrado.</div>'}
          <div class="aj-bts">${aberto ? '<button type="button" class="aj-b p" data-env>Enviar</button><button type="button" class="aj-b ok" data-fim title="Manda a resposta final e encerra o pedido">Responder e encerrar</button>' : ''}<button type="button" class="aj-b" data-at style="margin-left:auto">Abrir o atendimento ↗</button></div></div>`;
      const c = POP.querySelector('#ajConv'); c.scrollTop = c.scrollHeight;
      marcarVisto(v); contador();
      const tx = POP.querySelector('#ajTxt');
      if (tx) { tx.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(v, false); } }); setTimeout(() => tx.focus(), 120); }
      const b1 = POP.querySelector('[data-env]'), b2 = POP.querySelector('[data-fim]');
      if (b1) b1.onclick = () => enviar(v, false);
      if (b2) b2.onclick = () => enviar(v, true);
      POP.querySelector('[data-at]').onclick = () => irPara('t=' + encodeURIComponent(v.tid));
    }
    POP.querySelector('[data-fechar]').onclick = fechar;
    const vt = POP.querySelector('[data-voltar]'); if (vt) vt.onclick = () => { SEL = null; render(); };
    const td = POP.querySelector('[data-todos]'); if (td) td.onclick = () => irPara('ajuda');
    POP.querySelectorAll('[data-v]').forEach(b => (b.onclick = () => { SEL = b.dataset.v; render(); }));
    POP.querySelectorAll('[data-dm]').forEach(b => (b.onclick = () => abrirDM(b.dataset.dm)));
    const pp = POP.querySelector('[data-pessoas]'); if (pp) pp.onclick = () => { SEL = '@pessoas'; render(); };
  }
  async function carregarDM(com) {
    try { const r = await api('/conversa/' + encodeURIComponent(com)); DMS[com] = { mensagens: r.mensagens, ultima_em: (r.mensagens[r.mensagens.length - 1] || {}).em }; } catch (e) { toast('⚠ ' + e.message); }
  }
  async function abrirDM(com) { SEL = 'dm:' + com; if (!DMS[com]) { DMS[com] = { mensagens: [] }; abrir(); } await carregarDM(com); abrir(); }
  async function enviarDM(com) {
    const tx = POP.querySelector('#ajTxt'), texto = tx ? tx.value.trim() : '';
    if (!texto) { toast('Escreva a mensagem.'); return; }
    if (ocupado) return; ocupado = true;
    try { const r = await api('/conversa', { para: com, texto }); (DMS[com] = DMS[com] || { mensagens: [] }).mensagens.push(r.mensagem); DMS[com].ultima_em = r.mensagem.em; tx.value = '';
      await atualizar(); render(); }
    catch (e) { toast('⚠ ' + e.message); }
    finally { ocupado = false; }
  }
  /* abre o Atendimento (aba do hub) já no lugar certo */
  function irPara(hash) { try { window.postMessage({ hub: 'abrir', id: 'tickets', hash }, location.origin); } catch (_) {} fechar(); }

  async function enviar(v, encerrar) {
    const tx = POP.querySelector('#ajTxt'), texto = tx ? tx.value.trim() : '';
    if (!texto) { toast(encerrar ? 'Escreva a resposta final antes de encerrar.' : 'Escreva a mensagem.'); return; }
    if (ocupado) return; ocupado = true;
    POP.querySelectorAll('.aj-b').forEach(b => (b.disabled = true));
    try { await api('/ajuda/mensagem', { tid: v.tid, pid: v.id, texto, encerrar }); toast(encerrar ? 'Pedido de ajuda encerrado.' : 'Enviado.'); await atualizar(); if (encerrar) SEL = null; render(); }
    catch (e) { toast('⚠ ' + e.message); POP.querySelectorAll('.aj-b').forEach(b => (b.disabled = false)); }
    finally { ocupado = false; }
  }

  async function atualizar() {
    let r;
    try { r = await api('/ajuda'); }
    catch (e) { if ([401, 403, 404, 503].includes(e.status) && primeira) { desligado = true; if (BTN) BTN.remove(); } return; }
    montar();
    const antes = D, vistoAntes = lerVisto();
    D = r;
    if (primeira) {   // na primeira carga não abre balão de coisa antiga
      primeira = false; contador(); return;
    }
    // chegou algo para mim (pedido novo ao meu setor, ou resposta numa conversa minha) → abre o balão na hora
    const ids = new Set((antes ? antes.pedidos : []).map(x => x.id + '|' + x.ultima_em));
    const chegou = D.pedidos.filter(x => x.status === 'aberto' && x.ultimo_de !== D.eu.usuario && !ids.has(x.id + '|' + x.ultima_em)
      && String(x.ultima_em || '') > String(vistoAntes[x.id] || ''));
    contador();
    const digitando = POP.classList.contains('aberto') && POP.querySelector('#ajTxt') && POP.querySelector('#ajTxt').value.trim();
    const convAntes = new Map(((antes && antes.conversas) || []).map(c => [c.com, c.ultima_em]));
    const dmNova = (D.conversas || []).filter(c => c.ultimo_de !== D.eu.usuario && convAntes.get(c.com) !== c.ultima_em && dmNaoLida(c));
    for (const c of dmNova) if (DMS[c.com]) await carregarDM(c.com);   // conversa aberta: traz as mensagens novas
    if (dmNova.length && !digitando) {
      const alvo = dmNova[0];
      if (!POP.classList.contains('aberto') || SEL === 'dm:' + alvo.com || !SEL || SEL === '@pessoas') { await abrirDM(alvo.com); }
      else render();
      try { const a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator(), g = a.createGain(); o.frequency.value = 660; g.gain.value = .05; o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + .15); } catch (_) {}
      return;
    }
    if (chegou.length && !digitando) {
      const alvo = chegou.sort((a, b) => String(b.ultima_em).localeCompare(String(a.ultima_em)))[0];
      if (!POP.classList.contains('aberto') || SEL === alvo.id || !SEL) abrir(alvo);
      try { const a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator(), g = a.createGain(); o.frequency.value = 880; g.gain.value = .05; o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + .15); } catch (_) {}
    } else if (POP.classList.contains('aberto') && !digitando) render();
  }

  function ciclo() {
    if (desligado) return;
    atualizar().finally(() => setTimeout(ciclo, document.visibilityState === 'visible' ? 15000 : 60000));
  }
  window.AjudaHub = { atualizar, abrir: () => abrir(null) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ciclo); else ciclo();
})();
