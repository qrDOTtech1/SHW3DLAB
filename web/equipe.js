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
    const mv = moduleVue();
    const vue = mv?.cam ? [mv.cam.position.toArray().map(x => +x.toFixed(1)), mv.orb.target.toArray().map(x => +x.toFixed(1))] : null;
    const m = { ...moi, souris, vue, ...extra, ts: Date.now() };
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
    if (m.t === 'etat') recevoirEtat(m);
    if (m.t === 'demande' && m.pid === moi.projet?.id && rev) envoyerEtat(true);
    if (suivi === m.id) suivre(p);
    if (m.t === 'save') {                              // un coequipier a enregistre : on recupere apres son envoi
      clearTimeout(recevoir._s);
      recevoir._s = setTimeout(() => document.getElementById('pj-synchro')?.click(), 25000);
    }
    dessinerCurseur(p);
    rendre();
  }

  // ------------------------------------------------------------ PROJET PARTAGE : meme etat chez tous, en direct
  const moduleCourant = () => window.__PROJETS?.TYPES?.[moi.projet?.type]?.module?.();
  const lireEtat = () => { try { return JSON.stringify(moduleCourant()?.exporter?.() ?? null); } catch { return null; } };
  let rev = 0, dernierEtat = null, applique = false, attente = null, envoyes = new Set(), suivi = null;
  const idsFichiers = j => [...new Set([...(j || '').matchAll(/"fichier":\s*"([0-9a-f]{12})"/g)].map(x => x[1]))];
  async function envoyerEtat(repli = false) {
    if (!moi.projet?.id || dernierEtat == null) return;
    if (dernierEtat.length > 200000) { if (!repli) action('modifie (trop gros pour le direct : enregistrer pour partager)'); return; }
    const neufs = idsFichiers(dernierEtat).filter(i => !envoyes.has(i));
    if (neufs.length) {
      neufs.forEach(i => envoyes.add(i));
      await fetch0('/api/equipe/partager', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: neufs }) });
    }
    envoyer({ t: 'etat', pid: moi.projet.id, rev, donnees: dernierEtat }, true);
  }
  function recevoirEtat(m) {
    if (m.pid !== moi.projet?.id || m.rev <= rev) return;
    rev = m.rev; attente = m; if (!applique) appliquerAttente();
  }
  async function appliquerAttente() {
    applique = true;
    while (attente) {
      const m = attente; attente = null;
      try {
        const ids = idsFichiers(m.donnees);
        for (let i = 0; ids.length && i < 10; i++) {   // maillage neuf : il arrive par la synchro GitHub
          const r = await (await fetch0('/api/equipe/dispo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })).json();
          if (!r.manquants.length) break;
          await fetch0('/api/synchro', { method: 'POST' }); await new Promise(r_ => setTimeout(r_, 5000));
        }
        const mod = moduleCourant(), d = JSON.parse(m.donnees);
        await (mod?.appliquer || mod?.charger)?.call(mod, d);
        dernierEtat = lireEtat();
      } catch (e) { console.warn('equipe : etat non applique', e); }
    }
    applique = false;
  }
  setInterval(() => {                                  // detection generique de TOUT changement du projet ouvert
    if (applique || !moi.projet?.id) return;
    const e = lireEtat();
    if (e == null) return;
    if (dernierEtat == null) { dernierEtat = e; return; }
    if (e !== dernierEtat) { dernierEtat = e; rev = Date.now(); envoyerEtat(); }
  }, 700);
  // SUIVRE : meme onglet, meme projet, meme angle de vue
  function suivre(p) {
    if (p.onglet && p.onglet !== moi.onglet) document.querySelector(`[data-tab="${p.onglet}"]`)?.click();
    if (p.projet?.id && p.projet.id !== moi.projet?.id && !suivre.ouvre) {
      suivre.ouvre = true; Promise.resolve(window.SHWOuvrirProjet?.(p.projet.id)).finally(() => { suivre.ouvre = false; });
    }
    const mod = moduleVue();
    if (p.vue && mod?.cam && p.onglet === moi.onglet) { mod.cam.position.fromArray(p.vue[0]); mod.orb.target.fromArray(p.vue[1]); mod.orb.update(); }
  }
  function moduleVue() { return { cfg: window.__CFG, c3d: window.__C3D, kc: window.__KC, sw: window.__SW }[moi.onglet]; }

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
      ${estMoi ? '' : `<button data-suivre="${p.id}" title="Meme onglet, meme projet, meme angle de vue">${suivi === p.id ? 'Ne plus suivre' : 'Suivre'}</button>`}</div>`;
  }
  function rendre() {
    const repli = fen.classList.contains('repli');
    const n = pairs.size;
    fen.innerHTML = `<div class="eq-h"><span class="eq-pt" style="background:${ok ? '#3ddc97' : (cle ? '#f5c542' : '#8b919c')}"></span>
      <b>Equipe</b><span class="eq-n">${cle ? (ok ? (n ? `${n} en ligne` : 'seul pour l\'instant') : 'connexion...') : 'non configuree'}</span>
      <button data-r title="Reglages">&#9881;</button><button data-p title="Replier">${repli ? '&#9650;' : '&#9660;'}</button></div>
      <div class="eq-b">${cle ? [...pairs.values()].map(p => ligne(p, false)).join('') + ligne(moi, true)
        : `<p class="eq-v">Entre le meme <b>code d'equipe</b> (1 lettre + 4 chiffres) sur chaque poste pour travailler ensemble.</p>`}</div>`;
  }
  fen.addEventListener('click', async e => {
    if (e.target.closest('[data-p]')) { fen.classList.toggle('repli'); return rendre(); }
    if (e.target.closest('[data-r]')) return reglages();
    const s = e.target.closest('[data-suivre]');
    if (s) {
      const p = pairs.get(s.dataset.suivre); if (!p) return;
      suivi = suivi === p.id ? null : p.id;
      if (suivi) suivre(p);
      rendre();
    }
  });
  async function reglages() {
    const nom = prompt('Ton nom (vu par l\'equipe) :', moi.nom); if (nom === null) return;
    let code = (await (await fetch('/api/equipe')).json()).code || '';
    for (;;) {                                         // format simple : 1 lettre + 4 chiffres (ex. K4827)
      code = prompt('Code d\'equipe : 1 lettre + 4 chiffres (le meme sur chaque poste)', code); if (code === null) return;
      code = code.trim().toUpperCase(); if (/^[A-Z][0-9]{4}$/.test(code)) break;
      alert('Format attendu : 1 lettre puis 4 chiffres, par exemple K4827');
    }
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
  window.addEventListener('shw:projet', e => {
    const change = moi.projet?.id !== e.detail.id;
    moi.projet = e.detail;
    if (change) { rev = 0; dernierEtat = lireEtat(); envoyes = new Set(); envoyer({ t: 'demande', pid: e.detail.id }, true); }  // recupere l'etat en cours
    action(`ouvre « ${e.detail.nom} »`);
  });
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
