// SHWORK : conception mecanique (bibliotheque parametrique, assemblage, animation des engrenages, nomenclature).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const A = () => window.ATELIER;
const api = (u, b) => A().api(u, b);
const toast = m => A().toast(m);
const r2 = v => Math.round(v * 100) / 100;

const W = { cat: null, pieces: [], sel: null, geo: {}, anim: false, idn: 1, projet: null };
window.__SW = W;

// ------------------------------------------------------------------ scene
const el = $('#sw-view');
const ren = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
ren.setPixelRatio(Math.min(devicePixelRatio, 2)); ren.shadowMap.enabled = true; el.appendChild(ren.domElement);
const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(36, 1, 0.5, 5000); cam.up.set(0, 0, 1); cam.position.set(-80, -180, 150);
const orb = new OrbitControls(cam, ren.domElement); orb.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.5));
const sun = new THREE.DirectionalLight(0xffffff, 2.1); sun.position.set(-150, -200, 400); sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -250, right: 250, top: 250, bottom: -250 }); scene.add(sun);
const plaque = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.MeshStandardMaterial({ color: 0x1b2230, roughness: 0.9 }));
plaque.receiveShadow = true; plaque.position.z = -0.05; scene.add(plaque);
const grille = new THREE.GridHelper(400, 40, 0x3d4a5e, 0x283141); grille.rotation.x = Math.PI / 2; scene.add(grille);
window.addEventListener('theme', e => plaque.material.color.setHex(e.detail === 'light' ? 0xe4e8ef : 0x1b2230));
if (document.documentElement.dataset.scene === 'light') plaque.material.color.setHex(0xe4e8ef);
const tc = new TransformControls(cam, ren.domElement);
tc.addEventListener('dragging-changed', e => { orb.enabled = !e.value; if (!e.value) majNomenclature(); });
scene.add(tc);
function taille() { const w = el.clientWidth, h = el.clientHeight; if (!w) return; ren.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix(); }
new ResizeObserver(taille).observe(el);
let t0 = performance.now();
(function boucle(t) {
  requestAnimationFrame(boucle);
  const dt = (t - t0) / 1000; t0 = t;
  if (W.anim) animer(dt || 0);
  orb.update(); ren.render(scene, cam);
})(performance.now());
const loader = new STLLoader();
const charger = f => W.geo[f] || (W.geo[f] = new Promise((ok, ko) => loader.load(`/c3d/${f}.stl`, g => { g.computeVertexNormals(); ok(g); }, undefined, ko)));
const couleur = id => A().bobine(id)?.couleur || '#d9822b';
const PALETTE = [0xd9822b, 0x5fb3a1, 0x6c8ebf, 0xc9a227, 0xb5607a, 0x8fa35b];

// ------------------------------------------------------------------ pieces
// piece = { id, nom, type, params, groupe(THREE.Group), maillages[], info, bobine }
async function construire(piece) {
  const r = await api('/api/meca/piece', { nom: piece.type, params: piece.params });
  piece.info = r.info; piece.objets = r.objets;
  const g = piece.groupe || new THREE.Group();
  g.clear();
  for (const [i, o] of r.objets.entries()) {
    const geo = await charger(o.fichier);
    const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: piece.couleur ?? PALETTE[(W.idn + i) % PALETTE.length], roughness: 0.45, metalness: 0.08 }));
    m.castShadow = true; m.receiveShadow = true; m.userData.piece = piece; m.userData.k = i;
    // pivot de rotation des engrenages (animation) : centre de l'axe declare par le generateur
    const an = r.info.animation?.find(a => a.piece === i);
    if (an) { const pv = new THREE.Group(); pv.position.set(an.axe[0], an.axe[1], 0); m.position.set(-an.axe[0], -an.axe[1], 0); pv.add(m); pv.userData.vitesse = an.vitesse; g.add(pv); }
    else if (piece.type === 'engrenage') { const pv = new THREE.Group(); pv.add(m); pv.userData.vitesse = piece.vitesse ?? 1; g.add(pv); }
    else {
      const T = r.info.assemblage?.[i];
      if (T) {                                  // pose de montage fournie par le generateur (vue montee)
        const M = new THREE.Matrix4().fromArray(T.flat()).transpose();
        m.userData.pose = M.clone();
        if (!W.eclate) M.decompose(m.position, m.quaternion, m.scale);
      }
      g.add(m);
    }
  }
  if (W.eclate) eclater(g);
  piece.groupe = g;
  return piece;
}
async function ajouter(type, params = {}, opts = {}) {
  const c = W.cat[type];
  const p = { id: 'p' + (W.idn++), type, nom: c.nom, params: Object.fromEntries(c.champs.map(f => [f.k, f.val])), couleur: PALETTE[W.idn % PALETTE.length] };
  Object.assign(p.params, params);
  try {
    $('#sw-info').textContent = `Generation : ${c.nom}...`;
    await construire(p);
    const b = new THREE.Box3(); W.pieces.forEach(x => b.union(new THREE.Box3().setFromObject(x.groupe)));
    const bp = new THREE.Box3().setFromObject(p.groupe);
    if (opts.position) p.groupe.position.fromArray(opts.position);
    else if (W.pieces.length) p.groupe.position.x = b.max.x + 10 - bp.min.x;
    p.groupe.position.z -= Math.min(0, new THREE.Box3().setFromObject(p.groupe).min.z);
    scene.add(p.groupe); W.pieces.push(p); selectionner(p); majNomenclature(); cadrer();
  } catch (e) { toast(e.message); }
  return p;
}
function eclater(g) {              // pieces cote a cote, dans leur orientation d'impression
  let x = 0;
  g.children.forEach(m => { if (!m.isMesh) return; m.position.set(0, 0, 0); m.quaternion.identity(); m.updateMatrixWorld();
    const b = new THREE.Box3().setFromObject(m); m.position.x = x - b.min.x; x += b.max.x - b.min.x + 10; });
}
async function basculerEclate() {
  W.eclate = !W.eclate; $('#sw-eclate').classList.toggle('on', W.eclate);
  for (const p of W.pieces) { const pos = p.groupe.position.clone(); await construire(p); p.groupe.position.copy(pos); }
}
function selectionner(p) {
  W.sel = p; tc.detach(); if (p) tc.attach(p.groupe);
  for (const x of W.pieces) x.groupe.traverse(o => { if (o.isMesh) { o.material.emissive?.setHex(x === p ? 0x442200 : 0x000000); } });
  formulaire();
}
function supprimer() { if (!W.sel) return; scene.remove(W.sel.groupe); W.pieces = W.pieces.filter(x => x !== W.sel); selectionner(null); majNomenclature(); }

// ------------------------------------------------------------------ formulaire auto (schema du generateur)
let _t = null;
function formulaire() {
  const z = $('#sw-params');
  if (!W.sel) { z.innerHTML = '<p class="mute">Choisis une piece dans la bibliotheque, ou clique une piece de l\'assemblage.</p>'; return; }
  const c = W.cat[W.sel.type], p = W.sel.params;
  z.innerHTML = `<label>Nom<input id="sw-nom" value="${W.sel.nom.replace(/"/g, '')}"></label>` + c.champs.map(f => {
    const v = p[f.k];
    if (f.type === 'bool') return `<label class="chk"><input type="checkbox" data-k="${f.k}" ${v ? 'checked' : ''}> ${f.label}</label>`;
    if (f.type === 'choix') return `<label>${f.label}<select data-k="${f.k}">${f.options.map(o => `<option ${o == v ? 'selected' : ''}>${o}</option>`).join('')}</select></label>`;
    return `<label>${f.label} <b data-v="${f.k}">${v}</b><input type="range" data-k="${f.k}" min="${f.min}" max="${f.max}" step="${f.pas}" value="${v}">${f.aide ? `<span class="mute">${f.aide}</span>` : ''}</label>`;
  }).join('') + `<div id="sw-infos" class="mute"></div>`;
  $('#sw-nom').onchange = e => { W.sel.nom = e.target.value; majNomenclature(); };
  const vs = W.sel.variantes ||= {};
  const zv = document.createElement('div'); zv.className = 'sw-versions';
  zv.innerHTML = `<h2>Versions</h2><div class="grid2"><select id="sw-v-liste"><option value="">(version courante)</option>${Object.keys(vs).map(n => `<option ${n === W.sel.version ? 'selected' : ''}>${n}</option>`).join('')}</select>
    <button id="sw-v-suppr">Supprimer</button></div><div class="grid2" style="margin-top:5px"><input id="sw-v-nom" placeholder="nom de la version"><button id="sw-v-save">Enregistrer</button></div>`;
  z.prepend(zv);
  $('#sw-v-save').onclick = () => { const n = $('#sw-v-nom').value.trim() || `v${Object.keys(vs).length + 1}`; vs[n] = JSON.parse(JSON.stringify(W.sel.params)); W.sel.version = n; formulaire(); toast(`Version "${n}" enregistree`); };
  $('#sw-v-liste').onchange = async e => { const n = e.target.value; if (!n) return; W.sel.params = JSON.parse(JSON.stringify(vs[n])); W.sel.version = n;
    const pos = W.sel.groupe.position.clone(); await construire(W.sel); W.sel.groupe.position.copy(pos); formulaire(); majNomenclature(); };
  $('#sw-v-suppr').onclick = () => { const n = $('#sw-v-liste').value; if (n) { delete vs[n]; W.sel.version = null; formulaire(); } };
  if (W.sel.type === 'vibedeck') {
    const b = document.createElement('button'); b.textContent = 'Envoyer les touches au lot Keycaps'; b.style.marginTop = '8px';
    b.onclick = async () => {
      const K = window.__KC; if (!K) return;
      const n = (W.sel.params.colonnes | 0) * (W.sel.params.rangees | 0);
      const sel = document.getElementById('kc-rangee'); document.getElementById('kc-clavier').value = W.sel.nom;
      $('[data-tab="kc"]').click(); await new Promise(r => setTimeout(r, 300));
      sel.value = 'macro'; sel.dispatchEvent(new Event('change'));
      toast(`Touches M1..M9 ajoutees : ajuste a ${n} touches dans le lot`);
    };
    z.appendChild(b);
  }
  z.querySelectorAll('[data-k]').forEach(i => i.addEventListener('input', () => {
    const k = i.dataset.k; p[k] = i.type === 'checkbox' ? (i.checked ? 1 : 0) : i.type === 'range' ? +i.value : i.value;
    const b = z.querySelector(`[data-v="${k}"]`); if (b) b.textContent = i.value;
    clearTimeout(_t); _t = setTimeout(async () => { const pos = W.sel.groupe.position.clone(); try { await construire(W.sel); W.sel.groupe.position.copy(pos); majNomenclature(); infos(); } catch (e) { toast(e.message); } }, 250);
  }));
  infos();
}
function infos() {
  const i = W.sel?.info; if (!i) return;
  const lignes = [];
  if (i.entraxe_mm) lignes.push(`Entraxe <b>${i.entraxe_mm} mm</b> &middot; rapport <b>${i.rapport}</b>`);
  if (i.r_primitif) lignes.push(`Diametre primitif ${r2(2 * i.r_primitif)} mm &middot; tete ${r2(2 * i.r_tete)} mm`);
  if (i.torsion_deg) lignes.push(`Torsion de l'helice ${i.torsion_deg} deg`);
  if (i.billes) lignes.push(`${i.billes} billes de ${i.d_bille} mm`);
  if (i.diametre_primitif) lignes.push(`Diametre primitif ${i.diametre_primitif} mm`);
  if (i.pas_mm) lignes.push(`Pas ${i.pas_mm} mm, ${i.dents} dents`);
  if (i.force_sortie_6bar_N) lignes.push(`Force a 6 bar : sortie <b>${i.force_sortie_6bar_N} N</b> (~${r2(i.force_sortie_6bar_N / 9.81)} kg), rentree ${i.force_rentree_6bar_N} N`);
  if (i.joint) lignes.push(`Joint : <b>${i.joint}</b> &middot; gorge ${i.profondeur} mm de profondeur x ${i.largeur} mm, fond d${i.fond}`);
  if (i.ecran_a_mesurer) lignes.push(`<span class="badge warn">${i.ecran_a_mesurer}</span>`);
  if (i.dimensions_boitier_mm) lignes.push(`Boitier ${i.dimensions_boitier_mm.join(' x ')} mm &middot; ${i.touches} touches`);
  if (i.conseil) lignes.push(i.conseil);
  if (i.quincaillerie) lignes.push('A acheter : ' + i.quincaillerie.join(', '));
  $('#sw-infos').innerHTML = lignes.join('<br>');
}

// ------------------------------------------------------------------ animation des engrenages
function animer(dt) {
  const v = +$('#sw-vitesse').value;     // tours / min de l'entree
  for (const p of W.pieces) p.groupe.children.forEach(c => { if (c.userData.vitesse != null) c.rotation.z += dt * v / 60 * 2 * Math.PI * c.userData.vitesse; });
}
$('#sw-animer').onclick = () => { W.anim = !W.anim; $('#sw-animer').classList.toggle('on', W.anim); $('#sw-animer').textContent = W.anim ? 'Stop' : 'Animer'; };

// ------------------------------------------------------------------ nomenclature + analyse
function majNomenclature() {
  const q = {};
  const lignes = W.pieces.map(p => {
    (p.info?.quincaillerie || []).forEach(x => q[x] = (q[x] || 0) + 1);
    const n = p.objets?.length || 0, poids = (p.objets || []).reduce((a, o) => a + (o.analyse?.poids_g || 0), 0);
    return `<tr data-p="${p.id}"><td>${p.nom}</td><td>${n}</td><td>${r2(poids)} g</td></tr>`;
  });
  const tot = W.pieces.reduce((a, p) => a + (p.objets || []).reduce((b, o) => b + (o.analyse?.poids_g || 0), 0), 0);
  $('#sw-nomenclature').innerHTML = `<table class="tbl"><tr><th>Piece</th><th>Qte</th><th>Poids</th></tr>${lignes.join('')}
    <tr><td><b>Total imprime</b></td><td></td><td><b>${r2(tot)} g</b></td></tr></table>
    ${Object.keys(q).length ? `<p><b>Quincaillerie</b><br>${Object.entries(q).map(([k, n]) => `${n} x ${k}`).join('<br>')}</p>` : ''}`;
  $$('#sw-nomenclature [data-p]').forEach(tr => tr.onclick = () => selectionner(W.pieces.find(p => p.id === tr.dataset.p)));
}

// ------------------------------------------------------------------ interaction
const ray = new THREE.Raycaster(), souris = new THREE.Vector2(); let bas = null;
ren.domElement.addEventListener('pointerdown', e => bas = [e.clientX, e.clientY]);
ren.domElement.addEventListener('pointerup', e => {
  if (!bas || Math.hypot(e.clientX - bas[0], e.clientY - bas[1]) > 4 || tc.dragging || e.button !== 0) return;
  const r = ren.domElement.getBoundingClientRect();
  souris.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1); ray.setFromCamera(souris, cam);
  const meshes = []; W.pieces.forEach(p => p.groupe.traverse(o => o.isMesh && meshes.push(o)));
  const h = ray.intersectObjects(meshes, false)[0];
  selectionner(h ? h.object.userData.piece : null);
});
document.addEventListener('keydown', e => {
  if (!$('#tab-sw').classList.contains('on') || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
  if (e.key === 'Delete') supprimer();
  if (e.key === 'w') tc.setMode('translate'); if (e.key === 'e') tc.setMode('rotate');
  if (e.key === 'Escape') selectionner(null);
});
function cadrer() {
  const b = new THREE.Box3(); W.pieces.forEach(p => b.union(new THREE.Box3().setFromObject(p.groupe)));
  if (W.reference) b.union(new THREE.Box3().setFromObject(W.reference.mesh));
  if (b.isEmpty()) return;
  const c = b.getCenter(new THREE.Vector3()), r = Math.max(b.getSize(new THREE.Vector3()).length(), 40);
  orb.target.copy(c); cam.position.copy(c).add(new THREE.Vector3(-0.45, -1, 0.8).normalize().multiplyScalar(r * 1.6)); orb.update();
}
$('#sw-cadrer').onclick = cadrer;
$('#sw-eclate').onclick = basculerEclate;
$('#sw-suppr').onclick = supprimer;
$('#sw-dupliquer').onclick = async () => { if (!W.sel) return; const p = await ajouter(W.sel.type, { ...W.sel.params }); p.nom = W.sel.nom; };

// envoi vers Creation 3D (les pieces gardent leur position dans l'assemblage)
async function versServeur() {
  const out = [];
  for (const p of W.pieces) p.groupe.updateMatrixWorld(true), p.groupe.traverse(o => { if (o.isMesh) out.push({ fichier: o.geometry.userData.fichier || p.objets[o.userData.k].fichier, matrice: o.matrixWorld.toArray(), nom: p.nom, bobine: $('#sw-bobine').value, trou: false }); });
  return out;
}
$('#sw-vers-c3d').onclick = async () => {
  const C = window.__C3D; if (!C?._ajout) return;
  for (const p of W.pieces) for (const o of p.objets) await C._ajout({ ...o, nom: p.nom }, $('#sw-bobine').value);
  toast(`${W.pieces.length} piece(s) envoyee(s) dans Creation 3D`); $('[data-tab="c3d"]').click();
};
$('#sw-imprimer').onclick = async () => {
  if (!W.pieces.length) return toast('Assemblage vide');
  try {
    const objets = (await versServeur()).map(o => ({ ...o, matrice: null }));    // chaque piece posee a plat a l'impression
    const { job } = await api('/api/c3d/imprimer', { outil: 'imprimer', objets });
    await A().suivre(job, '#sw-prog', res => { const S = A().S; S.gen = res; S.tranches = {}; A().renderPlateauxImp(); toast(`${res.plateaux.length} plateau(x) prets`); $('[data-tab="imprimer"]').click(); });
  } catch (e) { toast(e.message); }
};

// ------------------------------------------------------------------ projets (sauvegarde / chargement)
W.exporter = () => ({ reference: W.reference ? { fichier: W.reference.fichier, nom: W.reference.nom } : null, pieces: W.pieces.map(p => ({ type: p.type, nom: p.nom, params: p.params, variantes: p.variantes || {}, version: p.version || null, position: p.groupe.position.toArray(), rotation: p.groupe.rotation.toArray().slice(0, 3), couleur: p.couleur })) });
W.charger = async d => {
  for (const p of [...W.pieces]) scene.remove(p.groupe); W.pieces = []; selectionner(null);
  for (const x of d.pieces || []) { const p = await ajouter(x.type, x.params, { position: x.position }); p.nom = x.nom; p.variantes = x.variantes || {}; p.version = x.version; if (x.rotation) p.groupe.rotation.set(...x.rotation); }
  if (d.reference) await W.baseImportee(d.reference, d.reference.nom);
  majNomenclature(); cadrer();
};
W.miniature = () => { ren.render(scene, cam); const c = document.createElement('canvas'); c.width = 320; c.height = 220; c.getContext('2d').drawImage(ren.domElement, 0, 0, 320, 220); return c.toDataURL('image/png'); };
W.vider = () => W.charger({});
W.reference = null;
W.baseImportee = async (r, nom) => {           // maillage de reference (ex. carrosserie) : semi-transparent, non imprime
  const g = await charger(r.fichier);
  if (W.reference) scene.remove(W.reference.mesh);
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x9fb4d0, transparent: true, opacity: 0.35, depthWrite: false }));
  scene.add(m); W.reference = { fichier: r.fichier, nom, mesh: m }; cadrer();
};

// ------------------------------------------------------------------ demarrage
(async function init() {
  for (let i = 0; i < 60 && !A()?.S?.etat; i++) await new Promise(r => setTimeout(r, 100));
  W.cat = await api('/api/meca/catalogue');
  const cats = {};
  for (const [k, c] of Object.entries(W.cat)) if (c.cat !== 'Projets') (cats[c.cat] ||= []).push([k, c]);
  $('#sw-lib').innerHTML = Object.entries(cats).map(([cat, l]) => `<h2>${cat}</h2><div class="c3d-gens">${l.map(([k, c]) => `<button data-sw="${k}">${c.nom}</button>`).join('')}</div>`).join('');
  $$('[data-sw]').forEach(b => b.onclick = () => ajouter(b.dataset.sw));
  $('#sw-bobine').innerHTML = A().S.etat.bobines.map(b => `<option value="${b.id}">${b.nom}</option>`).join('');
  formulaire(); majNomenclature(); taille();
  document.addEventListener('click', e => { if (e.target.closest('[data-tab="sw"]')) setTimeout(taille, 30); });
})();
