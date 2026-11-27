/* presenca.js — STATUS DO ATENDENTE na barra do hub (ao lado dos Pedidos de ajuda)
 *
 * Ao abrir o hub, a pessoa entra ONLINE. Clicando no botão: Online · pausas (Pausa, Almoço, Banheiro,
 * Reunião… cadastradas no CX › Ajustes › Setor e perfil) · Offline. Diferente de Online = não recebe
 * atendimento. O botão avisa o servidor a cada minuto (o "sinal"); sem sinal por 5 min → Offline sozinho.
 * Só aparece para quem usa o CX (servidor: /api/tickets/presenca).
 */
(function () {
  'use strict';
  if (window.PresencaHub) return;
  const CSS = `
.pr-btn{position:relative;height:38px;display:flex;align-items:center;gap:7px;padding:0 12px 0 10px;border-radius:12px;cursor:pointer;
  font:600 12.5px var(--sans,Inter),sans-serif;color:var(--txt);border:1px solid var(--vidro-borda);background:rgba(255,255,255,.03);white-space:nowrap;
  transition:transform .3s var(--mola),box-shadow .3s}
.pr-btn:hover{transform:translateY(-1px);box-shadow:0 0 22px -6px var(--pr-c)}
.pr-btn i{width:9px;height:9px;border-radius:50%;background:var(--pr-c);box-shadow:0 0 8px var(--pr-c);flex:none}
.pr-btn small{font-weight:500;color:var(--txt3);font-size:11px}
.pr-pop{position:fixed;z-index:9002;width:240px;border-radius:16px;padding:6px;display:flex;flex-direction:column;gap:2px;
  background:linear-gradient(160deg,rgba(255,255,255,calc(var(--vidro-a,.075) + .03)),rgba(255,255,255,var(--vidro-b,.02))),color-mix(in srgb,var(--noite2) 90%,transparent);
  backdrop-filter:var(--blur,saturate(160%) blur(22px));-webkit-backdrop-filter:var(--blur,saturate(160%) blur(22px));
  border:1px solid var(--vidro-borda-forte,rgba(255,255,255,.16));box-shadow:0 30px 70px -24px rgba(0,0,0,.75);
  transform:scale(.94) translateY(-6px);transform-origin:top right;opacity:0;pointer-events:none;transition:transform .3s var(--mola),opacity .18s}
.pr-pop.aberto{transform:none;opacity:1;pointer-events:auto}
.pr-pop h5{margin:6px 8px 4px;font:700 10px var(--sans,Inter),sans-serif;letter-spacing:1.4px;text-transform:uppercase;color:var(--txt3)}
.pr-op{display:flex;align-items:center;gap:10px;width:100%;text-align:left;padding:9px 10px;border-radius:11px;border:0;background:transparent;color:var(--txt);
  font:500 13.5px var(--sans,Inter),sans-serif;cursor:pointer}
.pr-op:hover{background:rgba(255,255,255,.07)}
.pr-op .e{width:22px;text-align:center;font-size:15px}
.pr-op.on{background:color-mix(in srgb,var(--pr-c) 16%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--pr-c) 45%,transparent)}
.pr-op .ck{margin-left:auto;color:var(--pr-c);font-weight:800}
.pr-sep{height:1px;background:var(--vidro-borda);margin:4px 6px}`;
  const COR = { online: '#34d399', offline: '#6b7183' }, PAUSA = '#f59e0b';
  let BTN, POP, D = null, ativo = false;
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cor = (st) => COR[st] || PAUSA;
  const rotulo = (st) => st === 'online' ? 'Online' : st === 'offline' ? 'Offline' : ((D.pausas || []).find((x) => x.id === st) || {}).rotulo || 'Pausa';
  const emoji = (st) => st === 'online' ? '🟢' : st === 'offline' ? '⚫' : ((D.pausas || []).find((x) => x.id === st) || {}).emoji || '⏸';
  const desde = () => { if (!D.desde) return ''; const m = Math.max(0, Math.floor((Date.now() / 1000 - D.desde) / 60)); return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}`; };

  async function api(metodo, corpo, inicio) {
    const r = await fetch('/api/tickets/presenca' + (inicio ? '?inicio=1' : ''), { method: metodo, credentials: 'same-origin', cache: 'no-store',
      headers: corpo ? { 'Content-Type': 'application/json' } : {}, body: corpo ? JSON.stringify(corpo) : undefined });
    if (!r.ok) { const e = new Error('HTTP ' + r.status); e.status = r.status; throw e; }
    return r.json();
  }
  function montar() {
    if (BTN) return;
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    BTN = document.createElement('button'); BTN.type = 'button'; BTN.className = 'pr-btn';
    const dir = document.querySelector('.topo .topo-acoes'), antes = document.querySelector('.topo .aj-btn') || document.getElementById('btnConfig');
    if (!dir) return;
    dir.insertBefore(BTN, antes && antes.parentNode === dir ? antes : dir.firstChild);
    BTN.onclick = () => (POP.classList.contains('aberto') ? fechar() : abrir());
    POP = document.createElement('div'); POP.className = 'pr-pop'; POP.setAttribute('role', 'menu'); document.body.appendChild(POP);
    document.addEventListener('click', (e) => { if (POP.classList.contains('aberto') && !POP.contains(e.target) && !BTN.contains(e.target)) fechar(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
  }
  function desenhar() {
    if (!BTN || !D) return;
    BTN.style.setProperty('--pr-c', cor(D.status));
    BTN.innerHTML = `<i></i>${esc(rotulo(D.status))}${D.status !== 'online' && D.desde ? ` <small>${desde()}</small>` : ''}`;
    BTN.title = D.status === 'online' ? 'Online — recebendo atendimentos. Clique para pausar ou ficar offline.' : `${rotulo(D.status)} — não recebe atendimentos. Clique para mudar.`;
    const op = (id) => `<button type="button" class="pr-op${D.status === id ? ' on' : ''}" data-st="${esc(id)}" style="--pr-c:${cor(id)}"><span class="e">${emoji(id)}</span>${esc(rotulo(id))}${D.status === id ? '<span class="ck">✓</span>' : ''}</button>`;
    POP.innerHTML = `<h5>Meu status</h5>${op('online')}<div class="pr-sep"></div>${(D.pausas || []).map((x) => op(x.id)).join('')}<div class="pr-sep"></div>${op('offline')}`;
    POP.querySelectorAll('[data-st]').forEach((b) => (b.onclick = () => mudar(b.dataset.st)));
  }
  function abrir() { const r = BTN.getBoundingClientRect(); POP.style.top = (r.bottom + 8) + 'px'; POP.style.right = Math.max(10, innerWidth - r.right) + 'px'; POP.classList.add('aberto'); }
  function fechar() { if (POP) POP.classList.remove('aberto'); }
  async function mudar(st) {
    fechar();
    try { await api('POST', { status: st }); D.status = st; D.desde = Date.now() / 1000; desenhar(); } catch (_) { /* tenta no próximo sinal */ }
  }
  async function sinal(inicio) {
    try {
      D = await api('GET', null, inicio);
      if (!ativo) { ativo = true; montar(); }
      desenhar();
    } catch (e) {
      if ([401, 403, 404, 503].includes(e.status)) { pararTudo(); }   // sem CX para esta pessoa: o botão não aparece
    }
  }
  let timer = 0;
  function pararTudo() { clearInterval(timer); if (BTN) BTN.remove(); if (POP) POP.remove(); BTN = POP = null; ativo = false; }
  function iniciar() { sinal(true); timer = setInterval(() => sinal(false), 60000); setInterval(() => { if (D && D.status !== 'online') desenhar(); }, 30000); }
  window.PresencaHub = { atualizar: () => sinal(false) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
