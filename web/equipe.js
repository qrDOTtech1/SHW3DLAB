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
    const m = { ...moi, souris, vue, sel, v: rev, h: empreinte(), ...extra, ts: Date.now() };
    if (window.__eqPerdre && m.t === 'etat') return;   // test : simule un message perdu par le relais
    client.publish(sujet, await chiffrer(m), { qos: m.t === 'etat' ? 1 : 0 });
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
    if (avec === m.id && m.t === 'fen') { recevoirFen(m); return; }
    if (avec === m.id && m.t === 'fenact') { recevoirFenAct(m); return; }
    if (m.t === 'rtc' && m.cible === moi.id) signalRTC(m);
    if (!liens.has(m.id) && moi.id < m.id) ouvrirLien(m.id);   // le plus petit identifiant appelle
    if (m.t === 'shop' && avec === m.id) window.__SHOP?.appliquer(m.shop);
    if (m.t === 'etat') recevoirEtat(m);
    verifierAccord(m);
    if (m.t === 'demande' && m.pid === cleCourante) envoyerEtat(true);
    if (m.t === 'suivi' && m.cible === moi.id) envoyerEtat(true);
    if (m.onglet === 'c3d' && moi.onglet === 'c3d' && m.sel) window.__C3D?.surlignerPair?.(m.id, m.sel, m.couleur);
    if (suivi === m.id) suivre(p);
    if (m.t === 'save') {                              // un coequipier a enregistre : on recupere apres son envoi
      notifier(`${hasard(CLARKSON.sauve, m.nom)} ${m.quoi ? 'Projet : ' + m.quoi : ''}`, m.couleur);
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
  // ------------------------------------------------------------ LIEN DIRECT entre les deux PC (WebRTC, chiffre)
  // Le relais ne sert qu'a se presenter : ensuite les maillages passent de navigateur a navigateur, sans GitHub.
  const liens = new Map(), attentes = new Map();
  function brancher(id, pc, dc) {
    dc.binaryType = 'arraybuffer';
    const l = liens.get(id); l.dc = dc;
    let enCours = null;
    dc.onopen = rendre; dc.onclose = () => { liens.delete(id); rendre(); };
    dc.onmessage = async ev => {
      if (typeof ev.data === 'string') {
        const m = JSON.parse(ev.data);
        if (m.veut) {
          const r = await fetch0(`/c3d/${m.veut}.stl`);
          if (!r.ok) return dc.send(JSON.stringify({ absent: m.veut }));
          const b = await r.arrayBuffer();
          dc.send(JSON.stringify({ debut: m.veut, taille: b.byteLength }));
          for (let o = 0; o < b.byteLength; o += 60000) {
            while (dc.bufferedAmount > 4e6) await new Promise(t => setTimeout(t, 20));
            dc.send(b.slice(o, o + 60000));
          }
        }
        if (m.debut) enCours = { id: m.debut, taille: m.taille, buf: new Uint8Array(m.taille), o: 0 };
        if (m.absent) attentes.get(m.absent)?.ko(new Error('absent'));
        return;
      }
      enCours.buf.set(new Uint8Array(ev.data), enCours.o); enCours.o += ev.data.byteLength;
      if (enCours.o >= enCours.taille) {
        const f = enCours; enCours = null;
        await fetch0('/api/equipe/recevoir/' + f.id, { method: 'POST', body: f.buf });
        attentes.get(f.id)?.ok(f.taille);
      }
    };
  }
  const creerPC = id => {
    const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
    liens.set(id, { pc, dc: null });
    pc.ondatachannel = e => brancher(id, pc, e.channel);
    pc.onconnectionstatechange = () => { if (['failed', 'closed'].includes(pc.connectionState)) { liens.delete(id); rendre(); } };
    return pc;
  };
  const icePret = pc => new Promise(ok => { if (pc.iceGatheringState === 'complete') return ok(); const t = setTimeout(ok, 3000); pc.addEventListener('icegatheringstatechange', () => { if (pc.iceGatheringState === 'complete') { clearTimeout(t); ok(); } }); });
  async function ouvrirLien(id) {
    const pc = creerPC(id); brancher(id, pc, pc.createDataChannel('shw'));
    await pc.setLocalDescription(await pc.createOffer()); await icePret(pc);
    envoyer({ t: 'rtc', cible: id, sdp: pc.localDescription }, true);
  }
  async function signalRTC(m) {
    if (m.sdp.type === 'offer') {
      liens.get(m.id)?.pc.close();
      const pc = creerPC(m.id);
      await pc.setRemoteDescription(m.sdp);
      await pc.setLocalDescription(await pc.createAnswer()); await icePret(pc);
      envoyer({ t: 'rtc', cible: m.id, sdp: pc.localDescription }, true);
    } else await liens.get(m.id)?.pc.setRemoteDescription(m.sdp);
  }
  function demanderDirect(pair, fid, delai = 60000) {
    const dc = liens.get(pair)?.dc;
    if (dc?.readyState !== 'open') return Promise.reject(new Error('pas de lien'));
    return new Promise((ok, ko) => {
      const t = setTimeout(() => ko(new Error('delai')), delai);
      attentes.set(fid, { ok: v => { clearTimeout(t); ok(v); }, ko: e => { clearTimeout(t); ko(e); } });
      dc.send(JSON.stringify({ veut: fid }));
    });
  }
  window.__eqLien = { liens, demanderDirect };
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
    dernierEnvoiEtat = performance.now();
    envoyer({ t: 'etat', pid: cleCourante, rev, force, donnees: dernierEtat }, true);
  }
  function recevoirEtat(m) {
    const meneur = suivi === m.id || (avec === m.id && rejoint);
    const pourMoi = m.pid === cleCourante || (meneur && m.force) || (avec === m.id && m.onglet === moi.onglet);
    if (!pourMoi) return;
    if (!m.force && (m.rev < rev || (m.rev === rev && m.id < moi.id))) return;
    if (m.force && !meneur && (m.rev < rev || (m.rev === rev && m.id < moi.id))) return;     // une reponse a "demande" n'ecrase que si elle est plus recente
    rev = Math.max(rev, m.rev); attente = m; if (!applique) appliquerAttente();
  }
  // ANTI-DIVERGENCE : le relais peut perdre un message. Chaque poste annonce l'empreinte de son etat ; si elles different
  // alors qu'on travaille sur la meme chose, le poste en retard redemande l'etat. Les ecrans finissent toujours identiques.
  let _hE = null, _hV = 0, ecart = 0, dernierAppel = 0;
  function empreinte() {
    if (dernierEtat == null) return 0;
    if (_hE === dernierEtat) return _hV;
    _hE = dernierEtat; const t = dernierEtat.replace(/(\.\d{2})\d+/g, '$1');
    let h = 5381; for (let i = 0; i < t.length; i++) h = (h * 33 + t.charCodeAt(i)) | 0;
    return (_hV = h);
  }
  function verifierAccord(m) {
    if (!m.h || !cleCourante || applique || m.cle !== cleCourante || m.onglet !== moi.onglet) return;
    if (m.h === empreinte()) { ecart = 0; return; }
    if (performance.now() - dernierEnvoiEtat < 1500) return;   // une modification est en train de partir
    if (++ecart < 3) return;
    const enRetard = m.v > rev || (m.v === rev && m.id > moi.id);
    if (enRetard && performance.now() - dernierAppel > 4000) { dernierAppel = performance.now(); envoyer({ t: 'demande', pid: cleCourante }, true); }
    else if (!enRetard && performance.now() - dernierAppel > 4000) { dernierAppel = performance.now(); envoyerEtat(true); }
  }
  let dernierEnvoiEtat = 0;
  async function appliquerAttente() {
    applique = true;
    while (suivre.ouvre) await new Promise(r => setTimeout(r, 100));   // d'abord finir d'ouvrir le projet, sinon objets en double
    while (attente) {
      const m = attente; attente = null;
      try {
        for (let i = 0; i < 30 && m.onglet !== moi.onglet; i++) await new Promise(r => setTimeout(r, 100));   // pas d'etat sur le mauvais module
        if (m.onglet !== moi.onglet) continue;
        const ids = idsFichiers(m.donnees);
        const man = (await (await fetch0('/api/equipe/dispo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })).json()).manquants;
        for (const i of man) await demanderDirect(m.id, i).catch(() => { });   // d'abord par le lien direct, sinon par la sauvegarde
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
    let cle = (suivi && pairs.get(suivi)?.cle) || (avec && rejoint && pairs.get(avec)?.cle) || cleLocale();
    if (cle?.startsWith('libre:') && !suivi && !avec) cle = null;   // sans projet enregistre, on ne partage que si on travaille ensemble
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
  // ---- le klaxon : on previent AVANT de toucher au travail de quelqu'un
  const CLARKSON = {
    sauve: [n => `${n} a sauvegarde. Oui, sauvegarde. Comme un adulte responsable. Incroyable.`, n => `Nouvelle sauvegarde de ${n}. Ambitieux. Inutile. Magnifique.`, n => `${n} vient de sauvegarder. Et sur cette planete, c'est deja un exploit.`],
    rejoint: [n => `${n} monte a bord. Accrochez-vous, ca va mal se passer. Ou tres bien.`, n => `${n} met les mains sur le meme objet. Que pourrait-il arriver de mal ?`],
    parti: [n => `${n} a quitte le navire. Sans un mot. Typique.`],
  };
  const hasard = (l, n) => l[Math.floor(Math.random() * l.length)](n);
  function nonEnregistre() {
    const mod = moduleVue(); if (!mod?.exporter) return 0;
    const n = moi.onglet === 'c3d' ? mod.objets.length : 1;
    if (moi.onglet === 'c3d' && !n) return 0;
    if (moi.onglet === 'cfg' && !mod.modele) return 0;
    if (moi.onglet !== 'c3d' && moi.onglet !== 'cfg' && !(moi.projet?.id && rev)) return 0;
    const projetIci = moi.projet?.id && ONGLET_TYPE(moi.projet.type) === moi.onglet;
    return (!projetIci || rev) ? n : 0;
  }
  function demander(titre, texte, choix) {
    return new Promise(ok => {
      const v = document.createElement('div');
      v.style.cssText = 'position:fixed;inset:0;background:#0008;z-index:9800;display:grid;place-items:center';
      v.innerHTML = `<div style="width:min(440px,92vw);background:#14171d;color:#e9ebef;border:1px solid #ff6410;border-radius:14px;padding:18px 20px;font:13px 'Segoe UI',sans-serif">
        <b style="font-size:15px">${titre}</b><p style="line-height:1.45">${texte}</p>
        <div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">${choix.map(([k, l, fort]) => `<button data-c="${k}" style="padding:7px 12px;border-radius:8px;cursor:pointer;border:1px solid ${fort ? '#ff6410' : '#2a2e37'};background:${fort ? '#ff6410' : '#1d2027'};color:${fort ? '#14171d' : '#e9ebef'};font-weight:${fort ? 600 : 400}">${l}</button>`).join('')}</div></div>`;
      v.addEventListener('click', e => { const b = e.target.closest('[data-c]'); if (b) { v.remove(); ok(b.dataset.c); } });
      v.addEventListener('keydown', e => e.stopPropagation());
      document.body.appendChild(v);
    });
  }
  async function enregistrerIci() {
    const t = { c3d: 'creation3d', kc: 'keycaps', sw: 'swork', cfg: window.__CFG?.modele }[moi.onglet];
    if (t) await window.__PROJETS?.enregistrer?.(t);
  }
  // true = on peut y aller. Rejoindre quelqu'un remplace ce qu'il y a sur mon plan.
  async function avantDeRejoindre(p) {
    const n = nonEnregistre(); if (!n) return true;
    const quoi = moi.onglet === 'c3d' ? `${n} objet${n > 1 ? 's' : ''} non enregistre${n > 1 ? 's' : ''}` : 'des modifications non enregistrees';
    const c = await demander('Une petite seconde.', `Tu as ${quoi} sur ton plan. Si tu rejoins ${p.nom}, ca disparait de ton ecran. Definitivement. Comme ma patience devant un mode d'emploi. Que fait-on ?`,
      [['non', 'Annuler'], ['go', 'Foncer quand meme'], ['save', 'Enregistrer puis rejoindre', true]]);
    if (c === 'save') await enregistrerIci();
    return c !== 'non';
  }
  async function travaillerAvec(p) {
    if (avec === p.id) return quitterAvec();
    if (!await avantDeRejoindre(p)) return;
    suivi = null; avec = p.id; rejoint = true; camLiee = true;
    aller(p); envoyer({ t: 'ww', cible: p.id, on: true }, true); envoyer({ t: 'suivi', cible: p.id }, true); rendre();
  }
  function recevoirWW(m) {
    if (!m.on) { if (avec === m.id) { avec = null; rejoint = false; notifier(hasard(CLARKSON.parti, m.nom), m.couleur); } }
    else {
      suivi = null; avec = m.id; rejoint = false; camLiee = true; envoyerEtat(true);
      if (window.__SHOP?.etat().on) envoyer({ t: 'shop', shop: window.__SHOP.etat() }, true);
      notifier(hasard(CLARKSON.rejoint, m.nom), m.couleur);
      const n = nonEnregistre();
      if (n) demander(`${m.nom} veut bosser avec toi.`, `Ton plan n'est pas enregistre, et ${m.nom} le voit maintenant. Il peut le modifier. Avec ses mains. Tu enregistres, par prudence ?`,
        [['non', 'Refuser'], ['go', 'Bosser sans filet'], ['save', 'Enregistrer et bosser', true]]).then(c => {
          if (c === 'save') enregistrerIci();
          if (c === 'non') quitterAvec();
        });
    }
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

  // ------------------------------------------------------------ FENETRES PARTAGEES (travail commun)
  // Chaque fenetre tourne chez celui qui l'a ouverte : l'autre en voit une copie exacte, et ses gestes (clic, valeur,
  // deplacement, fermeture) sont executes par la vraie fenetre. Deux postes, une seule execution : aucun doublon.
  const SEL_FEN = '.at-flot:not([data-miroir]):not(#at-shop),.c3d-pan:not([data-miroir])';
  const envoyees = new Map(), miroirs = new Map();
  let numFen = 0;
  const cleFen = f => (f.dataset.fen ||= moi.id + '-' + (++numFen));
  function photoFen(f) {
    const c = f.cloneNode(true), a_ = f.querySelectorAll('input,select,textarea'), b_ = c.querySelectorAll('input,select,textarea');
    a_.forEach((x, i) => {
      if (x.type === 'file') return;
      if (x.type === 'checkbox' || x.type === 'radio') { if (x.checked) b_[i].setAttribute('checked', ''); else b_[i].removeAttribute('checked'); }
      else if (x.tagName === 'SELECT') b_[i].querySelectorAll('option').forEach((o, k) => { if (k === x.selectedIndex) o.setAttribute('selected', ''); else o.removeAttribute('selected'); });
      else if (x.tagName === 'TEXTAREA') b_[i].textContent = x.value;
      else b_[i].setAttribute('value', x.value);
    });
    c.querySelectorAll('img').forEach(i => { if ((i.getAttribute('src') || '').startsWith('data:')) i.removeAttribute('src'); });
    return c.innerHTML;
  }
  setInterval(() => {
    if (!avec) { if (envoyees.size) envoyees.clear(); if (miroirs.size) { miroirs.forEach(m => m.remove()); miroirs.clear(); } return; }
    const vues = new Set();
    document.querySelectorAll(SEL_FEN).forEach(f => {
      const k = cleFen(f), r = f.getBoundingClientRect(); vues.add(k);
      const html = photoFen(f), pos = [Math.round(r.left), Math.round(r.top), Math.round(r.width)].join();
      const av = envoyees.get(k);
      if (av?.html === html && av?.pos === pos) return;
      if (html.length > 150000) return;
      const m = { t: 'fen', k, x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), cls: f.className };
      if (av?.html !== html) m.html = html;
      envoyees.set(k, { html, pos });
      envoyer(m, true);
    });
    for (const k of [...envoyees.keys()]) if (!vues.has(k)) { envoyees.delete(k); envoyer({ t: 'fen', k, ferme: 1 }, true); }
  }, 120);
  function recevoirFen(m) {
    let d = miroirs.get(m.k);
    if (m.ferme) { d?.remove(); miroirs.delete(m.k); return; }
    if (!d) {
      d = document.createElement('div'); d.dataset.miroir = m.k; d.className = m.cls;
      d.addEventListener('click', ev => {
        ev.preventDefault(); ev.stopPropagation();
        const c = ev.target.closest('button,a,[data-mod],[data-m],[data-i],[data-o],[data-pose],[data-sup],input[type=checkbox],input[type=radio],summary,label') || ev.target;
        if (c.matches('input[type=number],input[type=text],input[type=range],select,textarea,input:not([type])')) return;
        envoyer({ t: 'fenact', k: m.k, q: 'click', i: [...d.querySelectorAll('*')].indexOf(c) }, true);
      }, true);
      const champ = ev => { if (ev.target.type === 'file') return; envoyer({ t: 'fenact', k: m.k, q: 'val', i: [...d.querySelectorAll('*')].indexOf(ev.target), v: ev.target.type === 'checkbox' ? ev.target.checked : ev.target.value, fin: ev.type === 'change' }, true); };
      d.addEventListener('input', champ); d.addEventListener('change', champ);
      d.addEventListener('keydown', ev => {
        ev.stopPropagation();
        if (ev.key === 'Enter') { champ(ev); envoyer({ t: 'fenact', k: m.k, q: 'entree', i: [...d.querySelectorAll('*')].indexOf(ev.target) }, true); }
      });
      let bouge = false;
      d.addEventListener('pointerdown', () => { bouge = true; });
      addEventListener('pointermove', () => {
        if (!bouge || !d.isConnected || d.dataset.g) return;
        d.dataset.g = 1; setTimeout(() => { delete d.dataset.g; const r = d.getBoundingClientRect(); envoyer({ t: 'fenact', k: m.k, q: 'pos', x: Math.round(r.left), y: Math.round(r.top) }, true); }, 60);
      });
      addEventListener('pointerup', () => { bouge = false; });
      Object.assign(d.style, { position: 'fixed', zIndex: 9390, margin: 0, right: 'auto', bottom: 'auto', transform: 'none', outline: `2px solid ${pairs.get(avec)?.couleur || '#ff6410'}` });
      miroirs.set(m.k, d); document.body.appendChild(d); d._b = () => bouge;
    }
    if (!d._b()) { d.style.left = Math.min(m.x, innerWidth - 60) + 'px'; d.style.top = Math.min(m.y, innerHeight - 30) + 'px'; }
    d.style.width = m.w + 'px';
    if (m.html != null) {
      const act = document.activeElement, idx = d.contains(act) ? [...d.querySelectorAll('*')].indexOf(act) : -1, val = act?.value, sel = act?.selectionStart;
      d.innerHTML = m.html;
      if (idx >= 0) { const n = d.querySelectorAll('*')[idx]; if (n) { n.focus(); if (val !== undefined) n.value = val; try { n.setSelectionRange(sel, sel); } catch { } } }
    }
  }
  function recevoirFenAct(m) {
    const f = [...document.querySelectorAll(SEL_FEN)].find(x => x.dataset.fen === m.k); if (!f) return;
    if (m.q === 'pos') { Object.assign(f.style, { position: 'fixed', left: m.x + 'px', top: m.y + 'px', right: 'auto', bottom: 'auto', transform: 'none', margin: 0 }); return; }
    const c = f.querySelectorAll('*')[m.i]; if (!c) return;
    if (m.q === 'click') return c.click();
    if (m.q === 'entree') return c.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    if (c.type === 'checkbox') c.checked = m.v; else c.value = m.v;
    c.dispatchEvent(new Event(m.fin ? 'change' : 'input', { bubbles: true }));
  }

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
      <span>${ou}${!estMoi && liens.get(p.id)?.dc?.readyState === 'open' ? ' · lien direct' : ''}</span><em>${p.action || ''}${estMoi ? '' : ' · ' + ilya(p.actionTs || p.vu)}</em></div>
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
    if (e.target.closest('[data-p]')) { fen.classList.toggle('repli'); memoFen(); return rendre(); }
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
      if (suivi !== p.id && !await avantDeRejoindre(p)) return;
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

  // deplacable par sa barre de titre, position memorisee ; repliee par defaut quand on l'a repliee
  try {
    const m_ = JSON.parse(localStorage.getItem('shw-eq-fen') || '{}');
    if (m_.x != null) Object.assign(fen.style, { left: Math.min(m_.x, innerWidth - 60) + 'px', top: Math.min(m_.y, innerHeight - 30) + 'px', bottom: 'auto' });
    if (m_.repli) fen.classList.add('repli');
  } catch { }
  const memoFen = () => { try { const r = fen.getBoundingClientRect(); localStorage.setItem('shw-eq-fen', JSON.stringify({ x: fen.style.top ? r.left : null, y: r.top, repli: fen.classList.contains('repli') })); } catch { } };
  fen.addEventListener('pointerdown', e => {
    if (!e.target.closest('.eq-h') || e.target.closest('button')) return;
    const r = fen.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    const bouge = ev => Object.assign(fen.style, { left: Math.max(0, Math.min(innerWidth - 60, ev.clientX - dx)) + 'px', top: Math.max(0, Math.min(innerHeight - 30, ev.clientY - dy)) + 'px', bottom: 'auto' });
    const fin = () => { removeEventListener('pointermove', bouge); removeEventListener('pointerup', fin); memoFen(); };
    addEventListener('pointermove', bouge); addEventListener('pointerup', fin);
  });
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
  window.addEventListener('shw:shop', e => { if (avec) envoyer({ t: 'shop', shop: e.detail }, true); });
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
#eq-fen{position:fixed;left:72px;bottom:14px;z-index:9001;width:290px;background:#0d0f13ee;border:1px solid #2a2e37;border-radius:12px;color:#e9ebef;
  font:12px 'Segoe UI',system-ui,sans-serif;box-shadow:0 10px 30px #0007;backdrop-filter:blur(4px)}
#eq-fen .eq-h{display:flex;align-items:center;gap:7px;padding:8px 10px}
#eq-fen .eq-h .eq-n{flex:1;color:#8b919c;font-size:11px}
#eq-fen .eq-h button{background:none;border:0;color:#8b919c;cursor:pointer;font-size:12px;padding:0 3px}
#eq-fen .eq-pt{width:8px;height:8px;border-radius:50%}
#eq-fen .eq-b{padding:0 10px 9px;display:grid;gap:7px;max-height:40vh;overflow:auto}
#eq-fen.repli .eq-b,#eq-fen.repli .eq-avec,#eq-fen.repli .eq-code,#eq-fen.repli [data-coul],#eq-fen.repli [data-r]{display:none}
#eq-fen.repli{width:auto}#eq-fen.repli .eq-h{padding:4px 8px;gap:5px}#eq-fen.repli .eq-n{flex:none}
#eq-fen .eq-h{cursor:move;user-select:none}
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
