// ONGLET KEYCAPS : conception de touches (profils, tailles libres, tiges) + legendes / logos + jeux complets.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const A = () => window.ATELIER;
const api = (u, b) => A().api(u, b);
const toast = m => A().toast(m);

const K = { opts: null, image: '', geo: {}, dernier: null };
window.__KC = K;

// ------------------------------------------------------------------ scene
const el = $('#kc-view');
const ren = new THREE.WebGLRenderer({ antialias: true, alpha: true });
ren.setPixelRatio(Math.min(devicePixelRatio, 2)); ren.shadowMap.enabled = true; el.appendChild(ren.domElement);
const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(32, 1, 0.5, 2000); cam.up.set(0, 0, 1); cam.position.set(0, -70, 60);
const orb = new OrbitControls(cam, ren.domElement); orb.enableDamping = true; orb.target.set(0, 0, 4);
scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.5));
const sun = new THREE.DirectionalLight(0xffffff, 2.2); sun.position.set(-40, -60, 120); sun.castShadow = true; scene.add(sun);
const sol = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.ShadowMaterial({ opacity: 0.3 })); sol.receiveShadow = true; scene.add(sol);
const grille = new THREE.GridHelper(200, 40, 0x3a4250, 0x232934); grille.rotation.x = Math.PI / 2; scene.add(grille);
const groupe = new THREE.Group(); scene.add(groupe);
function taille() { const w = el.clientWidth, h = el.clientHeight; if (!w) return; ren.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix(); }
new ResizeObserver(taille).observe(el);
(function boucle() { requestAnimationFrame(boucle); orb.update(); ren.render(scene, cam); })();
const loader = new STLLoader();
const charger = f => K.geo[f] || (K.geo[f] = new Promise((ok, ko) => loader.load(`/c3d/${f}.stl`, g => { g.computeVertexNormals(); ok(g); }, undefined, ko)));
const couleur = id => A().bobine(id)?.couleur || '#e8e3d8';

// ------------------------------------------------------------------ parametres
const v = id => $('#kc-' + id);
const num = id => { const x = v(id).value; return x === '' ? null : +x; };
function params() {
  const libre = v('libre').checked;
  const p = {
    profil: v('profil').value, rang: +v('rang').value, tige: v('tige').value, jeu: num('jeu'),
    u_x: libre ? 1 : +v('ux').value, u_y: libre ? 1 : +v('uy').value, pas: num('pas'), ecart: num('ecart'),
    l_mm: libre ? num('l') : null, w_mm: libre ? num('w') : null,
    h_avant: num('hav'), h_arriere: num('har'), haut_l: num('hl'), haut_w: num('hw'), decal_haut: num('dech'),
    rayon_bas: num('rb'), rayon_haut: num('rh'), paroi: num('paroi'), creux: num('creux'), dish: v('dish').value || null,
    repere: v('repere').value, nervures: v('nerv').checked,
    type_legende: v('leg').value, texte: v('texte').value, police: v('police').value, taille_legende: +v('tl').value,
    rotation: +v('rot').value, dx: +v('dx').value, dy: +v('dy').value, face: v('face').value,
    mode_legende: v('mode').value, profondeur_legende: +v('prof').value, jeu_legende: +v('jeul').value,
    seuil: +v('seuil').value || null, inverser: v('inv').checked || null,
    texture: v('texture').value || null, texture_prof: num('texture_prof'), texture_taille: num('texture_taille'),
    ajour: v('ajour').value || null, ajour_taille: num('ajour_taille'), ajour_trait: num('ajour_trait'),
  };
  for (const k of Object.keys(p)) if (p[k] === null || Number.isNaN(p[k])) delete p[k];
  return p;
}
function majInfoProfil() {
  const pr = K.opts.profils[v('profil').value]; if (!pr) return;
  const [av, ar] = pr.rangs[v('rang').value] || Object.values(pr.rangs)[0];
  v('hav').placeholder = av; v('har').placeholder = ar; v('creux').placeholder = pr.creux;
  v('hl').placeholder = '(auto)'; v('hw').placeholder = '(auto)';
  $('#kc-libre-zone').hidden = !v('libre').checked; $('#kc-u-zone').hidden = v('libre').checked;
  $('#kc-leg-texte').hidden = v('leg').value !== 'texte'; $('#kc-leg-logo').hidden = v('leg').value !== 'logo';
  $('#kc-leg-opts').hidden = v('leg').value === 'aucune';
  $$('.kc-v').forEach(b => { const i = b.dataset.for && $('#kc-' + b.dataset.for); if (i) b.textContent = i.value; });
}

// ------------------------------------------------------------------ apercu en direct
let _t = null, _n = 0;
function apercu() { majInfoProfil(); clearTimeout(_t); _t = setTimeout(generer, 350); }
async function generer() {
  const n = ++_n;
  $('#kc-etat').textContent = 'Calcul...';
  try {
    const r = await api('/api/kc/touche', { params: params(), image: K.image });
    if (n !== _n) return;
    groupe.clear();
    for (const o of r.objets) {
      const g = await charger(o.fichier);
      const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: couleur(o.role === 'legende' ? v('bob-leg').value : v('bob-touche').value), roughness: 0.45 }));
      m.castShadow = true; m.receiveShadow = true;
      if (o.role === 'legende' && v('eclate').checked) m.position.z += 14;
      groupe.add(m);
    }
    K.dernier = r;
    const i = r.info, a = r.objets[0].analyse;
    $('#kc-etat').innerHTML = `<b>${i.profil}</b> R${i.rang} &middot; ${i.dimensions_mm.join(' x ')} mm &middot; dessus ${i.haut_mm.join(' x ')} &middot; ${i.tige}`
      + `${i.stabilisateurs.length ? ` &middot; stabs a &plusmn;${Math.abs(i.stabilisateurs[0])} mm` : ''} &middot; ${a.poids_g} g`;
  } catch (e) { if (n === _n) $('#kc-etat').textContent = e.message; }
}
$$('#tab-kc input, #tab-kc select').forEach(i => i.addEventListener('input', () => { if (!i.closest('#kc-jeu-zone')) apercu(); }));
const TEXTURES = { alveoles: 'Nid d\'abeille', hexa_bombe: 'Hexagones bombes', voronoi: 'Cellules', pierre: 'Pierre', diamant: 'Moletage diamant', rainures: 'Rainures', vagues: 'Vagues', tressage: 'Tressage', picots: 'Picots', cuir: 'Cuir', bruit: 'Granuleux', ecailles: 'Ecailles', bois: 'Bois' };
const AJOURS = { alveoles: 'Nid d\'abeille', cercles: 'Cercles', gaufre: 'Grille', triangles: 'Triangles', voronoi: 'Cellules', fentes: 'Fentes', diamant: 'Losanges' };

$$('.kc-vue').forEach(b => b.onclick = () => {
  const d = { dessus: [0, -0.01, 90], face: [0, -90, 8], iso: [-45, -70, 55] }[b.dataset.v]; cam.position.set(...d); orb.target.set(0, 0, 4); orb.update();
});
v('logo').onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(f); });
  K.image = (await api('/api/image', { data })).id; toast('Logo charge'); apercu();
};

$('#kc-vers-c3d').onclick = async () => {
  if (!K.dernier) return;
  for (const o of K.dernier.objets) await window.__C3D?._ajout?.(o, o.role === 'legende' ? v('bob-leg').value : v('bob-touche').value);
  toast('Touche ajoutee dans Creation 3D'); $('[data-tab="c3d"]').click();
};

// ------------------------------------------------------------------ LOT (plusieurs touches differentes, plusieurs claviers)
K.lot = [];
K.edition = null;                       // id de l'element du lot en cours de modification
const RANGEES = {
  azerty_lettres: 'AZERTYUIOPQSDFGHJKLMWXCVBN'.split('').map(t => ({ texte: t, rang: 'AZERTYUIOP'.includes(t) ? 2 : 'QSDFGHJKLM'.includes(t) ? 3 : 4, repere: 'FJ'.includes(t) ? 'barre' : 'aucun' })),
  chiffres: '1234567890'.split('').map(t => ({ texte: t, rang: 1 })),
  modificateurs: [['Esc', 1, 1], ['Tab', 1.5, 2], ['Verr', 1.75, 3], ['Maj', 2.25, 4], ['Ctrl', 1.25, 4], ['Alt', 1.25, 4], ['Entree', 2.25, 3], ['Retour', 2, 1], ['Espace', 6.25, 4], ['AltGr', 1.25, 4]].map(([texte, u, rang]) => ({ texte, u, rang })),
  fleches: ['↑', '←', '↓', '→'].map(t => ({ texte: t, rang: 4 })),
  pave: [['7', 1, 2], ['8', 1, 2], ['9', 1, 2], ['4', 1, 3], ['5', 1, 3, 'point'], ['6', 1, 3], ['1', 1, 4], ['2', 1, 4], ['3', 1, 4], ['0', 2, 4], ['.', 1, 4], ['+', 1, 3], ['-', 1, 1], ['*', 1, 1], ['/', 1, 1]].map(([texte, u, rang, repere]) => ({ texte, u, rang, repere })),
  f: Array.from({ length: 12 }, (_, i) => ({ texte: 'F' + (i + 1), rang: 1 })),
  macro: Array.from({ length: 9 }, (_, i) => ({ texte: 'M' + (i + 1), rang: 3 })),
};
const champs = () => K.exporter().champs;
function appliquerChamps(c) { for (const [id, val] of Object.entries(c)) { const i = document.getElementById(id); if (!i || id.startsWith('kc-clavier') || id === 'kc-qte') continue; if (i.type === 'checkbox') i.checked = val; else i.value = val; } }
const resume = c => {
  const pr = K.opts?.profils[c['kc-profil']]?.nom?.split(' ')[0] || c['kc-profil'];
  const taille = c['kc-libre'] ? `${c['kc-l']}x${c['kc-w']} mm` : `${c['kc-ux']}u`;
  const leg = c['kc-leg'] === 'aucune' ? 'vierge' : c['kc-leg'] === 'logo' ? 'logo' : `"${c['kc-texte']}"`;
  const extra = [c['kc-mode'] === 'percer' || c['kc-mode'] === 'translucide' ? 'RGB' : '', c['kc-texture'] ? 'texture' : '', c['kc-ajour'] ? 'ajoure' : ''].filter(Boolean).join(' ');
  return `${leg} &middot; ${pr} R${c['kc-rang']} &middot; ${taille}${extra ? ' &middot; ' + extra : ''}`;
};
async function miniatureActuelle() { await new Promise(r => setTimeout(r, 60)); return K.miniature(); }
async function ajouterAuLot(c = champs(), image = K.image, mini = null) {
  K.lot.push({ id: 'k' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), clavier: v('clavier').value.trim() || 'Mon clavier',
    qte: Math.max(1, +v('qte').value || 1), champs: c, image, mini: mini || await miniatureActuelle() });
  rendreLot(); sauverLot();
}
function rendreLot() {
  const groupes = {};
  for (const it of K.lot) (groupes[it.clavier] ||= []).push(it);
  $('#kc-claviers').innerHTML = Object.keys(groupes).map(g => `<option value="${g}">`).join('');
  $('#kc-lot').innerHTML = Object.entries(groupes).map(([g, l]) => `<div class="kc-groupe"><div class="kc-gtete"><b>${g}</b>
      <span class="mute">${l.reduce((a, x) => a + x.qte, 0)} touche(s)</span><button data-g-suppr="${g}" title="Retirer ce clavier du lot">&#10005;</button></div>
    ${l.map(it => `<div class="kc-item ${K.edition === it.id ? 'edit' : ''}" data-id="${it.id}"><img src="${it.mini}" alt="">
      <div class="t">${resume(it.champs)}</div>
      <div class="q"><button data-a="moins">-</button><b>${it.qte}</b><button data-a="plus">+</button></div>
      <div class="a"><button data-a="editer" title="Modifier">&#9998;</button><button data-a="dupliquer" title="Dupliquer">&#10697;</button><button data-a="stl" title="Exporter cette touche en STL">STL</button><button data-a="suppr" title="Retirer">&#10005;</button></div></div>`).join('')}</div>`).join('')
    || '<p class="mute">Lot vide : regle une touche puis "+ Ajouter au lot". Tu peux melanger profils, tailles, couleurs et claviers.</p>';
  const tot = K.lot.reduce((a, x) => a + x.qte, 0);
  $('#kc-nb').textContent = tot ? `${tot} touche(s), ${Object.keys(groupes).length} clavier(s)` : '';
  $$('#kc-lot [data-a]').forEach(b => b.onclick = async () => {
    const id = b.closest('.kc-item').dataset.id, it = K.lot.find(x => x.id === id), a = b.dataset.a;
    if (a === 'plus') it.qte++;
    if (a === 'moins') it.qte = Math.max(1, it.qte - 1);
    if (a === 'suppr') K.lot = K.lot.filter(x => x !== it);
    if (a === 'dupliquer') K.lot.splice(K.lot.indexOf(it) + 1, 0, { ...it, id: it.id + 'd' + Date.now().toString(36), champs: { ...it.champs } });
    if (a === 'editer') { K.edition = id; appliquerChamps(it.champs); K.image = it.image; v('clavier').value = it.clavier; $('#kc-maj').disabled = false; apercu(); }
    if (a === 'stl') return exporter([it]);
    rendreLot(); sauverLot();
  });
  $$('[data-g-suppr]').forEach(b => b.onclick = () => { K.lot = K.lot.filter(x => x.clavier !== b.dataset.gSuppr); rendreLot(); sauverLot(); });
}
const versServeur = l => l.map(it => {
  const avant = champs(); appliquerChamps(it.champs); const p = params(); appliquerChamps(avant);
  return { nom: it.champs['kc-texte'] || 'touche', clavier: it.clavier, qte: it.qte, params: p, image: it.image };
});
async function exporter(l) {
  try {
    const { job } = await api('/api/kc/lot/export', { items: versServeur(l) });
    await A().suivre(job, '#kc-prog', r => { const a = document.createElement('a'); a.href = r.zip; a.download = 'keycaps.zip'; a.click(); toast(`${r.fichiers} fichier(s) STL exporte(s)`); });
  } catch (e) { toast(e.message); }
}
$('#kc-ajouter').onclick = () => ajouterAuLot();
$('#kc-maj').onclick = async () => {
  const it = K.lot.find(x => x.id === K.edition); if (!it) return;
  it.champs = champs(); it.image = K.image; it.clavier = v('clavier').value.trim() || it.clavier; it.mini = await miniatureActuelle();
  K.edition = null; $('#kc-maj').disabled = true; rendreLot(); sauverLot(); toast('Touche mise a jour');
};
v('rangee').onchange = async e => {
  const r = RANGEES[e.target.value]; e.target.value = ''; if (!r) return;
  const base = champs();
  for (const t of r) {
    const c = { ...base, 'kc-texte': t.texte, 'kc-leg': base['kc-leg'] === 'aucune' ? 'texte' : base['kc-leg'] };
    if (t.u) { c['kc-ux'] = String(t.u); c['kc-libre'] = false; }
    if (t.rang) c['kc-rang'] = String(t.rang);
    if (t.repere) c['kc-repere'] = t.repere;
    await ajouterAuLot(c, K.image, null);
  }
  toast(`${r.length} touches ajoutees au lot`);
};
$('#kc-export-lot').onclick = () => K.lot.length ? exporter(K.lot) : toast('Lot vide');
$('#kc-vider-lot').onclick = () => { if (K.lot.length) { K.lot = []; K.edition = null; rendreLot(); sauverLot(); } };
$('#kc-btn-jeu').onclick = async () => {
  if (!K.lot.length) return toast('Lot vide : ajoute des touches');
  try {
    const { job } = await api('/api/kc/lot/imprimer', { items: versServeur(K.lot), bobines: { touche: v('bob-touche').value, legende: v('bob-leg').value } });
    await A().suivre(job, '#kc-prog', res => {
      const S = A().S; S.gen = res; S.tranches = {}; A().renderPlateauxImp();
      toast(`${K.lot.reduce((a, x) => a + x.qte, 0)} touches sur ${res.plateaux.length} plateau(x) : onglet Imprimer`); $('[data-tab="imprimer"]').click();
    });
  } catch (e) { toast(e.message); }
};
$('#kc-stl').onclick = () => exporter([{ clavier: 'touche', qte: 1, champs: champs(), image: K.image }]);
function sauverLot() { try { localStorage.setItem('kc_lot', JSON.stringify(K.lot)); } catch { } }
try { K.lot = JSON.parse(localStorage.getItem('kc_lot') || '[]'); } catch { K.lot = []; }
// legende RGB : position au nord (au-dessus de la LED des switchs) par defaut
v('mode').addEventListener('change', () => { if (['percer', 'translucide'].includes(v('mode').value) && +v('dy').value === 0) { v('dy').value = 4; apercu(); } });

// ------------------------------------------------------------------ projets
const champsKC = () => $$('#tab-kc input:not([type=file]), #tab-kc select, #tab-kc textarea').filter(i => i.id);
let defauts = null;
K.exporter = () => ({ champs: Object.fromEntries(champsKC().filter(i => !['kc-clavier', 'kc-qte', 'kc-rangee'].includes(i.id)).map(i => [i.id, i.type === 'checkbox' ? i.checked : i.value])), image: K.image, lot: K.lot });
K.charger = async d => {
  for (const [id, v] of Object.entries(d.champs || {})) { const i = document.getElementById(id); if (!i) continue; if (i.type === 'checkbox') i.checked = v; else i.value = v; }
  K.image = d.image || ''; if (d.lot) { K.lot = d.lot; rendreLot(); } apercu();
};
K.vider = async () => { if (defauts) await K.charger({ champs: defauts, image: '', lot: [] }); };
K.miniature = () => { orb.update(); ren.render(scene, cam); const c = document.createElement('canvas'); c.width = 320; c.height = 220; c.getContext('2d').drawImage(ren.domElement, 0, 0, 320, 220); return c.toDataURL('image/png'); };

// ------------------------------------------------------------------ demarrage
(async function init() {
  for (let i = 0; i < 600 && !(A()?.S?.polices && A()?.S?.etat); i++) await new Promise(r => setTimeout(r, 100));   // serveur occupe : jusqu'a 60 s
  if (!A()?.S?.polices || !A()?.S?.etat) return toast?.('Keycaps : serveur trop lent, recharge la page');
  K.opts = await api('/api/kc/options');
  v('profil').innerHTML = Object.entries(K.opts.profils).map(([k, p]) => `<option value="${k}">${p.nom}</option>`).join('');
  v('tige').innerHTML = Object.entries(K.opts.tiges).map(([k, n]) => `<option value="${k}">${n}</option>`).join('');
  v('police').innerHTML = Object.entries(A().S.polices).map(([k, p]) => `<option value="${k}">${p.label}</option>`).join('');
  const bobs = A().S.etat.bobines.map(b => `<option value="${b.id}">${b.nom}</option>`).join('');
  v('bob-touche').innerHTML = bobs; v('bob-leg').innerHTML = bobs;
  v('texture').innerHTML += Object.entries(TEXTURES).map(([k, n]) => `<option value="${k}">${n}</option>`).join('');
  v('ajour').innerHTML += Object.entries(AJOURS).map(([k, n]) => `<option value="${k}">${n}</option>`).join('');
  const bl = A().S.etat.bobines.find(b => /blanc|white/i.test(b.nom)), no = A().S.etat.bobines.find(b => /noir|black/i.test(b.nom));
  if (bl) v('bob-touche').value = bl.id; if (no) v('bob-leg').value = no.id;
  rendreLot(); majInfoProfil(); taille(); generer();
  defauts = K.exporter().champs;
  document.addEventListener('click', e => { if (e.target.closest('[data-tab="kc"]')) setTimeout(taille, 30); });
})();
