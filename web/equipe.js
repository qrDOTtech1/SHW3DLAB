// MODE EQUIPE (facon Miro) : on voit la souris des autres et ce qu'ils font, en direct.
// Transport : relais MQTT public (WebSocket), messages CHIFFRES AES-256-GCM avec une cle derivee du CODE D'EQUIPE
// (jamais envoye : le relais ne voit que du bruit). Meme code sur chaque poste = meme equipe.
// - curseurs des coequipiers (quand ils sont sur le meme onglet) avec leur nom ;
// - mini-fenetre "Equipe" : qui est en ligne, ou, sur quel projet, derniere action, bouton "Suivre" ;
// - quand quelqu'un enregistre un projet, les autres lancent la synchro GitHub ~25 s plus tard.
(() => {
  const RELAIS = ['wss://broker.emqx.io:8084/mqtt', 'wss://broker.hivemq.com:8884/mqtt', 'wss://test.mosquitto.org:8081/mqtt'];
  const COULEURS = ['#ff6410', '#3ddc97', '#4aa3ff', '#f5c542', '#c77dff', '#ff5a8a'];
  const moi = { id: Math.random().toString(36).slice(2, 10), nom: '', couleur: '', onglet: '', projet: null, action: 'arrive', ts: 0 };
  const pairs = new Map();
  let client = null, cle = null, sujet = '', relais = 0, ok = false, dernierEnvoi = 0, souris = null;

  // ------------------------------------------------------------ crypto
  const enc = new TextEncoder(), dec = new TextDecoder();
  const hex = b => [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
  async function preparer(code) {
    const base = await crypto.subtle.importKey('raw', enc.encode(code), 'PBKDF2', false, ['deriveKey']);
    cle = await crypto.subtle.deriveKey({ name: 'PBKDF2', salt: enc.encode('shw3dlab-equipe'), iterations: 120000, hash: 'SHA-256' },
      base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
    sujet = 'shw3dlab/eq/' + hex(await crypto.subtle.digest('SHA-256', enc.encode('sujet:' + code))).slice(0, 32);
  }
  async function chiffrer(o) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const c = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, cle, enc.encode(JSON.stringify(o)));
    const out = new Uint8Array(12 + c.byteLength); out.set(iv); out.set(new Uint8Array(c), 12); return out;
  }
  async function dechiffrer(b) {
    try {
      const u = new Uint8Array(b);
      return JSON.parse(dec.decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: u.slice(0, 12) }, cle, u.slice(12))));
    } catch { return null; }                          // pas notre equipe / message altere : ignore
  }

  // ------------------------------------------------------------ transport
  function connecter() {
    if (!window.mqtt || !cle) return;
    try { client?.end(true); } catch { }
    client = window.mqtt.connect(RELAIS[relais % RELAIS.length], { clientId: 'shw_' + moi.id, keepalive: 30, reconnectPeriod: 4000, connectTimeout: 8000, clean: true });
    let echecs = 0;
    client.on('connect', () => { ok = true; echecs = 0; client.subscribe(sujet); envoyer({ t: 'p' }, true); rendre(); });
    client.on('close', () => { ok = false; rendre(); if (++echecs >= 3) { relais++; connecter(); } });
    client.on('message', async (_, b) => {
      const m = await dechiffrer(b);
      if (!m || m.id === moi.id) return;
      recevoir(m);
    });
  }
  async function envoyer(extra = {}, force = false) {
    if (!ok || !client) return;
    const t = performance.now();
    if (!force && extra.t === 'p' && t - dernierEnvoi < 70) return;
    dernierEnvoi = t;
    const m = { ...moi, souris, ...extra, ts: Date.now() };
    client.publish(sujet, await chiffrer(m), { qos: 0 });
  }

  // ------------------------------------------------------------ reception
  function recevoir(m) {
    if (m.t === 'bye') { pairs.delete(m.id); retirerCurseur(m.id); return rendre(); }
    const p = pairs.get(m.id) || { premier: Date.now() };
    const nouvelleAction = m.action && m.action !== p.action;
    Object.assign(p, m, { vu: Date.now() });
    if (nouvelleAction) p.actionTs = Date.now();
    pairs.set(m.id, p);
    if (m.t === 'save') {                              // un coequipier a enregistre : on recupere apres son envoi
      clearTimeout(recevoir._s);
      recevoir._s = setTimeout(() => document.getElementById('pj-synchro')?.click(), 25000);
    }
    dessinerCurseur(p);
    rendre();
  }

  // ------------------------------------------------------------ curseurs
  const calque = document.createElement('div');
  calque.id = 'eq-calque';
  function zone() { return document.querySelector('.tab.on') || document.body; }
  function dessinerCurseur(p) {
    let c = document.getElementById('eq-c-' + p.id);
    const visible = p.souris && p.onglet === moi.onglet;
    if (!visible) { if (c) c.style.display = 'none'; return; }
    if (!c) {
      c = document.createElement('div'); c.id = 'eq-c-' + p.id; c.className = 'eq-curseur';
      c.innerHTML = `<svg width="18" height="18" viewBox="0 0 18 18"><path d="M1 1 L1 15 L5 11 L8 17 L10.5 16 L7.6 10 L13 10 Z" stroke="#0d0f13" stroke-width="1.2"/></svg><span></span>`;
      calque.appendChild(c);
    }
    const r = zone().getBoundingClientRect();
    c.style.display = 'block';
    c.style.transform = `translate(${r.left + p.souris[0] * r.width}px, ${r.top + p.souris[1] * r.height}px)`;
    c.querySelector('path').setAttribute('fill', p.couleur);
    const s = c.querySelector('span'); s.textContent = p.nom + (p.action ? ' · ' + p.action : ''); s.style.background = p.couleur;
  }
  function retirerCurseur(id) { document.getElementById('eq-c-' + id)?.remove(); }

  // ------------------------------------------------------------ mini-fenetre
  const ONGLETS = { creer: 'Creer', c3d: 'Creation 3D', kc: 'Keycaps', sw: 'SHWork', pj: 'Projets', cfg: 'Projet', imprimer: 'Imprimer', filaments: 'Filaments', couts: 'Couts', imprimante: 'Imprimante' };
  const fen = document.createElement('div'); fen.id = 'eq-fen';
  function ilya(ts) { const s = Math.round((Date.now() - ts) / 1000); return s < 5 ? "a l'instant" : s < 60 ? `il y a ${s} s` : `il y a ${Math.round(s / 60)} min`; }
  function ligne(p, estMoi) {
    const ou = (ONGLETS[p.onglet] || p.onglet || '?') + (p.projet ? ` · ${p.projet.nom}` : '');
    return `<div class="eq-l"><i style="background:${p.couleur}"></i><div class="eq-t"><b>${p.nom}${estMoi ? ' (moi)' : ''}</b>
      <span>${ou}</span><em>${p.action || ''}${estMoi ? '' : ' · ' + ilya(p.actionTs || p.vu)}</em></div>
      ${estMoi ? '' : `<button data-suivre="${p.id}" title="Aller ou il est">Suivre</button>`}</div>`;
  }
  function rendre() {
    const repli = fen.classList.contains('repli');
    const n = pairs.size;
    fen.innerHTML = `<div class="eq-h"><span class="eq-pt" style="background:${ok ? '#3ddc97' : (cle ? '#f5c542' : '#8b919c')}"></span>
      <b>Equipe</b><span class="eq-n">${cle ? (ok ? (n ? `${n} en ligne` : 'seul pour l\'instant') : 'connexion...') : 'non configuree'}</span>
      <button data-r title="Reglages">&#9881;</button><button data-p title="Replier">${repli ? '&#9650;' : '&#9660;'}</button></div>
      <div class="eq-b">${cle ? [...pairs.values()].map(p => ligne(p, false)).join('') + ligne(moi, true)
        : `<p class="eq-v">Entre le meme <b>code d'equipe</b> sur chaque poste pour travailler ensemble.</p>`}</div>`;
  }
  fen.addEventListener('click', async e => {
    if (e.target.closest('[data-p]')) { fen.classList.toggle('repli'); return rendre(); }
    if (e.target.closest('[data-r]')) return reglages();
    const s = e.target.closest('[data-suivre]');
    if (s) {
      const p = pairs.get(s.dataset.suivre); if (!p) return;
      if (p.projet?.id && window.SHWOuvrirProjet) window.SHWOuvrirProjet(p.projet.id);
      else document.querySelector(`[data-tab="${p.onglet}"]`)?.click();
    }
  });
  async function reglages() {
    const nom = prompt('Ton nom (vu par l\'equipe) :', moi.nom); if (nom === null) return;
    const code = prompt('Code d\'equipe (le meme sur chaque poste) :', (await (await fetch('/api/equipe')).json()).code || ''); if (code === null) return;
    await fetch('/api/equipe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nom: nom.trim(), code: code.trim() }) });
    location.reload();
  }

  // ------------------------------------------------------------ ce que JE fais
  function action(txt) { moi.action = txt; moi.actionTs = Date.now(); envoyer({ t: 'p' }, true); rendre(); }
  function libelle(el) {
    const t = (el.getAttribute('title') && !el.textContent.trim() ? el.getAttribute('title') : el.textContent || el.value || '').replace(/\s+/g, ' ').trim();
    return t.length > 34 ? t.slice(0, 32) + '…' : t;
  }
  document.addEventListener('mousemove', e => {
    const r = zone().getBoundingClientRect();
    souris = [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
    envoyer({ t: 'p' });
  }, { passive: true });
  document.addEventListener('mouseleave', () => { souris = null; envoyer({ t: 'p' }, true); });
  document.addEventListener('click', e => {
    if (e.target.closest('#eq-fen')) return;
    const nav = e.target.closest('[data-tab]');
    if (nav) { moi.onglet = nav.dataset.tab; [...pairs.values()].forEach(dessinerCurseur); return action('dans ' + (ONGLETS[moi.onglet] || moi.onglet)); }
    const b = e.target.closest('button, [role=menuitem], .menu-item, li[data-a], .pj-carte, a');
    if (b) { const l = libelle(b); if (l) action(`clique « ${l} »`); }
  }, true);
  document.addEventListener('contextmenu', () => action('menu clic droit'), true);
  document.addEventListener('change', e => {
    const el = e.target; if (el.closest('#eq-fen')) return;
    const lab = el.closest('label')?.textContent || el.labels?.[0]?.textContent || el.previousElementSibling?.textContent || el.name || el.id || 'un reglage';
    action(`regle « ${lab.replace(/\s+/g, ' ').trim().slice(0, 30)} »`);
  }, true);
  window.addEventListener('shw:projet', e => { moi.projet = e.detail; action(`ouvre « ${e.detail.nom} »`); });
  // chargements (fenetre SHWCharge) : "Hugo fait : Generation du projet..."
  const attendreCharge = setInterval(() => {
    const C = window.SHWCharge; if (!C || C.__eq) return;
    const debut = C.debut.bind(C);
    C.debut = (titre, o) => { action(titre + '…'); const h = debut(titre, o); const fin = h.fin.bind(h); h.fin = () => { action('fini : ' + titre); fin(); }; return h; };
    C.__eq = true; clearInterval(attendreCharge);
  }, 300);
  // enregistrements de projet -> les autres synchronisent
  const fetch0 = window.fetch.bind(window);
  window.fetch = async (u, o = {}) => {
    const r = await fetch0(u, o);
    const url = typeof u === 'string' ? u : u?.url || '';
    if (/\/api\/projets(\/[^/]+(\/dupliquer)?)?$/.test(url) && /POST|DELETE/i.test(o.method || '') && r.ok) {
      action(/DELETE/i.test(o.method) ? 'met un projet a la corbeille' : 'enregistre un projet'); envoyer({ t: 'save' }, true);
    }
    return r;
  };
  setInterval(() => {                                  // presence + menage des absents
    envoyer({ t: 'p' }, true);
    for (const [id, p] of pairs) if (Date.now() - p.vu > 20000) { pairs.delete(id); retirerCurseur(id); }
    rendre();
  }, 5000);
  window.addEventListener('beforeunload', () => envoyer({ t: 'bye' }, true));

  // ------------------------------------------------------------ demarrage
  const css = document.createElement('style');
  css.textContent = `
#eq-calque{position:fixed;inset:0;pointer-events:none;z-index:9000}
.eq-curseur{position:absolute;left:0;top:0;transition:transform .09s linear;will-change:transform}
.eq-curseur span{position:absolute;left:14px;top:14px;white-space:nowrap;font:600 11px 'Segoe UI',sans-serif;color:#0d0f13;padding:2px 7px;border-radius:8px;max-width:320px;overflow:hidden;text-overflow:ellipsis}
#eq-fen{position:fixed;left:14px;bottom:14px;z-index:9001;width:290px;background:#0d0f13ee;border:1px solid #2a2e37;border-radius:12px;color:#e9ebef;
  font:12px 'Segoe UI',system-ui,sans-serif;box-shadow:0 10px 30px #0007;backdrop-filter:blur(4px)}
#eq-fen .eq-h{display:flex;align-items:center;gap:7px;padding:8px 10px}
#eq-fen .eq-h .eq-n{flex:1;color:#8b919c;font-size:11px}
#eq-fen .eq-h button{background:none;border:0;color:#8b919c;cursor:pointer;font-size:12px;padding:0 3px}
#eq-fen .eq-pt{width:8px;height:8px;border-radius:50%}
#eq-fen .eq-b{padding:0 10px 9px;display:grid;gap:7px;max-height:40vh;overflow:auto}
#eq-fen.repli .eq-b{display:none}
#eq-fen .eq-l{display:flex;gap:8px;align-items:center}
#eq-fen .eq-l i{width:10px;height:10px;border-radius:50%;flex:none}
#eq-fen .eq-t{flex:1;display:grid;line-height:1.3;min-width:0}
#eq-fen .eq-t span{color:#c9ced6;font-size:11px}
#eq-fen .eq-t em{color:#ff9a5c;font-size:11px;font-style:normal;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#eq-fen .eq-l button{background:#1d2027;border:1px solid #2a2e37;color:#e9ebef;border-radius:6px;font-size:11px;padding:3px 7px;cursor:pointer}
#eq-fen .eq-v{color:#8b919c;margin:0}`;
  document.head.appendChild(css);
  document.body.append(calque, fen);
  moi.onglet = document.querySelector('nav [data-tab].on, [data-tab].on')?.dataset.tab || 'creer';
  (async () => {
    const c = await (await fetch0('/api/equipe')).json();
    moi.nom = c.nom; moi.couleur = c.couleur || COULEURS[[...c.nom].reduce((a, x) => a + x.charCodeAt(0), 0) % COULEURS.length];
    if (c.code) { await preparer(c.code); connecter(); }
    rendre();
  })();
})();
