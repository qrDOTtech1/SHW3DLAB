// PROJETS : tous les projets (Creation 3D, Keycaps, SHWork...). Chaque TYPE de projet declare son interface :
// onglet a ouvrir + exporter() / charger(donnees) / miniature(). Un nouveau type (ex. "voiture RC") n'a qu'a
// s'enregistrer dans TYPES pour avoir sa propre interface.
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const A = () => window.ATELIER;
const api = (u, b, m) => A().api(u, b, m);
const toast = m => A().toast(m);

export const TYPES = {
  creation3d: { nom: 'Creation 3D', onglet: 'c3d', icone: '&#9651;', module: () => window.__C3D },
  keycaps: { nom: 'Keycaps', onglet: 'kc', icone: '&#9000;', module: () => window.__KC },
  swork: { nom: 'SHWork (mecanique)', onglet: 'sw', icone: '&#9881;', module: () => window.__SW },
};
const P = { courant: {}, filtre: 'tous', liste: [] };
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
    TYPES[k] = { nom: m.nom, onglet: 'cfg', icone: '&#9670;', module: () => window.__CFG, modele: k };
    if (!document.querySelector(`[data-pj-creer="${k}"]`)) {
      const b = document.createElement('button'); b.className = 'primary'; b.dataset.pjCreer = k; b.innerHTML = `+ ${m.nom}`;
      document.querySelector('#tab-pj .pj-tete').appendChild(b); b.onclick = () => creer(k);
      const f = document.createElement('button'); f.dataset.pjFiltre = k; f.textContent = m.nom;
      document.querySelector('[data-pj-filtre="swork"]').after(f);
      f.onclick = () => { P.filtre = k; $$('[data-pj-filtre]').forEach(x => x.classList.toggle('on', x === f)); rafraichir(); };
    }
  }
}

async function rafraichir() {
  P.liste = await api('/api/projets');
  const l = P.liste.filter(p => P.filtre === 'tous' || p.type === P.filtre);
  $('#pj-grille').innerHTML = l.length ? l.map(p => {
    const t = TYPES[p.type] || { nom: p.type, icone: '?' };
    return `<div class="pj-carte" data-id="${p.id}">
      <div class="pj-mini">${p.miniature ? `<img src="/api/projets/${p.id}/miniature?t=${p.date}" alt="">` : `<span>${t.icone}</span>`}</div>
      <div class="pj-corps"><b>${p.nom}</b><span class="badge">${t.nom}</span>
        <p class="mute">${new Date((p.date || 0) * 1000).toLocaleString()}${p.description ? ' &middot; ' + p.description : ''}</p>
        <div class="pj-actions"><button class="primary" data-a="ouvrir">Ouvrir</button><button data-a="renommer">Renommer</button>
          <button data-a="dupliquer">Dupliquer</button><button data-a="supprimer">Corbeille</button></div></div></div>`;
  }).join('') : '<p class="mute">Aucun projet. Cree-en un, ou enregistre depuis Creation 3D / Keycaps / SHWork.</p>';
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

export async function ouvrir(id) {
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
$$('[data-pj-filtre]').forEach(b => b.onclick = () => { P.filtre = b.dataset.pjFiltre; $$('[data-pj-filtre]').forEach(x => x.classList.toggle('on', x === b)); rafraichir(); });
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
$$('[data-pj-creer]').forEach(b => b.onclick = () => creer(b.dataset.pjCreer));
document.addEventListener('click', e => { if (e.target.closest('[data-tab="pj"]')) rafraichir(); });
majTitres();

// boutons Enregistrer du configurateur (le type = le modele ouvert)
document.getElementById('cfg-enregistrer').onclick = () => window.__CFG?.modele && enregistrer(window.__CFG.modele);
document.getElementById('cfg-enregistrer-sous').onclick = () => window.__CFG?.modele && enregistrer(window.__CFG.modele, true);
document.getElementById('cfg-nouveau').onclick = () => window.__CFG?.modele && creer(window.__CFG.modele);
