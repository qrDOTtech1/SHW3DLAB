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
    const sel = moi.onglet === 'c3d' ? (window.__C3D?.sel || []).map(o => o.id) : null;
    const m = { ...moi, souris, vue, sel, ...extra, ts: Date.now() };
    client.publish(sujet, await chiffrer(m), { qos: 0 });
  }

  // ------------------------------------------------------------ reception
  function recevoir(m) {
    if (m.t === 'bye') { pairs.delete(m.id); retirerCurseur(m.id); if (avec === m.id) quitterAvec(false); return rendre(); }
    const p = pairs.get(m.id) || { premier: Date.now() };
    const nouvelleAction = m.action && m.action !== p.action;
    Object.assign(p, m, { vu: Date.now() });
    if (nouvelleAction) p.actionTs = Date.now();
    pairs.set(m.id, p);
    if (m.t === 'ww' && m.cible === moi.id) return recevoirWW(m);
    if (avec === m.id) recevoirAvec(m, p);
    if (m.t === 'etat') recevoirEtat(m);
    if (m.t === 'demande' && m.pid === cleCourante) envoyerEtat(true);
    if (m.t === 'suivi' && m.cible === moi.id) envoyerEtat(true);
    if (m.onglet === 'c3d' && moi.onglet === 'c3d' && m.sel) window.__C3D?.surlignerPair?.(m.id, m.sel, m.couleur);
    if (suivi === m.id) suivre(p);
    if (m.t === 'save') {                              // un coequipier a enregistre : on recupere apres son envoi
      notifier(`${m.nom} a sauvegarde ${m.quoi || 'un projet'}`, m.couleur);
      clearTimeout(recevoir._s);                       // recupere sa sauvegarde des qu'elle est en ligne, sans rien relancer
      const recup = async () => {
        await fetch0('/api/synchro', { method: 'POST' }).catch(() => { });
        window.__PROJETS?.rafraichir?.();
      };
      recevoir._s = setTimeout(recup, 12000); setTimeout(recup, 30000);
    }
    dessinerCurseur(p);
    rendre();
  }

  function notifier(txt, coul) {
    const d = document.createElement('div');
    d.style.cssText = `position:fixed;right:16px;bottom:16px;z-index:9650;background:#14171d;color:#e9ebef;border-left:4px solid ${coul || '#ff6410'};padding:10px 14px;border-radius:8px;font:13px 'Segoe UI',sans-serif;box-shadow:0 8px 24px #0008`;
    d.textContent = txt; document.body.appendChild(d); setTimeout(() => d.remove(), 7000);
  }
  // ------------------------------------------------------------ PROJET PARTAGE : meme etat chez tous, en direct
  // La "session" = projet enregistre, ou espace de travail de l'onglet s'il n'est pas encore enregistre.
  // Versions : compteur logique (jamais l'heure du PC : les horloges des postes different).
  const ONGLET_TYPE = t => window.__PROJETS?.TYPES?.[t]?.onglet;
  const cleLocale = () => {
    if (moi.projet?.id && ONGLET_TYPE(moi.projet.type) === moi.onglet) return moi.projet.id;
    if (moi.onglet === 'cfg') return window.__CFG?.modele ? 'libre:cfg:' + window.__CFG.modele : null;
    return moduleVue()?.exporter ? 'libre:' + moi.onglet : null;
  };
  const lireEtat = () => { try { return JSON.stringify(moduleVue()?.exporter?.() ?? null); } catch { return null; } };
  let rev = 0, dernierEtat = null, applique = false, attente = null, envoyes = new Set(), suivi = null, cleCourante = null;
  const idsFichiers = j => [...new Set([...(j || '').matchAll(/"fichier":\s*"([0-9a-f]{12})"/g)].map(x => x[1]))];
  async function envoyerEtat(force = false) {
    if (!cleCourante || dernierEtat == null || dernierEtat === 'null') return;
    if (dernierEtat.length > 200000) { if (!force) action('modifie (trop gros pour le direct : enregistrer pour partager)'); return; }
    const neufs = idsFichiers(dernierEtat).filter(i => !envoyes.has(i));
    if (neufs.length) {
      neufs.forEach(i => envoyes.add(i));
      await fetch0('/api/equipe/partager', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: neufs }) });
    }
    envoyer({ t: 'etat', pid: cleCourante, rev, force, donnees: dernierEtat }, true);
  }
  function recevoirEtat(m) {
    const meneur = suivi === m.id || (avec === m.id && rejoint);
    const pourMoi = m.pid === cleCourante || (meneur && m.force) || (avec === m.id && m.onglet === moi.onglet);
    if (!pourMoi) return;
    if (!m.force && (m.rev < rev || (m.rev === rev && m.id < moi.id))) return;
    if (m.force && !meneur && m.rev <= rev) return;     // une reponse a "demande" n'ecrase que si elle est plus recente
    rev = Math.max(rev, m.rev); attente = m; if (!applique) appliquerAttente();
  }
  async function appliquerAttente() {
    applique = true;
    while (suivre.ouvre) await new Promise(r => setTimeout(r, 100));   // d'abord finir d'ouvrir le projet, sinon objets en double
    while (attente) {
      const m = attente; attente = null;
      try {
        const ids = idsFichiers(m.donnees);
        for (let i = 0; ids.length && i < 10; i++) {   // maillage neuf : il arrive par la synchro GitHub
          const r = await (await fetch0('/api/equipe/dispo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })).json();
          if (!r.manquants.length) break;
          await fetch0('/api/synchro', { method: 'POST' }); await new Promise(r_ => setTimeout(r_, 5000));
        }
        const mod = moduleVue(), d = JSON.parse(m.donnees);
        await (mod?.appliquer || mod?.charger)?.call(mod, d);
        cleCourante = m.pid; moi.cle = m.pid; dernierEtat = lireEtat();
      } catch (e) { console.warn('equipe : etat non applique', e); }
    }
    applique = false;
  }
  setInterval(() => {                                  // detection generique de TOUT changement de la session
    if (applique || suivre.ouvre) return;
    if (!avec && ++tic % 6) return;                    // 80 ms en travail commun, 480 ms sinon
    const cle = (suivi && pairs.get(suivi)?.cle) || (avec && rejoint && pairs.get(avec)?.cle) || cleLocale();
    if (cle !== cleCourante) {
      cleCourante = cle; moi.cle = cle; rev = 0; dernierEtat = lireEtat(); envoyes = new Set();
      if (cle) envoyer({ t: 'demande', pid: cle }, true);   // recupere l'etat en cours chez les autres
      return;
    }
    if (!cle) return;
    const e = lireEtat();
    if (e == null) return;
    if (dernierEtat == null) { dernierEtat = e; return; }
    if (e !== dernierEtat) { dernierEtat = e; rev += 1; envoyerEtat(); }
  }, 80);

  // ------------------------------------------------------------ TRAVAILLER AVEC : les mains sur le meme objet
  // Deux postes lies : meme page, meme projet, memes modifications, meme vue. Le dernier qui agit mene la vue.
  let avec = null, rejoint = false, camLiee = true, tic = 0, interaction = 0, distant = false;
  function quitterAvec(prevenir = true) {
    if (prevenir && avec) envoyer({ t: 'ww', cible: avec, on: false }, true);
    avec = null; rejoint = false; rendre();
  }
  function travaillerAvec(p) {
    if (avec === p.id) return quitterAvec();
    suivi = null; avec = p.id; rejoint = true; camLiee = true;
    aller(p); envoyer({ t: 'ww', cible: p.id, on: true }, true); envoyer({ t: 'suivi', cible: p.id }, true); rendre();
  }
  function recevoirWW(m) {
    if (!m.on) { if (avec === m.id) { avec = null; rejoint = false; } }
    else { suivi = null; avec = m.id; rejoint = false; camLiee = true; envoyerEtat(true); }
    rendre();
  }
  function aller(p) {
    distant = true;
    if (p.onglet && p.onglet !== moi.onglet) document.querySelector(`[data-tab="${p.onglet}"]`)?.click();
    distant = false;
    if (p.projet?.id && p.projet.id !== moi.projet?.id && !suivre.ouvre) {
      suivre.ouvre = true; Promise.resolve(window.SHWOuvrirProjet?.(p.projet.id)).finally(() => { suivre.ouvre = false; });
    }
  }
  function recevoirAvec(m, p) {
    if (m.t === 'nav') aller(p);
    if (m.t === 'cam' && camLiee && m.onglet === moi.onglet && performance.now() > interaction && m.vue) {
      const mod = moduleVue();
      if (mod?.cam) { mod.cam.position.fromArray(m.vue[0]); mod.orb.target.fromArray(m.vue[1]); mod.orb.update(); }
    }
    if (m.t === 'champ' && moi.onglet === 'creer' && m.onglet === 'creer') {   // page sans projet : seulement les champs, jamais un bouton
      const el = document.getElementById(m.champ); if (!el) return;
      distant = true;
      if (el.type === 'checkbox') el.checked = m.val; else el.value = m.val;
      el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
      distant = false;
    }
  }
  ['pointerdown', 'pointermove', 'wheel'].forEach(t => document.addEventListener(t, e => {
    if (e.target?.tagName !== 'CANVAS' || (t === 'pointermove' && !e.buttons)) return;
    interaction = performance.now() + 500;
  }, { capture: true, passive: true }));
  setInterval(() => { if (avec && camLiee && performance.now() < interaction && moduleVue()?.cam) envoyer({ t: 'cam' }, true); }, 60);
  document.addEventListener('input', e => {
    if (distant || !avec || moi.onglet !== 'creer' || !e.target.id || e.target.closest('#eq-fen')) return;
    envoyer({ t: 'champ', champ: e.target.id, val: e.target.type === 'checkbox' ? e.target.checked : e.target.value }, true);
  }, true);

  // ------------------------------------------------------------ modification sur le disque (session Claude, synchro GitHub)
  let mtimeProjet = null, idMtime = null, monEcriture = 0;
  setInterval(async () => {
    const id = moi.projet?.id;
    if (!id || applique || id !== cleCourante) { mtimeProjet = null; idMtime = id; return; }
    try {
      const r = await (await fetch0(`/api/projets/${id}/rev`)).json();
      if (idMtime !== id || mtimeProjet == null) { idMtime = id; mtimeProjet = r.mtime; return; }
      if (r.mtime === mtimeProjet) return;
      mtimeProjet = r.mtime;
      if (performance.now() < monEcriture) return;
      const d = await (await fetch0('/api/projets/' + id)).json();
      const texte = JSON.stringify(d.donnees);
      if (texte === dernierEtat || applique) return;
      applique = true;
      const mod = moduleVue();
      await (mod?.appliquer || mod?.charger)?.call(mod, moi.projet.type && mod === window.__CFG ? { modele: moi.projet.type, ...d.donnees } : d.donnees);
      dernierEtat = lireEtat(); applique = false;
      action('projet modifie sur le disque : a jour');
    } catch { applique = false; }
  }, 2000);

  // ------------------------------------------------------------ nouveau code recu (ou ecrit par une session Claude)
  let sigVue = null, bandeau = false;
  setInterval(async () => {
    try {
      const v = await (await fetch0('/api/version')).json();
      sigVue ??= v.web;
      bandeau = v.web !== sigVue || v.py !== v.py_demarrage;
      fen.dataset.code = bandeau ? (v.py !== v.py_demarrage ? 'py' : 'web') : '';
      rendre();
    } catch { }
  }, 5000);
  // SUIVRE : meme onglet, meme projet, meme angle de vue
  function suivre(p) {
    aller(p);
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
    return `<div class="eq-l"><i style="background:${p.couleur}"></i><div class="eq-t"><b>${p.nom}${estMoi ? ' (moi)' : ''}${p.claude ? ' <span title="Une session Claude modifie le code sur ce poste" style="color:#c77dff;font-weight:500">+ Claude au travail</span>' : ''}</b>
      <span>${ou}</span><em>${p.action || ''}${estMoi ? '' : ' · ' + ilya(p.actionTs || p.vu)}</em></div>
      ${estMoi ? '' : `<button data-suivre="${p.id}" title="Meme onglet, meme projet, meme angle de vue">${suivi === p.id ? 'Ne plus suivre' : 'Suivre'}</button>
      <button data-avec="${p.id}" class="${avec === p.id ? 'on' : ''}" title="Les mains sur le meme objet : meme page, meme projet, memes modifications, meme vue">${avec === p.id ? 'Arreter' : 'Travailler avec'}</button>`}</div>`;
  }
  function rendre() {
    const repli = fen.classList.contains('repli');
    const n = pairs.size;
    fen.innerHTML = `<div class="eq-h"><span class="eq-pt" style="background:${ok ? '#3ddc97' : (cle ? '#f5c542' : '#8b919c')}"></span>
      <b>Equipe</b><span class="eq-n">${cle ? (ok ? (n ? `${n} en ligne` : 'seul pour l\'instant') : 'connexion...') : 'non configuree'}</span>
      <button data-coul title="Choisir ma couleur" style="color:${moi.couleur}">&#9679;</button><button data-r title="Reglages">&#9881;</button><button data-p title="Replier">${repli ? '&#9650;' : '&#9660;'}</button></div>
      ${fen.dataset.code ? `<div class="eq-code">Nouveau code recu <button data-maj>Mettre a jour</button></div>` : ''}
      ${avec ? `<div class="eq-avec">En direct avec ${pairs.get(avec)?.nom || '...'} <button data-cam>${camLiee ? 'Vue liee' : 'Vue libre'}</button></div>` : ''}
      <div class="eq-b">${cle ? [...pairs.values()].map(p => ligne(p, false)).join('') + ligne(moi, true)
        : `<p class="eq-v">Entre le meme <b>code d'equipe</b> (1 lettre + 4 chiffres) sur chaque poste pour travailler ensemble.</p>`}</div>`;
  }
  fen.addEventListener('click', async e => {
    if (e.target.closest('[data-p]')) { fen.classList.toggle('repli'); return rendre(); }
    if (e.target.closest('[data-coul]')) return choisirCouleur();
    if (e.target.closest('[data-r]')) return reglages();
    if (e.target.closest('[data-cam]')) { camLiee = !camLiee; return rendre(); }
    if (e.target.closest('[data-maj]')) {
      if (fen.dataset.code === 'py') {
        await fetch0('/api/redemarrer', { method: 'POST' }).catch(() => { });
        for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 1500)); try { if ((await fetch0('/api/equipe')).ok && i > 2) break; } catch { } }
      }
      return location.reload();
    }
    const w = e.target.closest('[data-avec]');
    if (w) { const p = pairs.get(w.dataset.avec); if (p) travaillerAvec(p); return; }
    const s = e.target.closest('[data-suivre]');
    if (s) {
      const p = pairs.get(s.dataset.suivre); if (!p) return;
      if (avec) quitterAvec();
      suivi = suivi === p.id ? null : p.id;
      if (suivi) { suivre(p); envoyer({ t: 'suivi', cible: p.id }, true); }   // l'etat exact de la personne suivie, tout de suite
      rendre();
    }
  });
  // couleur personnelle : seul le poste change, ni le nom ni le code ne sont redemandes
  function choisirCouleur() {
    const i = document.createElement('input'); i.type = 'color'; i.value = moi.couleur || '#ff6410';
    i.addEventListener('change', async () => {
      moi.couleur = i.value; rendre(); envoyer({ t: 'p' }, true);
      await fetch0('/api/equipe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ couleur: i.value }) });
    });
    i.click();
  }
  setInterval(async () => { try { moi.claude = (await (await fetch0('/api/claude')).json()).actif; } catch { } }, 10000);
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
    if (nav) { moi.onglet = nav.dataset.tab; [...pairs.values()].forEach(dessinerCurseur); if (avec && !distant) setTimeout(() => envoyer({ t: 'nav' }, true)); return action('dans ' + (ONGLETS[moi.onglet] || moi.onglet)); }
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
    moi.projet = e.detail; monEcriture = performance.now() + 4000;
    if (avec) envoyer({ t: 'nav' }, true);
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
    if (/\/api\/projets/.test(url) && /POST|DELETE/i.test(o.method || '')) monEcriture = performance.now() + 4000;
    if (/\/api\/projets(\/[^/]+(\/dupliquer)?)?$/.test(url) && /POST|DELETE/i.test(o.method || '') && r.ok) {
      action(/DELETE/i.test(o.method) ? 'met un projet a la corbeille' : 'enregistre un projet'); envoyer({ t: 'save', quoi: moi.projet?.nom ? `« ${moi.projet.nom} »` : '' }, true);
    }
    return r;
  };
  setInterval(() => {                                  // presence + menage des absents
    envoyer({ t: 'p' }, true);
    for (const [id, p] of pairs) if (Date.now() - p.vu > 20000) { pairs.delete(id); retirerCurseur(id); if (avec === id) quitterAvec(false); if (suivi === id) suivi = null; }
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
#eq-fen .eq-l button.on{background:#ff6410;color:#0d0f13;border-color:#ff6410}
#eq-fen .eq-avec,#eq-fen .eq-code{display:flex;justify-content:space-between;align-items:center;gap:6px;margin:0 10px 8px;padding:5px 8px;border-radius:8px;background:#ff641022;color:#ffb48a;font-size:11px}
#eq-fen .eq-avec button,#eq-fen .eq-code button{background:#1d2027;border:1px solid #2a2e37;color:#e9ebef;border-radius:6px;font-size:11px;padding:2px 6px;cursor:pointer}
#eq-fen .eq-l{flex-wrap:wrap}
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
