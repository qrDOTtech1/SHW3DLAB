// PROJETS : tous les projets (Creation 3D, Keycaps, SHWork...). Chaque TYPE de projet declare son interface :
// onglet a ouvrir + exporter() / charger(donnees) / miniature(). Un nouveau type (ex. "voiture RC") n'a qu'a
// s'enregistrer dans TYPES pour avoir sa propre interface.
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const A = () => window.ATELIER;
const api = (u, b, m) => A().api(u, b, m);
const toast = m => A().toast(m);

export const TYPES = {
  creation3d: { nom: 'Creation 3D', famille: 'Creations 3D', onglet: 'c3d', icone: '&#9651;', module: () => window.__C3D },
  keycaps: { nom: 'Keycaps', famille: 'Keycaps', onglet: 'kc', icone: '&#9000;', module: () => window.__KC },
  swork: { nom: 'SHWork (mecanique)', famille: 'Pieces mecaniques', onglet: 'sw', icone: '&#9881;', module: () => window.__SW },
};
let _ferm = [];
try { _ferm = JSON.parse(localStorage.getItem('pj-fermees') || '[]'); } catch { }
const P = { courant: {}, liste: [], fermees: new Set(_ferm) };
// dialogue "Nouveau projet" : nom + base vide ou STL importe (carrosserie, piece existante...)
function dialogueNouveau(t) {
  return new Promise(resolve => {
    const f = document.createElement('div'); f.className = 'pj-dialogue';
    f.innerHTML = `<div class="boite"><b>Nouveau projet ${t.nom}</b>
      <label>Nom<input data-n value="nouveau projet"></label>
      <label class="chk"><input type="checkbox" data-stl> Partir d'un fichier STL / OBJ / 3MF (base du projet)</label>
      <input type="file" data-f accept=".stl,.obj,.3mf,.ply" hidden>
      <p class="mute" data-aide hidden>Le fichier est importe tel quel comme BASE (reference) : on pourra ensuite le decouper, le modifier, construire autour.</p>
      <div class="pied"><button data-r="0">Annuler</button><button class="primary" data-r="1">Creer</button></div></div>`;
    document.body.appendChild(f);
    const cb = f.querySelector('[data-stl]'), fi = f.querySelector('[data-f]');
    cb.onchange = () => { fi.hidden = !cb.checked; f.querySelector('[data-aide]').hidden = !cb.checked; if (cb.checked) fi.click(); };
    f.querySelector('[data-n]').select();
    const fin = v => { f.remove(); resolve(v); };
    f.querySelector('[data-r="0"]').onclick = () => fin(null);
    f.querySelector('[data-r="1"]').onclick = () => {
      const nom = f.querySelector('[data-n]').value.trim(); if (!nom) return;
      fin({ nom, fichier: cb.checked ? fi.files[0] || null : null });
    };
    f.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Escape') fin(null); });
  });
}
async function importerBase(file) {
  if (!file) return null;
  if (file.size > 80e6) { toast('Fichier trop lourd (80 Mo max)'); return null; }
  const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(file); });
  toast(`Import de ${file.name}...`);
  return await api('/api/c3d/importer', { data, nom: file.name.replace(/[^\w\- .()]/g, '_') });
}

// petite fenetre de dialogue integree (pas de prompt / confirm du navigateur)
function dialogue(titre, { texte = null, message = '', ok = 'OK' } = {}) {
  return new Promise(resolve => {
    const f = document.createElement('div'); f.className = 'pj-dialogue';
    f.innerHTML = `<div class="boite"><b>${titre}</b>${message ? `<p class="mute">${message}</p>` : ''}
      ${texte !== null ? `<input value="${String(texte).replace(/"/g, '&quot;')}">` : ''}
      <div class="pied"><button data-r="0">Annuler</button><button class="primary" data-r="1">${ok}</button></div></div>`;
    document.body.appendChild(f);
    const i = f.querySelector('input'); i?.focus(); i?.select();
    const fin = v => { f.remove(); resolve(v); };
    f.querySelector('[data-r="0"]').onclick = () => fin(null);
    f.querySelector('[data-r="1"]').onclick = () => fin(texte !== null ? i.value.trim() || null : true);
    f.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter') f.querySelector('[data-r="1"]').click(); if (e.key === 'Escape') fin(null); });
  });
}       // courant[type] = { id, nom }
window.__PROJETS = { TYPES, P, enregistrer, ouvrir, enregistrerModeles };
function enregistrerModeles(modeles) {
  for (const [k, m] of Object.entries(modeles)) {
    TYPES[k] = { nom: m.nom, famille: m.famille || m.nom, version: m.version || '', archive: !!m.archive,
                 onglet: 'cfg', icone: m.icone || '&#9670;', module: () => window.__CFG, modele: k };
  }
  menuNouveau();
}
// menu "+ Nouveau projet" : types classes par famille (les versions archivees n'y figurent pas)
function menuNouveau() {
  const fam = {};
  for (const [k, t] of Object.entries(TYPES)) if (!t.archive) (fam[t.famille] = fam[t.famille] || []).push([k, t]);
  $('#pj-menu').innerHTML = Object.entries(fam).sort().map(([f, l]) => `<h4>${f}</h4>` +
    l.map(([k, t]) => `<button data-nouveau="${k}"><span style="color:#ff6410">${t.icone}</span> ${t.nom}${t.version ? ' <small class="mute">v' + t.version + '</small>' : ''}</button>`).join('')).join('');
  $$('#pj-menu [data-nouveau]').forEach(b => b.onclick = () => { $('#pj-menu').hidden = true; creer(b.dataset.nouveau); });
}
$('#pj-nouveau').onclick = e => { e.stopPropagation(); $('#pj-menu').hidden = !$('#pj-menu').hidden; };
document.addEventListener('click', e => { if (!e.target.closest('.pj-nouveau')) $('#pj-menu').hidden = true; });
['#pj-cherche', '#pj-tri', '#pj-archives'].forEach(s_ => $(s_).addEventListener('input', () => afficher()));

async function rafraichir() {
  P.liste = await api('/api/projets');
  afficher();
}
const vnum = v => String(v || '0').split('.').map(Number).reduce((a, x, i) => a + x / Math.pow(1000, i), 0);
function afficher() {
  const q = $('#pj-cherche').value.trim().toLowerCase(), tri = $('#pj-tri').value, archives = $('#pj-archives').checked;
  const fam = {};
  for (const p of P.liste) {
    const t = TYPES[p.type] || { nom: p.type, famille: 'Autres', icone: '?' };
    if (t.archive && !archives) continue;
    const texte = `${p.nom} ${t.nom} ${t.famille} ${p.description || ''} v${t.version || ''}`.toLowerCase();
    if (q && !texte.includes(q)) continue;
    (fam[t.famille] = fam[t.famille] || { icone: t.icone, l: [] }).l.push({ p, t });
  }
  const recent = g => Math.max(...g.l.map(x => x.p.date || 0));
  const ordre = Object.entries(fam).sort((a, b) => recent(b[1]) - recent(a[1]));
  if (!ordre.length) {
    $('#pj-grille').innerHTML = `<p class="mute">${P.liste.length ? 'Aucun projet ne correspond.' : 'Aucun projet : "+ Nouveau projet" pour commencer.'}</p>`;
    return;
  }
  $('#pj-grille').innerHTML = ordre.map(([f, g]) => {
    g.l.sort((a, b) => tri === 'nom' ? a.p.nom.localeCompare(b.p.nom) : tri === 'version'
      ? (vnum(b.t.version) - vnum(a.t.version)) || ((b.p.date || 0) - (a.p.date || 0))
      : ((a.t.archive - b.t.archive) || ((b.p.date || 0) - (a.p.date || 0))));
    const vmax = Math.max(0, ...g.l.filter(x => !x.t.archive && x.t.version).map(x => vnum(x.t.version)));
    return `<section class="pj-famille ${P.fermees.has(f) && !q ? 'ferme' : ''}" data-famille="${f}">
      <header><span class="ic">${g.icone}</span><h3>${f}</h3><span class="nb">${g.l.length} projet${g.l.length > 1 ? 's' : ''}</span><span class="chev">&#9662;</span></header>
      <div class="pj-grille-f">${g.l.map(({ p, t }) => carte(p, t, t.version && vnum(t.version) === vmax && !t.archive && g.l.length > 1)).join('')}</div></section>`;
  }).join('');
  $$('.pj-famille > header').forEach(h => h.onclick = () => {
    const f = h.parentElement.dataset.famille;
    if (P.fermees.has(f)) P.fermees.delete(f); else P.fermees.add(f);
    try { localStorage.setItem('pj-fermees', JSON.stringify([...P.fermees])); } catch { }
    h.parentElement.classList.toggle('ferme');
  });
  $$('.pj-carte [data-a]').forEach(b => b.onclick = async () => {
    const id = b.closest('.pj-carte').dataset.id, p = P.liste.find(x => x.id === id), a = b.dataset.a;
    if (a === 'ouvrir') return ouvrir(id);
    if (a === 'dupliquer') { await api(`/api/projets/${id}/dupliquer`, {}); return rafraichir(); }
    if (a === 'renommer') {
      const nom = await dialogue('Renommer le projet', { texte: p.nom, ok: 'Renommer' }); if (!nom) return;
      const d = await api('/api/projets/' + id); await api('/api/projets', { ...d, nom }); return rafraichir();
    }
    if (a === 'supprimer') {
      if (!await dialogue(`Mettre "${p.nom}" a la corbeille ?`, { message: 'Recuperable dans data/projets/corbeille.', ok: 'Corbeille' })) return;
      await api('/api/projets/' + id, undefined, 'DELETE'); toast('Projet mis a la corbeille'); rafraichir();
    }
  });
}
function carte(p, t, derniere) {
  return `<div class="pj-carte ${t.archive ? 'archive' : ''}" data-id="${p.id}">
    <div class="pj-mini">${p.miniature ? `<img src="/api/projets/${p.id}/miniature?t=${p.date}" alt="">` : `<span>${t.icone}</span>`}</div>
    <div class="pj-corps"><b>${p.nom}${t.version ? `<span class="ver">v${t.version}</span>` : ''}</b>
      ${derniere ? '<span class="derniere">Derniere version</span>' : t.archive ? '<span class="mute" style="font-size:11px">Archive</span>' : ''}
      <p class="mute">${new Date((p.date || 0) * 1000).toLocaleString()}${p.description ? ' &middot; ' + p.description : ''}</p>
      <div class="pj-actions"><button class="primary" data-a="ouvrir">Ouvrir</button><button data-a="renommer">Renommer</button>
        <button data-a="dupliquer">Dupliquer</button><button data-a="supprimer">Corbeille</button></div></div></div>`;
}

export async function ouvrir(id) {
  const p_ = P.liste.find(x => x.id === id);
  const ch = window.SHWCharge?.debut(`Ouverture de ${p_?.nom || 'projet'}`, { cle: 'ouvrir-' + (p_?.type || '') });
  try { return await _ouvrir(id); } finally { ch?.fin(); }
}
async function _ouvrir(id) {
  const d = await api('/api/projets/' + id), t = TYPES[d.type];
  if (!t) return toast(`Type de projet inconnu : ${d.type}`);
  $(`[data-tab="${t.onglet}"]`).click();
  await new Promise(r => setTimeout(r, 60));
  const m = t.module();
  if (!m?.charger) return toast('Interface du projet indisponible');
  await m.charger(t.modele ? { modele: t.modele, ...(d.donnees || {}) } : (d.donnees || {}));
  if (t.modele) window.__CFG.projet = { id: d.id, nom: d.nom };
  P.courant[d.type] = { id: d.id, nom: d.nom };
  majTitres();
  window.dispatchEvent(new CustomEvent('shw:projet', { detail: { id: d.id, nom: d.nom } }));   // mode equipe
  toast(`Projet "${d.nom}" ouvert`);
}

export async function enregistrer(type, sousNom = false) {
  const t = TYPES[type], m = t.module(); if (!m?.exporter) return;
  let cur = P.courant[type];
  if (!cur || sousNom) {
    const nom = await dialogue(`Enregistrer le projet ${t.nom}`, { texte: cur?.nom || 'mon projet', ok: 'Enregistrer' }); if (!nom) return;
    cur = { id: '', nom };
  }
  let miniature = '';
  try { miniature = m.miniature?.() || ''; } catch { }
  const r = await api('/api/projets', { id: cur.id, nom: cur.nom, type, donnees: m.exporter(), miniature });
  P.courant[type] = { id: r.id, nom: cur.nom }; majTitres();
  toast(`Projet "${cur.nom}" enregistre`);
  if ($('#tab-pj').classList.contains('on')) rafraichir();
}
function majTitres() {
  const zc = $('[data-pj-titre="__cfg"]'), mc = window.__CFG?.modele;
  if (zc && mc) zc.textContent = P.courant[mc] ? `Projet : ${P.courant[mc].nom}` : 'Projet non enregistre';
  for (const [type, t] of Object.entries(TYPES)) {
    const z = $(`[data-pj-titre="${type}"]`); if (z) z.textContent = P.courant[type] ? `Projet : ${P.courant[type].nom}` : 'Projet non enregistre';
  }
}

// boutons "Enregistrer / Enregistrer sous / Nouveau" presents dans chaque onglet
$$('[data-pj-save]').forEach(b => b.onclick = () => enregistrer(b.dataset.pjSave, b.dataset.sous === '1'));
$$('[data-pj-new]').forEach(b => b.onclick = () => creer(b.dataset.pjNew));
async function creer(type) {
  const t = TYPES[type];
  const choix = await dialogueNouveau(t); if (!choix) return;
  const base = await importerBase(choix.fichier);
  if (t.modele) await window.__CFG.ouvrirModele(t.modele, {});
  else { $(`[data-tab="${t.onglet}"]`).click(); await new Promise(r => setTimeout(r, 60)); await t.module()?.vider?.(); }
  if (base) await t.module()?.baseImportee?.(base, choix.fichier.name);
  const r = await api('/api/projets', { nom: choix.nom, type, donnees: t.module()?.exporter?.() || {}, miniature: t.module()?.miniature?.() || '',
    description: base ? `base : ${choix.fichier.name}` : '' });
  P.courant[type] = { id: r.id, nom: choix.nom }; if (t.modele) window.__CFG.projet = { id: r.id, nom: choix.nom };
  majTitres(); toast(`Projet "${choix.nom}" cree` + (base ? ` a partir de ${choix.fichier.name}` : ''));
}
window.__PROJETS.creer = creer;
menuNouveau();
document.addEventListener('click', e => { if (e.target.closest('[data-tab="pj"]')) rafraichir(); });
majTitres();

// boutons Enregistrer du configurateur (le type = le modele ouvert)
document.getElementById('cfg-enregistrer').onclick = () => window.__CFG?.modele && enregistrer(window.__CFG.modele);
document.getElementById('cfg-enregistrer-sous').onclick = () => window.__CFG?.modele && enregistrer(window.__CFG.modele, true);
document.getElementById('cfg-nouveau').onclick = () => window.__CFG?.modele && creer(window.__CFG.modele);

// ---------------------------------------------------------------- SYNCHRO des projets entre postes (GitHub)
function etatSynchro(e) {
  const el = $('#pj-synchro-etat'); if (!el || !e) return;
  const quand = e.derniere ? new Date(e.derniere * 1000).toLocaleTimeString().slice(0, 5) : '';
  el.textContent = e.ok === null ? '' : (e.ok ? `synchro ${quand}` + (e.recus ? ` · ${e.recus} recu(s)` : '') : `⚠ ${e.message}`);
  el.style.color = e.ok === false ? '#ff5a4f' : '#8b919c';
}
let _vueSynchro = 0;
async function surveillerSynchro() {
  try {
    const e = await (await fetch('/api/synchro')).json(); etatSynchro(e);
    if (e.derniere && e.derniere !== _vueSynchro) { if (_vueSynchro && e.recus) rafraichir(); _vueSynchro = e.derniere; }
  } catch { }
}
$('#pj-synchro')?.addEventListener('click', async () => {
  const b = $('#pj-synchro'); b.disabled = true; $('#pj-synchro-etat').textContent = 'synchro...';
  try { const e = await (await fetch('/api/synchro', { method: 'POST' })).json(); etatSynchro(e); _vueSynchro = e.derniere; await rafraichir(); }
  finally { b.disabled = false; }
});
surveillerSynchro(); setInterval(surveillerSynchro, 20000);

window.SHWOuvrirProjet = id => _ouvrir(id);              // bouton "Suivre" du mode equipe
