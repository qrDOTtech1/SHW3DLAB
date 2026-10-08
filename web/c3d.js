// CREATION 3D : editeur facon Tinkercad (plan de travail, solides / percages, grouper) + outils pro.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { STLExporter } from 'three/addons/exporters/STLExporter.js';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { MOTIFS, preparer, appliquer } from './effets.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const A = () => window.ATELIER;
const api = (u, b) => A().api(u, b);
const toast = m => A().toast(m);
const r2 = v => Math.round(v * 100) / 100;

const PLAT = [220, 215, 245];
const C = { objets: [], sel: [], hist: [], futur: [], geo: {}, mode: 'translate', mesure: null, surplombs: false, idn: 1 };
window.__C3D = C;

// ------------------------------------------------------------------ scene
const el = $('#c3d-view');
const ren = new THREE.WebGLRenderer({ antialias: true, alpha: true });
ren.setPixelRatio(Math.min(devicePixelRatio, 2)); ren.shadowMap.enabled = true;
el.appendChild(ren.domElement);
const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(38, 1, 0.5, 6000);
cam.up.set(0, 0, 1);
cam.position.set(-40, -260, 210);
const orb = new OrbitControls(cam, ren.domElement); orb.enableDamping = true; orb.target.set(0, 0, 0);
scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.5));
const sun = new THREE.DirectionalLight(0xffffff, 2.0); sun.position.set(-150, -200, 400); sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -220, right: 220, top: 220, bottom: -220 });
scene.add(sun);
// plateau K2 SE : plaque + grille 10 mm + contour + axes
const plaque = new THREE.Mesh(new THREE.PlaneGeometry(PLAT[0], PLAT[1]), new THREE.MeshStandardMaterial({ color: 0x1b2230, roughness: 0.9 }));
plaque.receiveShadow = true; plaque.position.z = -0.05; scene.add(plaque);
const grille = new THREE.GridHelper(220, 22, 0x3d4a5e, 0x283141); grille.rotation.x = Math.PI / 2; scene.add(grille);
const fine = new THREE.GridHelper(220, 220, 0x202733, 0x202733); fine.rotation.x = Math.PI / 2; fine.position.z = -0.02;
fine.material.transparent = true; fine.material.opacity = 0.45; scene.add(fine);
const bord = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(PLAT[0], PLAT[1], PLAT[2])),
  new THREE.LineBasicMaterial({ color: 0x3a4658, transparent: true, opacity: 0.5 }));
bord.position.z = PLAT[2] / 2; scene.add(bord);
for (const [v, c] of [[[1, 0, 0], 0xff5566], [[0, 1, 0], 0x55dd88]]) {
  const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-110 * v[0], -107.5 * v[1], 0.05), new THREE.Vector3(110 * v[0], 107.5 * v[1], 0.05)]);
  scene.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: 0.5 })));
}
const tc = new TransformControls(cam, ren.domElement);
tc.addEventListener('dragging-changed', e => { orb.enabled = !e.value; if (!e.value) { appliquerPivot(); poserSiSous(); memo(); majInspecteur(); analyserBientot(); } });
tc.addEventListener('objectChange', () => { suivrePivot(); majInspecteur(true); });
scene.add(tc);
// pivot : la gizmo deplace un objet "pivot" ; ses deplacements sont recopies sur toute la selection
const pivot = new THREE.Object3D(); scene.add(pivot);
let pivot0 = null, enfants0 = [];

function taille() {
  const w = el.clientWidth, h = el.clientHeight; if (!w) return;
  ren.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix();
}
new ResizeObserver(taille).observe(el);
(function boucle() { requestAnimationFrame(boucle); orb.update(); ren.render(scene, cam); })();
document.addEventListener('click', e => { if (e.target.closest('[data-tab="c3d"]')) setTimeout(taille, 30); });

// ------------------------------------------------------------------ materiaux
const loader = new STLLoader();
const couleurBob = id => A().bobine(id)?.couleur || '#e8e3d8';
function materiau(o, sel) {
  if (o.trou) return new THREE.MeshStandardMaterial({ color: sel ? 0x9fb4d0 : 0x7d8796, transparent: true, opacity: sel ? 0.55 : 0.38, depthWrite: false });
  const m = new THREE.MeshStandardMaterial({ color: couleurBob(o.bobine), roughness: 0.5, metalness: 0.03, vertexColors: C.surplombs });
  if (sel) { m.emissive = new THREE.Color(0xff7a2f); m.emissiveIntensity = 0.18; }
  return m;
}
async function geometrie(fichier) {
  if (!C.geo[fichier]) C.geo[fichier] = new Promise((ok, ko) => loader.load(`/c3d/${fichier}.stl`, g => { g.computeVertexNormals(); ok(g); }, undefined, ko));
  return C.geo[fichier];
}
function colorerSurplombs(mesh) {
  const g = mesh.geometry, n = g.attributes.normal, pos = g.attributes.position;
  const col = new Float32Array(pos.count * 3);
  const nm = new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld), v = new THREE.Vector3(), p = new THREE.Vector3();
  const zmin = new THREE.Box3().setFromObject(mesh).min.z;
  const base = new THREE.Color(couleurBob(mesh.userData.o.bobine));
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(n, i).applyMatrix3(nm).normalize();
    p.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld);
    const sur = v.z < -0.707 && p.z - zmin > 0.3;
    const c = sur ? new THREE.Color(0xff2d55) : base;
    col.set([c.r, c.g, c.b], i * 3);
  }
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
}

// ------------------------------------------------------------------ objets
function nouvelId() { return 'o' + (C.idn++) + Math.random().toString(36).slice(2, 5); }
async function ajouterObjet(o, opts = {}) {
  o.id = o.id || nouvelId();
  o.bobine = o.bobine || $('#c3-bob-defaut')?.value || A().S.etat?.bobines?.[0]?.id || 'b1';
  const g = (await geometrie(o.fichier)).clone();
  const mesh = new THREE.Mesh(g, materiau(o, false));
  mesh.castShadow = !o.trou; mesh.receiveShadow = true; mesh.userData.o = o;
  if (o.matrice) new THREE.Matrix4().fromArray(o.matrice).decompose(mesh.position, mesh.quaternion, mesh.scale);
  o.mesh = mesh; scene.add(mesh); C.objets.push(o);
  if (opts.placer) {
    mesh.updateMatrixWorld();
    const b = new THREE.Box3().setFromObject(mesh);
    const c = b.getCenter(new THREE.Vector3());
    mesh.position.x += (opts.placer.x ?? 0) - c.x; mesh.position.y += (opts.placer.y ?? 0) - c.y; mesh.position.z -= b.min.z;
    if (opts.placer.surDessus) {                 // empilement facon Tinkercad : pose sur ce qu'il y a dessous
      mesh.updateMatrixWorld(); const bb = new THREE.Box3().setFromObject(mesh); let z = 0;
      for (const x of C.objets) if (x !== o && !x.trou) { const bx = new THREE.Box3().setFromObject(x.mesh); if (bx.intersectsBox(new THREE.Box3(new THREE.Vector3(bb.min.x, bb.min.y, -1), new THREE.Vector3(bb.max.x, bb.max.y, 999)))) z = Math.max(z, bx.max.z); }
      mesh.position.z += z;
    }
  }
  mesh.updateMatrixWorld();
  if (C.surplombs) colorerSurplombs(mesh);
  return o;
}
function retirer(o) { scene.remove(o.mesh); o.mesh.geometry.dispose(); C.objets = C.objets.filter(x => x !== o); }
const serial = o => { o.mesh.updateMatrixWorld(); return { id: o.id, nom: o.nom, type: o.type, params: o.params, fichier: o.fichier, trou: !!o.trou, bobine: o.bobine, matrice: o.mesh.matrixWorld.toArray(), enfants: o.enfants || null }; };
const pourServeur = o => { o.mesh.updateMatrixWorld(); return { fichier: o.fichier, matrice: o.mesh.matrixWorld.toArray(), trou: !!o.trou, bobine: o.bobine, nom: o.nom || o.type }; };

// ------------------------------------------------------------------ historique
function memo() { C.hist.push(JSON.stringify(C.objets.map(serial))); if (C.hist.length > 80) C.hist.shift(); C.futur = []; sauverLocal(); }
async function restaurer(etat) {
  selectionner([]);
  for (const o of [...C.objets]) retirer(o);
  for (const s of JSON.parse(etat)) await ajouterObjet({ ...s });
  majInspecteur(); analyserBientot(); sauverLocal();
}
async function annuler() { if (C.hist.length < 2) return; C.futur.push(C.hist.pop()); await restaurer(C.hist.at(-1)); }
async function refaire() { if (!C.futur.length) return; const e = C.futur.pop(); C.hist.push(e); await restaurer(e); }
function sauverLocal() { try { localStorage.setItem('c3d_scene', JSON.stringify(C.objets.map(serial))); } catch { } }

// ------------------------------------------------------------------ selection + gizmo
function selectionner(liste, ajout = false) {
  if (ajout) { for (const o of liste) C.sel = C.sel.includes(o) ? C.sel.filter(x => x !== o) : [...C.sel, o]; }
  else C.sel = liste;
  for (const o of C.objets) o.mesh.material = materiau(o, C.sel.includes(o));
  tc.detach();
  if (C.sel.length) {
    const b = boite(C.sel); pivot.position.copy(b.getCenter(new THREE.Vector3())); pivot.position.z = b.min.z;
    pivot.rotation.set(0, 0, 0); pivot.scale.set(1, 1, 1); pivot.updateMatrixWorld();
    tc.attach(pivot); armerPivot();
  }
  majInspecteur(); analyserBientot();
}
function armerPivot() {
  pivot.updateMatrixWorld(); pivot0 = pivot.matrixWorld.clone();
  enfants0 = C.sel.map(o => { o.mesh.updateMatrixWorld(); return o.mesh.matrixWorld.clone(); });
}
function suivrePivot() {
  pivot.updateMatrixWorld();
  const delta = pivot.matrixWorld.clone().multiply(pivot0.clone().invert());
  C.sel.forEach((o, i) => { const m = delta.clone().multiply(enfants0[i]); m.decompose(o.mesh.position, o.mesh.quaternion, o.mesh.scale); o.mesh.updateMatrixWorld(); });
}
function appliquerPivot() { armerPivot(); if (C.surplombs) C.sel.forEach(o => colorerSurplombs(o.mesh)); }
function poserSiSous() {           // rien ne passe sous le plateau
  for (const o of C.sel) { const b = new THREE.Box3().setFromObject(o.mesh); if (b.min.z < -0.001 && !o.trou) { o.mesh.position.z -= b.min.z; o.mesh.updateMatrixWorld(); } }
  if (C.sel.length) { const b = boite(C.sel); pivot.position.z = b.min.z; armerPivot(); }
}
function boite(liste) { const b = new THREE.Box3(); for (const o of liste) { o.mesh.updateMatrixWorld(); b.union(new THREE.Box3().setFromObject(o.mesh)); } return b; }
function snap() {
  const s = +$('#c3-snap').value;
  tc.setTranslationSnap(s || null); tc.setRotationSnap(s ? THREE.MathUtils.degToRad(15) : null); tc.setScaleSnap(s ? 0.05 : null);
}
$('#c3-snap').onchange = snap; snap();
function modeGizmo(m) { C.mode = m; tc.setMode(m); $$('[data-mode]').forEach(b => b.classList.toggle('on', b.dataset.mode === m)); }
$$('[data-mode]').forEach(b => b.onclick = () => modeGizmo(b.dataset.mode));

// clic dans la scene : selection / regle
const ray = new THREE.Raycaster(), souris = new THREE.Vector2();
let bas = null;
ren.domElement.addEventListener('pointerdown', e => { bas = [e.clientX, e.clientY]; });
ren.domElement.addEventListener('pointerup', e => {
  if (e.button !== 0) return;
  if (!bas || Math.hypot(e.clientX - bas[0], e.clientY - bas[1]) > 4 || tc.dragging) return;
  const r = ren.domElement.getBoundingClientRect();
  souris.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(souris, cam);
  const hits = ray.intersectObjects(C.objets.map(o => o.mesh), false);
  if (C.arete && !_pan) { const h = ray.intersectObjects(C.objets.map(o => o.mesh), false)[0]; if (h) cliquerArete(h); return; }
  if (C.integ && !_pan) { const h = ray.intersectObjects(C.objets.filter(o => o !== C.integ.motif).map(o => o.mesh), false)[0]; if (h) poserSurSurface(h); else toast('Clique sur la surface d\'un objet'); return; }
  if (C.mesure) { mesurer(hits[0]?.point || ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), new THREE.Vector3())); return; }
  if (hits.length) selectionner([hits[0].object.userData.o], e.shiftKey);
  else if (!e.shiftKey) selectionner([]);
});

// ------------------------------------------------------------------ regle (mesure)
const reglerMat = new THREE.LineBasicMaterial({ color: 0xff7a2f, depthTest: false });
let regle = null;
function mesurer(p) {
  if (!p) return;
  C.mesure.pts.push(p.clone());
  if (regle) scene.remove(regle);
  const pts = C.mesure.pts;
  regle = new THREE.Group();
  for (const q of pts) { const s = new THREE.Mesh(new THREE.SphereGeometry(1.2), new THREE.MeshBasicMaterial({ color: 0xff7a2f, depthTest: false })); s.position.copy(q); regle.add(s); }
  if (pts.length === 2) {
    regle.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), reglerMat));
    const d = pts[0].distanceTo(pts[1]), dv = pts[1].clone().sub(pts[0]);
    $('#c3-mesure').hidden = false;
    $('#c3-mesure').textContent = `${r2(d)} mm  (dx ${r2(Math.abs(dv.x))} dy ${r2(Math.abs(dv.y))} dz ${r2(Math.abs(dv.z))})`;
    C.mesure.pts = [];
  }
  scene.add(regle);
}

// ------------------------------------------------------------------ inspecteur
const PARAMS = {
  boite: [['x', 'Largeur X', 20], ['y', 'Profondeur Y', 20], ['z', 'Hauteur Z', 20], ['arrondi', 'Arrondi des angles', 0]],
  cylindre: [['d', 'Diametre', 20], ['z', 'Hauteur', 20], ['cotes', 'Facettes', 96]],
  sphere: [['d', 'Diametre', 20]], demi_sphere: [['d', 'Diametre', 20]],
  cone: [['d', 'Diametre bas', 20], ['d_haut', 'Diametre haut', 0], ['z', 'Hauteur', 20]],
  pyramide: [['x', 'Base', 20], ['z', 'Hauteur', 20], ['cotes', 'Cotes', 4]],
  prisme: [['d', 'Diametre', 20], ['z', 'Hauteur', 20], ['cotes', 'Cotes', 6]],
  tube: [['d', 'Diametre', 20], ['paroi', 'Paroi', 2], ['z', 'Hauteur', 20]],
  tore: [['d', 'Diametre', 30], ['e', 'Epaisseur', 6]],
  etoile: [['d', 'Diametre', 30], ['branches', 'Branches', 5], ['creux', 'Creux (0-1)', 0.45], ['z', 'Epaisseur', 5]],
  coeur: [['x', 'Largeur', 30], ['z', 'Epaisseur', 5]],
  texte: [['texte', 'Texte', 'Steven'], ['h', 'Hauteur lettres', 15], ['z', 'Epaisseur', 3]],
  vis: [['d', 'Diametre (M)', 8], ['pas', 'Pas', 1.25], ['z', 'Longueur', 20], ['tete', 'Tete (cle)', 13]],
  ecrou: [['d', 'Diametre (M)', 8], ['pas', 'Pas', 1.25], ['tete', 'Cle', 13], ['z', 'Epaisseur', 6.5], ['jeu', 'Jeu', 0.25]],
  boite_couvercle: [['x', 'Largeur', 60], ['y', 'Profondeur', 40], ['z', 'Hauteur', 30], ['paroi', 'Paroi', 2], ['arrondi', 'Arrondi', 4], ['jeu', 'Jeu couvercle', 0.2]],
  anneau_cle: [['d', 'Diametre', 12], ['paroi', 'Paroi', 3], ['z', 'Epaisseur', 4]],
};
function majInspecteur(leger) {
  const z = $('#c3-insp');
  if (!C.sel.length) { z.innerHTML = '<p class="mute">Rien de selectionne. Ctrl+A : tout selectionner.</p>'; $('#c3-info').textContent = `${C.objets.length} objet(s) sur le plateau`; return; }
  const b = boite(C.sel), t = b.getSize(new THREE.Vector3());
  $('#c3-info').textContent = `${C.sel.length} selectionne(s) - ${r2(t.x)} x ${r2(t.y)} x ${r2(t.z)} mm`;
  if (leger && z.querySelector('#c3-dx')) {
    [['dx', t.x], ['dy', t.y], ['dz', t.z], ['px', b.min.x], ['py', b.min.y], ['pz', b.min.z]].forEach(([k, v]) => { const i = $('#c3-' + k); if (document.activeElement !== i) i.value = r2(v); });
    return;
  }
  const o = C.sel[0], seul = C.sel.length === 1;
  const bobs = A().S.etat?.bobines || [];
  const rot = seul ? new THREE.Euler().setFromQuaternion(o.mesh.quaternion, 'XYZ') : null;
  z.innerHTML = `
    ${seul ? `<label>Nom<input id="c3-nom" value="${(o.nom || o.type || '').replace(/"/g, '')}"></label>` : `<p><b>${C.sel.length} objets</b></p>`}
    <div class="grid2">
      <label>Type<select id="c3-trou"><option value="0" ${o.trou ? '' : 'selected'}>Solide</option><option value="1" ${o.trou ? 'selected' : ''}>Percage</option></select></label>
      <label>Couleur / bobine<select id="c3-bob">${bobs.map(x => `<option value="${x.id}" ${x.id === o.bobine ? 'selected' : ''}>${x.nom}</option>`).join('')}</select></label>
    </div>
    <div class="xyz"><span></span><span>X</span><span>Y</span><span>Z</span>
      <span>mm</span><input id="c3-dx" type="number" step="0.1" value="${r2(t.x)}"><input id="c3-dy" type="number" step="0.1" value="${r2(t.y)}"><input id="c3-dz" type="number" step="0.1" value="${r2(t.z)}">
      <span>pos</span><input id="c3-px" type="number" step="0.5" value="${r2(b.min.x)}"><input id="c3-py" type="number" step="0.5" value="${r2(b.min.y)}"><input id="c3-pz" type="number" step="0.5" value="${r2(b.min.z)}">
      ${seul ? `<span>rot</span>${['x', 'y', 'z'].map(a => `<input id="c3-r${a}" type="number" step="15" value="${r2(THREE.MathUtils.radToDeg(rot[a]))}">`).join('')}` : ''}
    </div>
    <label class="chk"><input type="checkbox" id="c3-prop" checked> Garder les proportions</label>
    ${seul && o.type === 'gen_vase' ? `<div class="params"><h2>Vase</h2><button id="c3-vase" class="primary" style="width:100%">Modifier : forme a la souris, epaisseur, texte / logo</button></div>` : ''}
    ${seul && o.type !== 'gen_vase' && o.type.startsWith('gen_') && GEN[o.type.slice(4)] ? `<div class="params"><h2>Parametres</h2>${GEN[o.type.slice(4)].champs.filter(c => c.type !== 'info' && c.type !== 'select').map(c => `<label>${c.label}<input data-p="${c.k}" type="number" step="any" value="${o.params?.[c.k] ?? c.val}"></label>`).join('')}<button id="c3-regen">Appliquer</button></div>` : ''}
    ${seul && PARAMS[o.type] ? `<div class="params"><h2>Parametres</h2>${PARAMS[o.type].map(([k, l, d]) => `<label>${l}<input data-p="${k}" ${typeof d === 'string' ? '' : 'type="number" step="any"'} value="${o.params?.[k] ?? d}"></label>`).join('')}
      ${o.type === 'texte' ? `<label>Police<select data-p="police">${Object.entries(A().S.polices || {}).map(([k, p]) => `<option value="${k}" ${k === (o.params?.police || 'arial_black') ? 'selected' : ''}>${p.label}</option>`).join('')}</select></label>` : ''}
      <button id="c3-regen">Appliquer</button></div>` : ''}
    ${seul && o.enfants ? '<p class="mute">Groupe : Degrouper pour retrouver les pieces.</p>' : ''}`;
  $('#c3-trou').onchange = e => { C.sel.forEach(x => { x.trou = e.target.value === '1'; x.mesh.castShadow = !x.trou; x.mesh.material = materiau(x, true); }); memo(); analyserBientot(); };
  $('#c3-bob').onchange = e => { C.sel.forEach(x => { x.bobine = e.target.value; x.mesh.material = materiau(x, true); }); memo(); analyserBientot(); };
  if (seul) $('#c3-nom').onchange = e => { o.nom = e.target.value; memo(); };
  for (const [k, ax] of [['dx', 'x'], ['dy', 'y'], ['dz', 'z']]) $('#c3-' + k).onchange = e => redimensionner(ax, +e.target.value);
  for (const [k, ax] of [['px', 'x'], ['py', 'y'], ['pz', 'z']]) $('#c3-' + k).onchange = e => deplacerA(ax, +e.target.value);
  if (seul) for (const a of ['x', 'y', 'z']) $('#c3-r' + a).onchange = () => {
    const centre = boite([o]).getCenter(new THREE.Vector3());
    o.mesh.rotation.set(...['x', 'y', 'z'].map(q => THREE.MathUtils.degToRad(+$('#c3-r' + q).value)));
    o.mesh.updateMatrixWorld(); const c2 = boite([o]).getCenter(new THREE.Vector3()); o.mesh.position.add(centre.sub(c2));
    finirEdition();
  };
  $('#c3-regen')?.addEventListener('click', regenerer);
  $('#c3-vase')?.addEventListener('click', () => ouvrirVase(o));
}
function finirEdition() { poserSiSous(); selectionner(C.sel); memo(); if (C.surplombs) C.sel.forEach(o => colorerSurplombs(o.mesh)); }
function redimensionner(ax, v) {
  if (!(v > 0)) return;
  const b = boite(C.sel), t = b.getSize(new THREE.Vector3()), k = v / t[ax], c = b.min.clone();
  const f = $('#c3-prop').checked ? new THREE.Vector3(k, k, k) : new THREE.Vector3(ax === 'x' ? k : 1, ax === 'y' ? k : 1, ax === 'z' ? k : 1);
  const S = new THREE.Matrix4().makeTranslation(c.x, c.y, c.z).multiply(new THREE.Matrix4().makeScale(f.x, f.y, f.z)).multiply(new THREE.Matrix4().makeTranslation(-c.x, -c.y, -c.z));
  for (const o of C.sel) { o.mesh.updateMatrixWorld(); S.clone().multiply(o.mesh.matrixWorld).decompose(o.mesh.position, o.mesh.quaternion, o.mesh.scale); }
  finirEdition();
}
function deplacerA(ax, v) { const b = boite(C.sel), d = v - b.min[ax]; for (const o of C.sel) o.mesh.position[ax] += d; finirEdition(); }
async function regenerer() {
  const o = C.sel[0], p = {};
  $$('#c3-insp [data-p]').forEach(i => p[i.dataset.p] = i.type === 'number' ? +i.value : i.value);
  try {
    const r = o.type.startsWith('gen_') ? (await api('/api/c3d/generer', { nom: o.type.slice(4), params: { ...o.params, ...p } })).objets[0]
      : await api('/api/c3d/forme', { type: o.type, params: p });
    const b0 = boite([o]); o.mesh.updateMatrixWorld();
    const s = serial(o); retirer(o);
    const n = await ajouterObjet({ ...s, fichier: r.fichier, params: { ...o.params, ...p }, id: undefined });
    n.mesh.scale.set(1, 1, 1); n.mesh.updateMatrixWorld();
    const b1 = boite([n]), c0 = b0.getCenter(new THREE.Vector3()), c1 = b1.getCenter(new THREE.Vector3());
    n.mesh.position.x += c0.x - c1.x; n.mesh.position.y += c0.y - c1.y; n.mesh.position.z += b0.min.z - b1.min.z;
    selectionner([n]); memo();
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ ajout de formes
async function ajouterForme(type, params = {}, placer = { x: 0, y: 0, surDessus: true }) {
  try {
    $('#c3-info').textContent = 'Calcul de la forme...';
    const r = await api('/api/c3d/forme', { type, params });
    const o = await ajouterObjet({ type, params, fichier: r.fichier, nom: type, trou: $('#c3-mode-trou').checked }, { placer });
    selectionner([o]); memo();
  } catch (e) { toast(e.message); }
}
$$('[data-forme]').forEach(b => {
  b.onclick = () => ajouterForme(b.dataset.forme, b.dataset.forme === 'texte' ? texteParams() : {});
  b.ondragstart = e => e.dataTransfer.setData('text/forme', b.dataset.forme);
});
function pointPlateau(e) {
  const r = ren.domElement.getBoundingClientRect();
  souris.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(souris, cam);
  return ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), new THREE.Vector3()) || new THREE.Vector3();
}
const stage = $('.c3d-stage');
stage.addEventListener('dragover', e => { e.preventDefault(); stage.classList.add('c3d-glisse'); });
stage.addEventListener('dragleave', () => stage.classList.remove('c3d-glisse'));
stage.addEventListener('drop', async e => {
  e.preventDefault(); stage.classList.remove('c3d-glisse');
  const p = pointPlateau(e), s = +$('#c3-snap').value || 0;
  if (s) { p.x = Math.round(p.x / s) * s; p.y = Math.round(p.y / s) * s; }
  const f = e.dataTransfer.getData('text/forme');
  if (f) return ajouterForme(f, f === 'texte' ? texteParams() : {}, { x: p.x, y: p.y, surDessus: true });
  const fich = e.dataTransfer.files[0]; if (!fich) return;
  if (/^image\//.test(fich.type)) { await chargerImage(fich); return convertirImage({ x: p.x, y: p.y }); }
  importer(fich, { x: p.x, y: p.y });
});
const texteParams = () => ({ texte: $('#c3-texte').value || 'Texte', police: $('#c3-police').value, h: +$('#c3-texte-h').value, z: 3 });
$('#c3-texte-add').onclick = () => ajouterForme('texte', texteParams());

// image -> 3D
let imageId = '';
async function chargerImage(f) {
  const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(f); });
  imageId = (await api('/api/image', { data })).id; $('#c3-img-add').disabled = false; toast('Image prete : choisis le mode puis Convertir');
}
$('#c3-img').onchange = e => e.target.files[0] && chargerImage(e.target.files[0]);
$('#c3-img-seuil').oninput = e => $('#v-c3-seuil').textContent = +e.target.value || 'auto';
async function convertirImage(placer = { x: 0, y: 0 }) {
  if (!imageId) return toast('Choisis une image');
  const mode = $('#c3-img-mode').value, s = +$('#c3-img-seuil').value;
  const params = { largeur: +$('#c3-img-l').value, socle: $('#c3-img-socle').value, seuil: s || null, inverser: $('#c3-img-inv').checked ? true : null };
  try {
    $('#c3-info').textContent = 'Conversion image -> 3D...';
    const r = await api('/api/c3d/image', { image: imageId, mode, params });
    const o = await ajouterObjet({ type: 'image', params: { mode, ...params }, fichier: r.fichier, nom: mode }, { placer });
    selectionner([o]); memo();
    if (mode === 'lithophanie') toast('Lithophanie : imprime-la DEBOUT (Orienter), en blanc, remplissage 100 %');
  } catch (e) { toast(e.message); }
}
$('#c3-img-add').onclick = () => convertirImage();

// import STL / OBJ / 3MF
async function importer(f, placer = { x: 0, y: 0 }) {
  if (f.size > 80e6) return toast('Fichier trop lourd (80 Mo max)');
  $('#c3-info').textContent = `Import de ${f.name}...`;
  const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(f); });
  try {
    const r = await api('/api/c3d/importer', { data, nom: f.name.replace(/[^\w\- .()]/g, '_') });
    const o = await ajouterObjet({ type: 'import', fichier: r.fichier, nom: f.name }, { placer });
    selectionner([o]); memo();
    if (!r.analyse.etanche) toast('Maillage non etanche : clique Reparer');
  } catch (e) { toast(e.message); }
}
$('#c3-import').onchange = e => e.target.files[0] && importer(e.target.files[0]);

// ------------------------------------------------------------------ actions de la barre
async function dupliquer() {
  if (!C.sel.length) return;
  const n = [];
  for (const o of C.sel) { const s = serial(o); n.push(await ajouterObjet({ ...s, id: undefined, matrice: s.matrice })); }
  for (const o of n) o.mesh.position.x += (+$('#c3-snap').value || 1) * 5;     // decale pour la voir
  selectionner(n); memo();
}
function supprimer() { for (const o of C.sel) retirer(o); selectionner([]); memo(); }
async function remplacer(anciens, r, opts = {}) {
  const res = [];
  for (const [k, x] of (r.objets || []).entries()) {
    const o = await ajouterObjet({ type: opts.type || 'groupe', fichier: x.fichier, nom: opts.nom?.(x, k) || x.nom, bobine: anciens.find(a => !a.trou)?.bobine,
      enfants: opts.enfants || null });
    res.push(o);
  }
  if (!opts.garder) for (const o of anciens) retirer(o);
  if (opts.poser) for (const o of res) { const b = boite([o]); o.mesh.position.z -= b.min.z; }
  if (opts.etaler) {               // morceaux / chevilles cote a cote pour les voir
    let x = boite(res).max.x;
    res.forEach((o, i) => { if (i === 0) return; const b = boite([o]); o.mesh.position.x += (x + 8 - b.min.x) - 0; x = boite([o]).max.x; o.mesh.position.z -= boite([o]).min.z; });
  }
  selectionner(res); memo(); return res;
}
async function outil(nom, params = {}, opts = {}) {
  if (!C.sel.length) return toast('Selectionne d\'abord un objet');
  $('#c3-info').textContent = `${nom}...`; document.body.style.cursor = 'progress';
  try { const r = await api('/api/c3d/outil', { outil: nom, objets: C.sel.map(pourServeur), params }); await remplacer([...C.sel], r, opts); return r; }
  catch (e) { toast(e.message); }
  finally { document.body.style.cursor = ''; }
}
async function grouper() {
  if (C.sel.length < 2) return toast('Selectionne au moins 2 objets (Maj+clic)');
  const enfants = C.sel.map(serial);
  await outil('grouper', {}, { enfants, nom: () => 'groupe' });
}
async function degrouper() {
  const g = C.sel.filter(o => o.enfants); if (!g.length) return toast('Ce n\'est pas un groupe');
  const n = [];
  for (const o of g) { for (const s of o.enfants) n.push(await ajouterObjet({ ...s, id: undefined })); retirer(o); }
  selectionner(n); memo();
}
function poser() { for (const o of C.sel) { const b = boite([o]); o.mesh.position.z -= b.min.z; } finirEdition(); }
function centrer() { const b = boite(C.sel), c = b.getCenter(new THREE.Vector3()); for (const o of C.sel) { o.mesh.position.x -= c.x; o.mesh.position.y -= c.y; } finirEdition(); }
function basculerTrou() { for (const o of C.sel) { o.trou = !o.trou; o.mesh.castShadow = !o.trou; } selectionner(C.sel); memo(); }
const ACTIONS = { arete: () => modeArete(), integrer: () => integrer(), annuler, refaire, dupliquer, supprimer, grouper, degrouper, poser, centrer, trou: basculerTrou,
  mesure: () => { C.mesure = C.mesure ? null : { pts: [] }; $('[data-c3="mesure"]').classList.toggle('on', !!C.mesure); if (!C.mesure) { $('#c3-mesure').hidden = true; if (regle) scene.remove(regle); } else toast('Regle : clique 2 points'); },
  surplombs: () => { C.surplombs = !C.surplombs; $('[data-c3="surplombs"]').classList.toggle('on', C.surplombs);
    for (const o of C.objets) { if (C.surplombs) colorerSurplombs(o.mesh); o.mesh.material = materiau(o, C.sel.includes(o)); }
    if (C.surplombs) toast('En rouge : surplombs > 45 deg (supports necessaires). Essaie Orienter auto.'); } };
$$('[data-c3]').forEach(b => b.onclick = () => ACTIONS[b.dataset.c3]());


// ------------------------------------------------------------------ panneaux d'outils (remplacent les prompts)
// panneau(titre, champs, {appliquer, changer, fermer}) : champs = [{k, label, type, val, min, max, step, options, aide}]
let _pan = null;
function panneau(titre, champs, cb) {
  fermerPanneau();
  const d = document.createElement('div'); d.className = 'c3d-pan';
  const ligne = c => {
    if (c.type === 'select') return `<label>${c.label}<select data-k="${c.k}">${c.options.map(([v, l]) => `<option value="${v}" ${v == c.val ? 'selected' : ''}>${l}</option>`).join('')}</select></label>`;
    if (c.type === 'check') return `<label class="chk"><input type="checkbox" data-k="${c.k}" ${c.val ? 'checked' : ''}> ${c.label}</label>`;
    if (c.type === 'range') return `<label>${c.label} <b data-v="${c.k}">${c.val}</b>${c.unite || ''}<input type="range" data-k="${c.k}" min="${c.min}" max="${c.max}" step="${c.step || 0.1}" value="${c.val}"></label>`;
    if (c.type === 'texte') return `<label>${c.label}<input data-k="${c.k}" value="${c.val ?? ''}"></label>`;
    if (c.type === 'info') return `<p class="mute" data-info="${c.k}">${c.val}</p>`;
    return `<label>${c.label}<input type="number" data-k="${c.k}" value="${c.val}" ${c.min != null ? `min="${c.min}"` : ''} ${c.max != null ? `max="${c.max}"` : ''} step="${c.step || 'any'}"></label>`;
  };
  d.innerHTML = `<div class="tete"><b>${titre}</b><button class="x" title="Fermer (Echap)">&#10005;</button></div>
    <div class="corps">${champs.map(c => ligne(c) + (c.aide ? `<p class="mute aide">${c.aide}</p>` : '')).join('')}</div>
    <div class="pied"><button class="annul">Annuler</button><button class="primary ok">${cb.libelle || 'Appliquer'}</button></div>`;
  $('.c3d-stage').appendChild(d);
  const vals = () => Object.fromEntries([...d.querySelectorAll('[data-k]')].map(i => [i.dataset.k, i.type === 'checkbox' ? i.checked : (i.type === 'number' || i.type === 'range') ? +i.value : i.value]));
  const changer = () => { d.querySelectorAll('[data-v]').forEach(b => b.textContent = d.querySelector(`[data-k="${b.dataset.v}"]`).value); cb.changer?.(vals(), d); };
  d.querySelectorAll('[data-k]').forEach(i => i.addEventListener('input', changer));
  const ok = async () => { const v = vals(); const b = d.querySelector('.ok'); b.disabled = true; b.textContent = 'Calcul...'; fermerPanneau(true); await cb.appliquer(v); };
  d.querySelector('.ok').onclick = ok;
  d.querySelector('.annul').onclick = () => fermerPanneau(); d.querySelector('.x').onclick = () => fermerPanneau();
  d.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); ok(); } if (e.key === 'Escape') fermerPanneau(); e.stopPropagation(); });
  _pan = { d, cb }; changer();
  d.querySelector('[data-k]')?.focus();
}
function fermerPanneau(applique) { if (!_pan) return; _pan.cb.fermer?.(applique); _pan.d.remove(); _pan = null; }
const fantomes = new THREE.Group(); scene.add(fantomes);
function viderFantomes() { for (const c of [...fantomes.children]) { fantomes.remove(c); c.geometry?.dispose?.(); } }
const matFantome = new THREE.MeshBasicMaterial({ color: 0xff7a2f, transparent: true, opacity: 0.25, depthWrite: false });

// outils du panneau droit
function aligner(ax) {
  if (C.sel.length < 2) return toast('Selectionne au moins 2 objets');
  const ref = boite([C.sel[0]]);
  for (const o of C.sel.slice(1)) { const b = boite([o]); if (ax === 'z') o.mesh.position.z += ref.min.z - b.min.z; else o.mesh.position[ax] += ref.getCenter(new THREE.Vector3())[ax] - b.getCenter(new THREE.Vector3())[ax]; }
  finirEdition();
}
function miroir(ax) {
  const b = boite(C.sel), c = b.getCenter(new THREE.Vector3());
  const M = new THREE.Matrix4().makeTranslation(c.x, c.y, c.z).multiply(new THREE.Matrix4().makeScale(ax === 'x' ? -1 : 1, ax === 'y' ? -1 : 1, ax === 'z' ? -1 : 1)).multiply(new THREE.Matrix4().makeTranslation(-c.x, -c.y, -c.z));
  for (const o of C.sel) { o.mesh.updateMatrixWorld(); M.clone().multiply(o.mesh.matrixWorld).decompose(o.mesh.position, o.mesh.quaternion, o.mesh.scale); }
  finirEdition();
}
function matsReseau(v, o) {
  const b = boite([o]), c = b.getCenter(new THREE.Vector3()), out = [];
  const n = Math.max(2, Math.min(200, v.n | 0));
  if (v.type === 'ligne') for (let i = 1; i < n; i++) out.push(new THREE.Matrix4().makeTranslation(v.dx * i, v.dy * i, v.dz * i));
  else if (v.type === 'grille') { for (let i = 0; i < n; i++) for (let j = 0; j < Math.max(1, v.n2 | 0); j++) if (i || j) out.push(new THREE.Matrix4().makeTranslation(v.dx * i, v.dy * j, 0)); }
  else {                                     // cercle autour d'un centre a `rayon` mm a gauche de l'objet
    const cx = c.x - v.rayon, cy = c.y, tot = THREE.MathUtils.degToRad(v.angle), pas = v.angle >= 360 ? tot / n : tot / (n - 1);
    for (let i = 1; i < n; i++) {
      const R = new THREE.Matrix4().makeTranslation(cx, cy, 0).multiply(new THREE.Matrix4().makeRotationZ(pas * i)).multiply(new THREE.Matrix4().makeTranslation(-cx, -cy, 0));
      if (!v.tourner) { const p = c.clone().applyMatrix4(R); R.makeTranslation(p.x - c.x, p.y - c.y, 0); }
      out.push(R);
    }
  }
  return out;
}
function reseau() {
  if (C.sel.length !== 1) return toast('Selectionne UN objet');
  const o = C.sel[0], t = boite([o]).getSize(new THREE.Vector3());
  const apercu = v => {
    viderFantomes(); o.mesh.updateMatrixWorld();
    for (const M of matsReseau(v, o).slice(0, 200)) { const g = new THREE.Mesh(o.mesh.geometry, matFantome); M.clone().multiply(o.mesh.matrixWorld).decompose(g.position, g.quaternion, g.scale); fantomes.add(g); }
  };
  panneau('Reseau de copies', [
    { k: 'type', label: 'Disposition', type: 'select', val: 'ligne', options: [['ligne', 'En ligne'], ['grille', 'En grille'], ['cercle', 'En cercle']] },
    { k: 'n', label: 'Nombre (total)', val: 4, min: 2, max: 200, step: 1 },
    { k: 'n2', label: 'Rangees (grille)', val: 2, min: 1, max: 50, step: 1 },
    { k: 'dx', label: 'Pas X (mm)', val: r2(t.x + 5) }, { k: 'dy', label: 'Pas Y (mm)', val: r2(t.y + 5) }, { k: 'dz', label: 'Pas Z (mm)', val: 0 },
    { k: 'rayon', label: 'Rayon du cercle (mm)', val: r2(Math.max(t.x, t.y) * 1.5) }, { k: 'angle', label: 'Angle total (deg)', val: 360 },
    { k: 'tourner', label: 'Tourner les copies avec le cercle', type: 'check', val: true },
  ], {
    changer: apercu, fermer: viderFantomes,
    appliquer: async v => {
      const s0 = serial(o), res = [o];
      for (const M of matsReseau(v, o)) { const m = await ajouterObjet({ ...s0, id: undefined }); M.clone().multiply(new THREE.Matrix4().fromArray(s0.matrice)).decompose(m.mesh.position, m.mesh.quaternion, m.mesh.scale); m.mesh.updateMatrixWorld(); res.push(m); }
      selectionner(res); memo();
    },
  });
}
const OUTILS = {
  aligner_x: () => aligner('x'), aligner_y: () => aligner('y'), aligner_z: () => aligner('z'),
  miroir_x: () => miroir('x'), miroir_y: () => miroir('y'), miroir_z: () => miroir('z'),
  intersection: () => C.sel.length < 2 ? toast('Selectionne au moins 2 objets') : outil('intersection'),
  reseau,
  couper: () => {
    if (C.sel.length !== 1) return toast('Selectionne UN objet');
    const bx = boite(C.sel), c = bx.getCenter(new THREE.Vector3());
    const plan = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: 0xff7a2f, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }));
    const champs = ax => ({ k: 'position', label: `Position du plan (${ax}, mm)`, type: 'range', min: r2(bx.min[ax]) + 0.2, max: r2(bx.max[ax]) - 0.2, step: 0.1, val: r2(c[ax]) });
    panneau('Couper au plan', [
      { k: 'axe', label: 'Plan de coupe', type: 'select', val: 'z', options: [['z', 'Horizontal (Z)'], ['x', 'Vertical X'], ['y', 'Vertical Y']] },
      champs('z'),
      { k: 'connecteur', label: 'Assemblage', type: 'select', val: 'tenons', options: [['tenons', 'Tenons (chevilles a imprimer)'], ['queue_aronde', 'Queue d\'aronde (glisse, sans colle)'], ['clips', 'Clips (s\'enclipse, sans colle)'], ['aucun', 'Aucun (coupe simple)']] },
      { k: 'd_tenon', label: 'Diametre tenon / clip (mm)', val: 4, min: 2, max: 12, step: 0.5 },
      { k: 'l_tenon', label: 'Longueur des tenons (mm)', val: 10, min: 4, max: 30, step: 1 },
      { k: 'info', type: 'info', val: 'Jeu de 0.15 mm partout. Tenons : chevilles a cote. Queue d\'aronde : la moitie du haut glisse dans celle du bas selon la longueur. Clips : tige fendue a bourrelet.' },
    ], {
      changer: (v, d) => {
        const ax = v.axe, r = d.querySelector('[data-k="position"]');
        if (r.dataset.ax !== ax) { r.dataset.ax = ax; r.min = r2(bx.min[ax]) + 0.2; r.max = r2(bx.max[ax]) - 0.2; r.value = r2(c[ax]); d.querySelector('[data-v="position"]').textContent = r.value; r.closest('label').firstChild.textContent = `Position du plan (${ax}, mm) `; }
        const t = bx.getSize(new THREE.Vector3()).multiplyScalar(1.25), p = +r.value;
        plan.rotation.set(0, 0, 0);
        if (ax === 'z') { plan.scale.set(t.x, t.y, 1); plan.position.set(c.x, c.y, p); }
        if (ax === 'x') { plan.rotation.y = Math.PI / 2; plan.scale.set(t.z, t.y, 1); plan.position.set(p, c.y, c.z); }
        if (ax === 'y') { plan.rotation.x = Math.PI / 2; plan.scale.set(t.x, t.z, 1); plan.position.set(c.x, p, c.z); }
        if (!plan.parent) fantomes.add(plan);
      },
      fermer: viderFantomes,
      appliquer: v => outil('couper', v, { poser: true, etaler: true, nom: (x, k) => x.nom + ' ' + (k + 1) }),
    });
  },
  decouper_plateau: () => outil('decouper_plateau', {}, { poser: true, etaler: true }),
  orienter: async () => { const r = await outil('orienter', {}, { poser: true }); if (r) toast(`Orientation optimale : ${r2(r.surplombs_mm2 / 100)} cm2 de surplombs restants`); },
  arrondir: () => panneau('Arrondir toutes les aretes', [
    { k: 'r', label: 'Rayon', type: 'range', min: 0.3, max: 10, step: 0.1, val: 1.5, unite: ' mm' },
    { k: 'i', type: 'info', val: 'Toutes les aretes saillantes sont arrondies d\'un coup. Les details plus fins que 2x le rayon disparaissent.' },
  ], { appliquer: v => outil('arrondir', v, { poser: true }) }),
  coque: () => panneau('Creuser (coque)', [
    { k: 'paroi', label: 'Epaisseur de paroi', type: 'range', min: 0.8, max: 8, step: 0.1, val: 2, unite: ' mm' },
    { k: 'ouverture', label: 'Trou d\'evacuation au fond (d 5 mm)', type: 'check', val: false },
    { k: 'i', type: 'info', val: 'Paroi constante partout : moins de matiere et de temps (ideal pour les grosses pieces, lampes, tirelires).' },
  ], { appliquer: v => outil('coque', v) }),
  epaissir: () => panneau('Epaissir / gonfler', [
    { k: 'e', label: 'Epaisseur ajoutee', type: 'range', min: 0.2, max: 10, step: 0.1, val: 1, unite: ' mm' },
  ], { appliquer: v => outil('epaissir', v, { poser: true }) }),
  effet: () => effetSurface(),
  ajourer: () => panneau('Ajourer (motif traversant)', [
    { k: 'motif', label: 'Motif des trous', type: 'select', val: 'alveoles', options: [['alveoles', "Nid d'abeille"], ['cercles', 'Cercles'], ['gaufre', 'Grille carree'], ['triangles', 'Triangles'], ['voronoi', 'Cellules organiques'], ['briques', 'Briques'], ['fentes', 'Fentes'], ['diamant', 'Losanges'], ['ecailles', 'Ecailles']] },
    { k: 'axe', label: 'Direction', type: 'select', val: 'cylindre', options: [['cylindre', 'Tout autour (objet rond : abat-jour, pot)'], ['z', 'De haut en bas (Z)'], ['x', 'De cote (X)'], ['y', 'De face (Y)']] },
    { k: 'taille', label: 'Taille des cellules', type: 'range', min: 1.5, max: 40, step: 0.5, val: 8, unite: ' mm' },
    { k: 'trait', label: 'Epaisseur des parois', type: 'range', min: 0.04, max: 0.4, step: 0.01, val: 0.12 },
    { k: 'rotation', label: 'Rotation', type: 'range', min: -90, max: 90, step: 1, val: 0, unite: ' deg' },
    { k: 'etirement', label: 'Etirement', type: 'range', min: 0.3, max: 3, step: 0.05, val: 1 },
    { k: 'alea', label: 'Irregularite (cellules)', type: 'range', min: 0, max: 1, step: 0.05, val: 0.85 },
    { k: 'bas', label: 'Commence a (rond)', type: 'range', min: 0, max: 90, step: 1, val: 10, unite: ' %' },
    { k: 'haut', label: "S'arrete a (rond)", type: 'range', min: 10, max: 100, step: 1, val: 90, unite: ' %' },
    { k: 'i', type: 'info', val: 'Les trous traversent la piece. Sur un objet creux (tube, pot creuse), ideal pour lampes et diffuseurs RGB. Ctrl+Z pour revenir.' },
  ], { appliquer: v => outil('ajourer', v) }),
  lisser: () => outil('lisser'), simplifier: () => outil('simplifier', { ratio: 0.5 }), reparer: () => outil('reparer'),
};
$$('[data-o]').forEach(b => b.onclick = () => OUTILS[b.dataset.o]());

// ------------------------------------------------------------------ analyse (poids, cout, surplombs)
let _tA = null;
function analyserBientot() { clearTimeout(_tA); _tA = setTimeout(analyser, 500); }
async function analyser() {
  const liste = (C.sel.length ? C.sel : C.objets);
  if (!liste.length) { $('#c3-analyse').innerHTML = '-'; return; }
  try {
    const { analyse: a } = await api('/api/c3d/outil', { outil: 'analyser', objets: liste.map(pourServeur) });
    $('#c3-analyse').innerHTML = `<div class="c3d-ana"><span>Dimensions</span><b>${a.dimensions_mm.map(v => r2(v)).join(' x ')}</b>
      <span>Volume</span><b>${a.volume_cm3} cm3</b><span>Poids estime</span><b>${a.poids_g} g</b><span>Matiere</span><b>${a.cout_matiere_eur.toFixed(2)} EUR</b>
      <span>Surplombs</span><b class="${a.surplombs_pct > 8 ? 'bad' : ''}">${a.surplombs_cm2} cm2 (${a.surplombs_pct} %)</b>
      <span>Plateau</span><b>${a.tient_plateau ? 'tient' : 'TROP GRAND'}</b><span>Maillage</span><b>${a.etanche ? 'etanche' : 'a reparer'}</b>
      <span>Triangles</span><b>${a.triangles.toLocaleString()}</b></div>
      <p class="mute">${C.sel.length ? 'Selection' : 'Tout le plateau'} - estimation, le tranchage donne le chiffre exact.</p>`;
  } catch (e) { $('#c3-analyse').textContent = e.message; }
}

// ------------------------------------------------------------------ projet / export / impression
$('#c3-sauver').onclick = () => window.__PROJETS?.enregistrer('creation3d');
$('#c3-ouvrir').onclick = () => $('[data-tab="pj"]').click();
$('#c3-vider').onclick = () => C.objets.length && panneau('Tout effacer ?', [{ k: 'i', type: 'info', val: `${C.objets.length} objet(s) seront retires du plateau (Ctrl+Z pour revenir).` }],
  { libelle: 'Effacer', appliquer: () => { for (const o of [...C.objets]) retirer(o); selectionner([]); memo(); } });
$('#c3-export').onclick = async () => {
  const l = (C.sel.length ? C.sel : C.objets); if (!l.length) return;
  try { const r = await api('/api/c3d/exporter', { outil: 'exporter', objets: l.map(pourServeur) }); const a = document.createElement('a'); a.href = r.url; a.download = 'creation.stl'; a.click(); } catch (e) { toast(e.message); }
};
$('#c3-imprimer').onclick = async () => {
  const sol = C.objets.filter(o => !o.trou);
  if (!sol.length) return toast('Rien a imprimer');
  if (C.objets.some(o => o.trou) && !C._okTrous) return panneau('Percages non groupes', [{ k: 'i', type: 'info', val: 'Des percages ne sont pas groupes avec un solide : ils seront ignores. Selectionne le solide + le percage puis Ctrl+G pour percer.' }],
    { libelle: 'Imprimer quand meme', appliquer: () => { C._okTrous = true; $('#c3-imprimer').click(); C._okTrous = false; } });
  try {
    const { job } = await api('/api/c3d/imprimer', { outil: 'imprimer', objets: C.objets.map(pourServeur) });
    await A().suivre(job, '#c3-prog', res => {
      const S = A().S; S.gen = res; S.tranches = {};
      A().renderPlateauxImp(); toast(`${res.plateaux.length} plateau(x) prets : onglet Imprimer`);
      $('[data-tab="imprimer"]').click();
    });
  } catch (e) { toast(e.message); }
};


// ------------------------------------------------------------------ GENERATEURS (vase, pot, keycap, bouton, support, shadowbox)
const GEN = {
  vase: { titre: 'Vase', champs: [
    { k: 'h', label: 'Hauteur', type: 'range', min: 30, max: 240, step: 1, val: 120, unite: ' mm' },
    { k: 'r_bas', label: 'Rayon du pied', type: 'range', min: 10, max: 100, step: 1, val: 30, unite: ' mm' },
    { k: 'r_ventre', label: 'Rayon du ventre', type: 'range', min: 10, max: 105, step: 1, val: 45, unite: ' mm' },
    { k: 'pos_ventre', label: 'Hauteur du ventre', type: 'range', min: 0.1, max: 0.7, step: 0.05, val: 0.35 },
    { k: 'r_col', label: 'Rayon du col', type: 'range', min: 5, max: 100, step: 1, val: 22, unite: ' mm' },
    { k: 'r_haut', label: 'Rayon de l\'ouverture', type: 'range', min: 5, max: 105, step: 1, val: 32, unite: ' mm' },
    { k: 'cotes', label: 'Section', type: 'select', val: 0, options: [[0, 'Ronde'], [3, 'Triangle'], [4, 'Carree'], [5, 'Pentagone'], [6, 'Hexagone'], [8, 'Octogone'], [12, '12 cotes']] },
    { k: 'torsion', label: 'Torsion', type: 'range', min: -360, max: 360, step: 5, val: 0, unite: ' deg' },
    { k: 'ondulation', label: 'Ondulations', type: 'range', min: 0, max: 15, step: 0.5, val: 0, unite: ' %' },
    { k: 'ondes', label: 'Nombre d\'ondes', type: 'range', min: 2, max: 30, step: 1, val: 8 },
    { k: 'paroi', label: 'Paroi (0 = plein, a imprimer en MODE VASE)', type: 'range', min: 0, max: 5, step: 0.2, val: 0, unite: ' mm' },
  ] },
  pot: { titre: 'Pot + soucoupe', champs: [
    { k: 'h', label: 'Hauteur', type: 'range', min: 40, max: 200, step: 1, val: 90, unite: ' mm' },
    { k: 'r_bas', label: 'Rayon du fond', type: 'range', min: 20, max: 90, step: 1, val: 35, unite: ' mm' },
    { k: 'r_haut', label: 'Rayon du haut', type: 'range', min: 20, max: 100, step: 1, val: 48, unite: ' mm' },
    { k: 'cotes', label: 'Section', type: 'select', val: 0, options: [[0, 'Ronde'], [6, 'Hexagone'], [8, 'Octogone']] },
    { k: 'torsion', label: 'Torsion', type: 'range', min: -180, max: 180, step: 5, val: 0, unite: ' deg' },
    { k: 'ondulation', label: 'Ondulations', type: 'range', min: 0, max: 10, step: 0.5, val: 0, unite: ' %' },
    { k: 'paroi', label: 'Paroi', type: 'range', min: 1.2, max: 5, step: 0.2, val: 2.4, unite: ' mm' },
  ], prep: v => ({ ...v, r_ventre: (v.r_bas * 2 + v.r_haut) / 3, r_col: (v.r_bas + v.r_haut * 2) / 3 }) },
  keycap: { titre: 'Touche de clavier (Cherry MX)', champs: [
    { k: 'u', label: 'Largeur', type: 'select', val: 1, options: [[1, '1u (lettre)'], [1.25, '1.25u (Ctrl, Alt)'], [1.5, '1.5u (Tab)'], [1.75, '1.75u (Maj lock)'], [2, '2u (Retour, Maj)'], [2.25, '2.25u (Entree)'], [6.25, '6.25u (Espace)']] },
    { k: 'h_avant', label: 'Hauteur avant', type: 'range', min: 5, max: 14, step: 0.1, val: 8, unite: ' mm' },
    { k: 'h_arriere', label: 'Hauteur arriere', type: 'range', min: 5, max: 14, step: 0.1, val: 9.5, unite: ' mm' },
    { k: 'dish', label: 'Creux du dessus', type: 'range', min: 0, max: 2, step: 0.1, val: 0.8, unite: ' mm' },
    { k: 'jeu', label: 'Jeu de la croix MX', type: 'range', min: 0, max: 0.2, step: 0.01, val: 0.05, unite: ' mm' },
    { k: 'i', type: 'info', val: 'Astuce : ajoute un texte et INTEGRE-le (mode incruster) sur le dessus = legende 2 couleurs.' },
  ] },
  bouton: { titre: 'Bouton de couture', champs: [
    { k: 'd', label: 'Diametre', type: 'range', min: 8, max: 50, step: 0.5, val: 20, unite: ' mm' },
    { k: 'e', label: 'Epaisseur', type: 'range', min: 1.5, max: 6, step: 0.1, val: 3, unite: ' mm' },
    { k: 'trous', label: 'Trous', type: 'select', val: 4, options: [[2, '2 trous'], [4, '4 trous']] },
    { k: 'd_trou', label: 'Diametre des trous', type: 'range', min: 1, max: 4, step: 0.1, val: 2, unite: ' mm' },
  ] },
  support_tel: { titre: 'Support telephone / tablette', champs: [
    { k: 'largeur', label: 'Largeur', type: 'range', min: 30, max: 180, step: 1, val: 70, unite: ' mm' },
    { k: 'angle', label: 'Inclinaison', type: 'range', min: 45, max: 80, step: 1, val: 65, unite: ' deg' },
    { k: 'appareil', label: 'Epaisseur de l\'appareil (+ coque)', type: 'range', min: 6, max: 20, step: 0.5, val: 12, unite: ' mm' },
    { k: 'epaisseur', label: 'Epaisseur du support', type: 'range', min: 3, max: 8, step: 0.5, val: 4, unite: ' mm' },
  ] },
};
function xLibre(larg) {        // place un nouvel objet a droite de ce qui existe deja (sans chevauchement)
  const autres = C.objets.filter(o => !o.trou); if (!autres.length) return 0;
  return boite(autres).max.x + 8 + larg / 2;
}
function ouvrirGen(nom) {
  if (nom === 'dessin') return ouvrirDessin();
  if (nom === 'shadowbox') return ouvrirShadowbox();
  if (nom === 'vase') return ouvrirVase();
  if (nom === 'logo') return ouvrirLogo();
  const G = GEN[nom];
  panneau(G.titre, G.champs.map(c => ({ ...c })), {
    libelle: 'Creer',
    appliquer: async v => {
      const p = G.prep ? G.prep(v) : v;
      try {
        $('#c3-info').textContent = `Generation : ${G.titre}...`;
        const r = await api('/api/c3d/generer', { nom, params: p });
        const nouv = [];
        for (const [i, x] of r.objets.entries()) nouv.push(await ajouterObjet({ type: 'gen_' + nom, params: p, fichier: x.fichier, nom: i ? 'soucoupe' : G.titre }, { placer: { x: xLibre(x.analyse.dimensions_mm[0]), y: 0 } }));
        selectionner(nouv); memo(); vue('iso');
        if (nom === 'vase' && !p.paroi) toast('Vase plein : tranche-le en MODE VASE (1 paroi spiralee) = rapide et etanche');
      } catch (e) { toast(e.message); }
    },
  });
}
$$('[data-gen]').forEach(b => b.onclick = () => ouvrirGen(b.dataset.gen));
// ------------------------------------------------------------------ LOGO SHWork : objet en relief, a poser sur une surface (Integrer)
function ouvrirLogo() {
  panneau('Logo SHWork', [
    { k: 'partie', label: 'Contenu', type: 'select', val: 'mot', options: [['mot', 'SHWork'], ['tout', 'SHWork + SUPER HIGH WORK'], ['slogan', 'SUPER HIGH WORK seul']] },
    { k: 'largeur', label: 'Largeur', type: 'range', min: 8, max: 200, step: 1, val: 40, unite: ' mm' },
    { k: 'epaisseur', label: 'Relief', type: 'range', min: 0.4, max: 5, step: 0.1, val: 1.2, unite: ' mm' },
    { k: 'socle', label: 'Socle (0 = sans)', type: 'range', min: 0, max: 4, step: 0.2, val: 0, unite: ' mm' },
    { k: 'i', type: 'info', val: 'Astuce : selectionne le logo puis la piece et utilise Integrer (relief, grave ou incruste 2 couleurs) : il epouse la surface.' },
  ], {
    libelle: 'Creer',
    appliquer: async v => {
      try {
        const r = await api('/api/c3d/logo', v);
        const n = await ajouterObjet({ type: 'logo', params: v, fichier: r.fichier, nom: 'Logo SHWork' }, { placer: { x: xLibre(r.analyse.dimensions_mm[0]), y: 0 } });
        selectionner([n]); memo();
      } catch (e) { toast(e.message); }
    },
  });
}

// ------------------------------------------------------------------ VASE : formes predefinies, profil a la souris, apercu 3D en direct, cartouche texte / logo
const VASES = {
  amphore: { nom: 'Amphore classique', h: 120, profil: [[0, 30], [0.35, 45], [0.8, 22], [1, 32]] },
  bouteille: { nom: 'Bouteille', h: 160, profil: [[0, 34], [0.5, 37], [0.72, 15], [1, 13]] },
  soliflore: { nom: 'Soliflore (une fleur)', h: 170, profil: [[0, 22], [0.18, 27], [0.6, 10], [1, 9]] },
  tulipe: { nom: 'Tulipe', h: 130, profil: [[0, 22], [0.25, 30], [0.7, 42], [1, 48]] },
  boule: { nom: 'Boule', h: 120, profil: [[0, 22], [0.45, 55], [0.9, 30], [1, 30]] },
  calebasse: { nom: 'Calebasse', h: 150, profil: [[0, 30], [0.25, 44], [0.55, 24], [0.75, 32], [1, 18]] },
  sablier: { nom: 'Sablier', h: 130, profil: [[0, 40], [0.5, 22], [1, 40]] },
  cylindre: { nom: 'Cylindre epure', h: 140, profil: [[0, 34], [1, 34]] },
  cone: { nom: 'Cone evase', h: 120, profil: [[0, 24], [1, 50]] },
  coupe: { nom: 'Coupe / bol', h: 70, profil: [[0, 24], [0.3, 46], [1, 62]] },
  lanterne: { nom: 'Lanterne cotelee', h: 150, profil: [[0, 36], [0.5, 40], [1, 36]], ondulation: 5, ondes: 16 },
  spirale: { nom: 'Spirale cotelee', h: 150, profil: [[0, 30], [0.35, 45], [0.8, 24], [1, 30]], ondulation: 7, ondes: 14, torsion: 150 },
  hexa: { nom: 'Hexagone torsade', h: 140, profil: [[0, 32], [0.5, 42], [1, 36]], cotes: 6, torsion: 120 },
  deco: { nom: 'Art deco (octogone)', h: 150, profil: [[0, 30], [0.15, 30], [0.85, 46], [1, 46]], cotes: 8 },
  galet: { nom: 'Galet bas', h: 80, profil: [[0, 40], [0.4, 60], [0.85, 30], [1, 26]] },
};
const VASE_DEF = { h: 120, paroi: 2, fond: 2.4, cotes: 0, torsion: 0, ondulation: 0, ondes: 8, perso: 'aucun', perso_support: 'vase', perso_texte: '', perso_police: 'bebas',
  perso_mode: 'relief', perso_cadre: 'ovale', perso_hauteur: 0.5, perso_taille: 34, perso_largeur: 52, perso_angle: 0, perso_relief: 0.8, perso_image: '' };

function ouvrirVase(cible = null) {
  const P = { ...VASE_DEF, profil: VASES.amphore.profil.map(a => [...a]), ...(cible?.params || {}) };
  if (!P.profil) P.profil = [[0, P.r_bas || 30], [P.pos_ventre || 0.35, P.r_ventre || 45], [0.8, P.r_col || 22], [1, P.r_haut || 32]];
  const polices = Object.entries(A().S.polices || {}).map(([k, p]) => [k, p.label]);
  let fant = null, nGen = 0, _t = null, place = null, pret = false;
  if (cible) { const b = boite([cible]); place = { x: b.getCenter(new THREE.Vector3()).x, y: b.getCenter(new THREE.Vector3()).y, z: b.min.z }; cible.mesh.visible = false; tc.detach(); }
  const apercu = () => {
    clearTimeout(_t);
    _t = setTimeout(async () => {
      const n = ++nGen;
      $('#c3-info').textContent = 'Apercu du vase...';
      try {
        const r = await api('/api/c3d/generer', { nom: 'vase', params: { ...P, apercu: true } });
        if (n !== nGen || !_pan) return;
        const g = (await geometrie(r.objets[0].fichier)).clone();
        if (fant) { scene.remove(fant); fant.traverse(c => c.geometry?.dispose?.()); }
        fant = new THREE.Group();
        const mv = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0xf2efe9, roughness: 0.5, transparent: true, opacity: 0.9 }));
        mv.castShadow = true; fant.add(mv);
        for (const x of r.objets.slice(1)) {          // plaque clipsable : meme repere que le vase
          const m2 = new THREE.Mesh((await geometrie(x.fichier)).clone(), new THREE.MeshStandardMaterial({ color: 0xc9a227, roughness: 0.4 }));
          m2.castShadow = true; fant.add(m2);
        }
        g.computeBoundingBox(); const bb = g.boundingBox;
        const pl = place || { x: xLibre(bb.max.x - bb.min.x), y: 0, z: 0 }; place = pl;
        fant.position.set(pl.x - (bb.min.x + bb.max.x) / 2, pl.y - (bb.min.y + bb.max.y) / 2, pl.z - bb.min.z);
        scene.add(fant);
        const a = r.objets[0].analyse;
        $('#c3-info').textContent = `Vase ${a.dimensions_mm.map(v => r2(v)).join(' x ')} mm - ${a.poids_g} g - ${P.paroi > 0 ? 'paroi ' + P.paroi + ' mm' : 'PLEIN (mode vase du slicer)'}`;
      } catch (e) { $('#c3-info').textContent = e.message; }
    }, 260);
  };
  const preset = cible ? '' : 'amphore';
  panneau(cible ? 'Modifier le vase' : 'Vase', [
    { k: 'preset', label: 'Forme predefinie', type: 'select', val: preset, options: [['', '(forme actuelle)'], ...Object.entries(VASES).map(([k, v]) => [k, v.nom])] },
    { k: 'i_prof', type: 'info', val: '' },
    { k: 'h', label: 'Hauteur', type: 'range', min: 30, max: 240, step: 1, val: P.h, unite: ' mm' },
    { k: 'paroi', label: 'Epaisseur de paroi (0 = plein, MODE VASE du slicer)', type: 'range', min: 0, max: 6, step: 0.2, val: P.paroi, unite: ' mm' },
    { k: 'fond', label: 'Epaisseur du fond', type: 'range', min: 0.8, max: 8, step: 0.2, val: P.fond, unite: ' mm' },
    { k: 'cotes', label: 'Section', type: 'select', val: P.cotes, options: [[0, 'Ronde'], [3, 'Triangle'], [4, 'Carree'], [5, 'Pentagone'], [6, 'Hexagone'], [8, 'Octogone'], [12, '12 cotes']] },
    { k: 'torsion', label: 'Torsion', type: 'range', min: -360, max: 360, step: 5, val: P.torsion, unite: ' deg' },
    { k: 'ondulation', label: 'Cotes / ondulations', type: 'range', min: 0, max: 15, step: 0.5, val: P.ondulation, unite: ' %' },
    { k: 'ondes', label: "Nombre d'ondes", type: 'range', min: 2, max: 30, step: 1, val: P.ondes },
    { k: 'perso', label: 'Zone de personnalisation', type: 'select', val: P.perso, options: [['aucun', 'Aucune'], ['texte', 'Texte'], ['logo', 'Logo'], ['texte_logo', 'Logo + texte']] },
    { k: 'perso_support', label: 'Ou ?', type: 'select', val: P.perso_support, options: [['vase', 'Directement sur le vase'], ['plaque', 'Plaque amovible clipsee sur le bord (cadeau)']] },
    { k: 'perso_texte', label: 'Texte', type: 'texte', val: P.perso_texte },
    { k: 'perso_police', label: 'Police', type: 'select', val: P.perso_police, options: polices.length ? polices : [['bebas', 'Bebas Neue']] },
    { k: 'perso_cadre', label: 'Cartouche', type: 'select', val: P.perso_cadre, options: [['ovale', 'Medaillon ovale'], ['pastille', 'Pastille ronde'], ['bandeau', 'Bandeau'], ['aucun', 'Sans cadre']] },
    { k: 'perso_mode', label: 'Rendu', type: 'select', val: P.perso_mode, options: [['relief', 'En relief'], ['grave', 'Grave']] },
    { k: 'perso_hauteur', label: 'Position en hauteur', type: 'range', min: 0.12, max: 0.88, step: 0.01, val: P.perso_hauteur },
    { k: 'perso_angle', label: 'Position autour', type: 'range', min: -180, max: 180, step: 5, val: P.perso_angle, unite: ' deg' },
    { k: 'perso_taille', label: 'Hauteur du cartouche', type: 'range', min: 10, max: 90, step: 1, val: P.perso_taille, unite: ' mm' },
    { k: 'perso_largeur', label: 'Largeur du cartouche', type: 'range', min: 15, max: 140, step: 1, val: P.perso_largeur, unite: ' mm' },
    { k: 'perso_relief', label: 'Relief / profondeur', type: 'range', min: 0.3, max: 2, step: 0.1, val: P.perso_relief, unite: ' mm' },
  ], {
    libelle: cible ? 'Appliquer' : 'Creer',
    changer: v => {
      if (!pret) return;
      if (v.preset && v.preset !== P._preset) {        // forme predefinie : remplace le profil et les reglages de style
        const s = VASES[v.preset]; P._preset = v.preset;
        P.profil = s.profil.map(a => [...a]); P.h = s.h; P.cotes = s.cotes || 0; P.torsion = s.torsion || 0; P.ondulation = s.ondulation || 0; P.ondes = s.ondes || 8;
        const d = _pan.d; for (const k of ['h', 'cotes', 'torsion', 'ondulation', 'ondes']) { const i = d.querySelector(`[data-k="${k}"]`); i.value = P[k]; const b = d.querySelector(`[data-v="${k}"]`); if (b) b.textContent = P[k]; }
        dessiner();
      } else for (const [k, x] of Object.entries(v)) if (k !== 'preset') P[k] = x;
      const d = _pan?.d; if (d) {
        const avec = P.perso !== 'aucun';
        d.querySelectorAll('[data-k^="perso_"]').forEach(i => i.closest('label').style.display = avec ? '' : 'none');
        d.querySelector('[data-k="perso_texte"]').closest('label').style.display = /texte/.test(P.perso) ? '' : 'none';
        d.querySelector('[data-k="perso_police"]').closest('label').style.display = /texte/.test(P.perso) ? '' : 'none';
        d.querySelector('.vase-logo').style.display = /logo/.test(P.perso) ? '' : 'none';
      }
      dessiner(); apercu();
    },
    fermer: applique => { clearTimeout(_t); nGen++; if (fant) { scene.remove(fant); fant.traverse(c => c.geometry?.dispose?.()); } if (!applique && cible) { cible.mesh.visible = true; selectionner([cible]); } },
    appliquer: async () => {
      const p = { ...P }; delete p._preset; delete p.preset;
      try {
        $('#c3-info').textContent = 'Generation du vase...';
        const r = await api('/api/c3d/generer', { nom: 'vase', params: p });
        const x = r.objets[0];
        const ajouterPlaques = async n => {           // les plaques gardent leur position relative au vase (deja clipsees)
          const g0 = await geometrie(x.fichier); g0.computeBoundingBox();
          for (const y of r.objets.slice(1)) {
            const pq = await ajouterObjet({ type: 'piece', params: null, fichier: y.fichier, nom: 'Plaque clipsable' });
            pq.mesh.position.copy(n.mesh.position); pq.mesh.quaternion.copy(n.mesh.quaternion); pq.mesh.updateMatrixWorld();
          }
        };
        if (cible) {
          const s = serial(cible); retirer(cible);
          const n = await ajouterObjet({ ...s, id: undefined, fichier: x.fichier, params: p, matrice: null }, { placer: { x: place.x, y: place.y } });
          n.mesh.position.z += place.z; n.mesh.updateMatrixWorld(); await ajouterPlaques(n); selectionner([n]);
        } else {
          const n = await ajouterObjet({ type: 'gen_vase', params: p, fichier: x.fichier, nom: 'Vase' }, { placer: { x: place?.x ?? xLibre(x.analyse.dimensions_mm[0]), y: place?.y ?? 0 } });
          await ajouterPlaques(n); selectionner([n]); vue('iso');
        }
        memo();
        if (!p.paroi) toast('Vase plein : tranche-le en MODE VASE (1 paroi spiralee) = rapide et etanche');
      } catch (e) { toast(e.message); if (cible) cible.mesh.visible = true; }
    },
  });
  // ---- editeur de profil a la souris (demi-silhouette : glisser les points, double-clic = ajouter, clic droit = retirer)
  const d = _pan.d; d.querySelector('.corps').style.maxHeight = '66vh';
  const zone = d.querySelector('[data-info="i_prof"]');
  zone.className = 'vase-prof';
  zone.innerHTML = `<canvas width="300" height="260" style="width:100%;max-width:300px;display:block;margin:0 auto;border-radius:12px;background:#15171c;cursor:grab;touch-action:none"></canvas>
    <p class="mute" style="text-align:center;margin:6px 0 0">Glisse les points pour sculpter le profil - double-clic : ajouter - clic droit : retirer</p>`;
  const lab = document.createElement('div'); lab.className = 'vase-logo';
  lab.innerHTML = `<button class="ghost" style="width:100%">Choisir un logo (image)...</button><p class="mute" data-logo>${P.perso_image ? 'Logo charge' : 'Aucun logo'}</p>`;
  d.querySelector('[data-k="perso_cadre"]').closest('label').before(lab);
  lab.querySelector('button').onclick = () => {
    const f = document.createElement('input'); f.type = 'file'; f.accept = 'image/*';
    f.onchange = async () => {
      const fi = f.files[0]; if (!fi) return;
      const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(fi); });
      try { P.perso_image = (await api('/api/image', { data })).id; lab.querySelector('[data-logo]').textContent = fi.name; apercu(); } catch (e) { toast(e.message); }
    };
    f.click();
  };
  const cv = zone.querySelector('canvas'), ctx = cv.getContext('2d');
  const W = cv.width, Hc = cv.height, M = 18, RMAX = 110;
  const ech = () => Math.min((W / 2 - M) / RMAX * 1.0, (Hc - 2 * M) / Math.max(P.h, 60));
  const versEcran = ([t, r]) => { const k = ech(); return [W / 2 + r * k, Hc - M - t * P.h * k]; };
  const depuisEcran = (x, y) => { const k = ech(); return [Math.min(1, Math.max(0, (Hc - M - y) / (P.h * k))), Math.min(RMAX, Math.max(4, (x - W / 2) / k))]; };
  function profilDense() {          // interpolation monotone (meme famille que le serveur) pour le trace
    const pts = [...P.profil].sort((a, b) => a[0] - b[0]), out = [];
    for (let i = 0; i <= 80; i++) {
      const t = i / 80; let j = 0; while (j < pts.length - 2 && t > pts[j + 1][0]) j++;
      const [t0, r0] = pts[j], [t1, r1] = pts[Math.min(j + 1, pts.length - 1)];
      const u = t1 > t0 ? Math.min(1, Math.max(0, (t - t0) / (t1 - t0))) : 0, s = u * u * (3 - 2 * u);
      out.push([t, r0 + (r1 - r0) * s]);
    }
    return out;
  }
  function dessiner() {
    if (!cv.isConnected) return;
    ctx.clearRect(0, 0, W, Hc);
    const k = ech();
    ctx.strokeStyle = 'rgba(255,255,255,.06)'; ctx.lineWidth = 1;
    for (let r = 10; r <= RMAX; r += 10) { ctx.beginPath(); ctx.moveTo(W / 2 + r * k, M); ctx.lineTo(W / 2 + r * k, Hc - M); ctx.moveTo(W / 2 - r * k, M); ctx.lineTo(W / 2 - r * k, Hc - M); ctx.stroke(); }
    const pd = profilDense();
    // silhouette pleine (les deux moities) facon piece de porcelaine
    ctx.beginPath();
    pd.forEach(([t, r], i) => { const [x, y] = versEcran([t, r]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    [...pd].reverse().forEach(([t, r]) => { const [x, y] = versEcran([t, r]); ctx.lineTo(W - x, y); });
    ctx.closePath();
    const gr = ctx.createLinearGradient(0, 0, W, 0); gr.addColorStop(0, '#3a3d45'); gr.addColorStop(0.5, '#e9e4da'); gr.addColorStop(1, '#3a3d45');
    ctx.fillStyle = gr; ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1;
    if (P.paroi > 0) {             // paroi interieure
      ctx.beginPath(); ctx.strokeStyle = 'rgba(20,20,24,.55)'; ctx.setLineDash([4, 4]);
      pd.forEach(([t, r], i) => { if (t * P.h < P.fond) return; const [x, y] = versEcran([t, Math.max(1, r - P.paroi)]); ctx.lineTo(x, y); });
      ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.strokeStyle = '#ff7a2f'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(W / 2, M - 6); ctx.lineTo(W / 2, Hc - M + 4); ctx.stroke();
    if (P.perso !== 'aucun') {   // emplacement du cartouche
      const yc = Hc - M - P.perso_hauteur * P.h * k, hh = P.perso_taille * k / 2;
      ctx.fillStyle = 'rgba(255,122,47,.18)'; ctx.fillRect(W / 2 - 3, yc - hh, 6, 2 * hh);
    }
    for (const p of P.profil) { const [x, y] = versEcran(p); ctx.beginPath(); ctx.arc(x, y, 6, 0, 7); ctx.fillStyle = '#ff7a2f'; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.stroke(); }
  }
  let prise = -1;
  const pos = e => { const b = cv.getBoundingClientRect(); return [(e.clientX - b.left) * W / b.width, (e.clientY - b.top) * Hc / b.height]; };
  const proche = (x, y) => { let best = -1, dm = 14; P.profil.forEach((p, i) => { const [a, b] = versEcran(p); const dd = Math.hypot(a - x, b - y); if (dd < dm) { dm = dd; best = i; } }); return best; };
  cv.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    const [x, y] = pos(e); prise = proche(x, y);
    if (prise >= 0) { cv.setPointerCapture(e.pointerId); cv.style.cursor = 'grabbing'; P._preset = null; d.querySelector('[data-k="preset"]').value = ''; }
  });
  cv.addEventListener('pointermove', e => {
    const [x, y] = pos(e);
    if (prise < 0) { cv.style.cursor = proche(x, y) >= 0 ? 'grab' : 'crosshair'; return; }
    const pts = [...P.profil].sort((a, b) => a[0] - b[0]), p = P.profil[prise];
    let [t, r] = depuisEcran(x, y);
    if (p === pts[0]) t = 0; else if (p === pts[pts.length - 1]) t = 1;     // pied et ouverture restent aux extremites
    p[0] = t; p[1] = r; dessiner(); apercu();
  });
  cv.addEventListener('pointerup', () => { prise = -1; cv.style.cursor = 'grab'; });
  cv.addEventListener('dblclick', e => { const [x, y] = pos(e); const [t, r] = depuisEcran(x, y); if (t > 0.02 && t < 0.98) { P.profil.push([t, r]); P._preset = null; dessiner(); apercu(); } });
  cv.addEventListener('contextmenu', e => {
    e.preventDefault(); e.stopPropagation();
    const [x, y] = pos(e), i = proche(x, y), p = P.profil[i];
    const s = [...P.profil].sort((a, b) => a[0] - b[0]);
    if (i >= 0 && P.profil.length > 2 && p !== s[0] && p !== s[s.length - 1]) { P.profil.splice(i, 1); dessiner(); apercu(); }
  });
  if (preset) P._preset = 'amphore';
  pret = true;
  _pan.cb.changer(Object.fromEntries([...d.querySelectorAll('[data-k]')].map(i => [i.dataset.k, i.type === 'checkbox' ? i.checked : (i.type === 'range' || i.type === 'number') ? +i.value : i.value])));
}


function ouvrirShadowbox() {
  const choisir = document.createElement('input'); choisir.type = 'file'; choisir.accept = 'image/*';
  choisir.onchange = async () => {
    const f = choisir.files[0]; if (!f) return;
    const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(f); });
    const { id } = await api('/api/image', { data });
    panneau('Shadowbox (tableau en couches)', [
      { k: 'couches', label: 'Nombre de couches', type: 'range', min: 2, max: 8, step: 1, val: 5 },
      { k: 'largeur', label: 'Largeur', type: 'range', min: 40, max: 200, step: 5, val: 100, unite: ' mm' },
      { k: 'e_couche', label: 'Epaisseur par couche', type: 'range', min: 0.6, max: 3, step: 0.2, val: 1.2, unite: ' mm' },
      { k: 'cadre', label: 'Largeur du cadre', type: 'range', min: 3, max: 15, step: 1, val: 6, unite: ' mm' },
      { k: 'detail', label: 'Detail mini', type: 'range', min: 0.4, max: 3, step: 0.1, val: 0.8, unite: ' mm' },
      { k: 'inverser', label: 'Inverser (clair au fond)', type: 'check', val: false },
      { k: 'i', type: 'info', val: 'Chaque couche est une piece a imprimer dans sa couleur (choisis la bobine de chaque couche). Elles s\'empilent dans le cadre.' },
    ], {
      libelle: 'Creer',
      appliquer: async v => {
        try {
          $('#c3-info').textContent = 'Decoupe de l\'image en couches...';
          const r = await api('/api/c3d/shadowbox', { image: id, params: v });
          const bobs = A().S.etat?.bobines || [], nouv = [];
          for (const [i, x] of r.objets.entries()) nouv.push(await ajouterObjet({ type: 'shadowbox', fichier: x.fichier, nom: x.nom, bobine: bobs[i % Math.max(1, bobs.length)]?.id }));
          selectionner(nouv); memo(); vue('iso');
        } catch (e) { toast(e.message); }
      },
    });
  };
  choisir.click();
}

// ------------------------------------------------------------------ DESSIN 2D -> extrusion / revolution
function ouvrirDessin() {
  const D = { pts: [], ferme: false, mode: 'extrusion', zoom: 4, ox: 0, oy: 0, souris: null, pas: 1 };
  const el = document.createElement('div'); el.className = 'c3d-dessin';
  el.innerHTML = `<div style="position:relative"><canvas></canvas><div class="aide2">Clic = point &middot; clic sur le 1er point ou Entree = fermer &middot; Retour arriere = annuler &middot; molette = zoom &middot; clic droit glisse = deplacer</div></div>
    <div class="cote"><h2>Dessin 2D</h2>
      <label>Mode<select data-d="mode"><option value="extrusion">Extrusion (forme sur mesure)</option><option value="revolution">Revolution (vase, bouton, pion...)</option></select></label>
      <p class="mute" data-d="aidemode">Dessine un contour ferme : il sera extrude vers le haut.</p>
      <label class="chk"><input type="checkbox" data-d="lisse"> Courbes douces (lisser les angles)</label>
      <label>Pas de la grille<select data-d="pas"><option value="0.5">0.5 mm</option><option value="1" selected>1 mm</option><option value="5">5 mm</option><option value="0">libre</option></select></label>
      <div data-d="opt-ext"><label>Hauteur <input type="number" data-d="h" value="10" step="0.5"></label>
        <label>Torsion (deg) <input type="number" data-d="torsion" value="0" step="5"></label>
        <label>Echelle du haut (depouille) <input type="number" data-d="echelle_haut" value="1" step="0.05" min="0" max="3"></label>
        <label>Paroi seulement (0 = plein) <input type="number" data-d="epaisseur" value="0" step="0.2" min="0"></label></div>
      <div data-d="opt-rev" hidden><label>Angle <input type="number" data-d="angle" value="360" step="15" min="15" max="360"></label>
        <p class="mute">L'axe de rotation est la ligne verticale orange (x = 0). Dessine le profil a droite.</p></div>
      <div class="grid2"><button data-d="annuler">Annuler point</button><button data-d="effacer">Effacer</button></div>
      <div class="grid2" style="margin-top:6px"><button data-d="rect">Rectangle 40x20</button><button data-d="cercle">Cercle d30</button></div>
      <p class="mute" data-d="info"></p>
      <button class="primary big" data-d="creer">Creer l'objet 3D</button>
      <button class="big" data-d="fermer" style="margin-top:6px">Fermer</button>
    </div>`;
  $('.c3d-stage').appendChild(el);
  const cv = el.querySelector('canvas'), ctx = cv.getContext('2d'), q = k => el.querySelector(`[data-d="${k}"]`);
  const taille = () => { const r = cv.parentElement.getBoundingClientRect(); cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio; dessiner(); };
  const versEcran = (x, y) => [cv.width / 2 + (x - D.ox) * D.zoom * devicePixelRatio, cv.height / 2 - (y - D.oy) * D.zoom * devicePixelRatio];
  const versMm = e => { const r = cv.getBoundingClientRect(); let x = (e.clientX - r.left - r.width / 2) / D.zoom + D.ox, y = -(e.clientY - r.top - r.height / 2) / D.zoom + D.oy;
    const p = +q('pas').value; if (p) { x = Math.round(x / p) * p; y = Math.round(y / p) * p; } if (D.mode === 'revolution') x = Math.max(0, x); return [r2(x), r2(y)]; };
  function dessiner() {
    const W = cv.width, H = cv.height, dpr = devicePixelRatio; ctx.clearRect(0, 0, W, H);
    // grille 1 / 10 mm
    for (const [pas, col] of [[1, '#171c25'], [10, '#252c38']]) {
      if (pas * D.zoom < 4) continue;
      ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.beginPath();
      const x0 = D.ox - W / 2 / D.zoom / dpr, x1 = D.ox + W / 2 / D.zoom / dpr, y0 = D.oy - H / 2 / D.zoom / dpr, y1 = D.oy + H / 2 / D.zoom / dpr;
      for (let x = Math.floor(x0 / pas) * pas; x < x1; x += pas) { const [sx] = versEcran(x, 0); ctx.moveTo(sx, 0); ctx.lineTo(sx, H); }
      for (let y = Math.floor(y0 / pas) * pas; y < y1; y += pas) { const [, sy] = versEcran(0, y); ctx.moveTo(0, sy); ctx.lineTo(W, sy); }
      ctx.stroke();
    }
    const [ax, ay] = versEcran(0, 0);
    ctx.strokeStyle = D.mode === 'revolution' ? '#ff7a2f' : '#3a4658'; ctx.lineWidth = 2 * dpr; ctx.beginPath(); ctx.moveTo(ax, 0); ctx.lineTo(ax, H); ctx.stroke();
    ctx.strokeStyle = '#3a4658'; ctx.lineWidth = 1 * dpr; ctx.beginPath(); ctx.moveTo(0, ay); ctx.lineTo(W, ay); ctx.stroke();
    const pts = D.lisse && D.ferme ? chaikin(D.pts) : D.pts;
    if (pts.length) {
      ctx.beginPath(); pts.forEach(([x, y], i) => { const [sx, sy] = versEcran(x, y); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); });
      if (D.ferme) { ctx.closePath(); ctx.fillStyle = 'rgba(255,122,47,.18)'; ctx.fill(); }
      else if (D.souris) { const [sx, sy] = versEcran(...D.souris); ctx.lineTo(sx, sy); }
      ctx.strokeStyle = '#ff9a4f'; ctx.lineWidth = 2 * dpr; ctx.stroke();
      for (const [x, y] of D.pts) { const [sx, sy] = versEcran(x, y); ctx.fillStyle = '#fff'; ctx.fillRect(sx - 3 * dpr, sy - 3 * dpr, 6 * dpr, 6 * dpr); }
    }
    if (D.souris && !D.ferme) {
      const [sx, sy] = versEcran(...D.souris); ctx.fillStyle = '#ffb36b'; ctx.font = `${12 * dpr}px Inter, sans-serif`;
      const l = D.pts.length ? Math.hypot(D.souris[0] - D.pts.at(-1)[0], D.souris[1] - D.pts.at(-1)[1]) : 0;
      ctx.fillText(`${D.souris[0]} ; ${D.souris[1]}${l ? `   (${r2(l)} mm)` : ''}`, sx + 10 * dpr, sy - 10 * dpr);
    }
    const b = D.pts.length ? D.pts.reduce((a, [x, y]) => [Math.min(a[0], x), Math.min(a[1], y), Math.max(a[2], x), Math.max(a[3], y)], [1e9, 1e9, -1e9, -1e9]) : null;
    q('info').textContent = `${D.pts.length} point(s)${D.ferme ? ' - forme fermee' : ''}${b ? ` - ${r2(b[2] - b[0])} x ${r2(b[3] - b[1])} mm` : ''}`;
  }
  function chaikin(p) { let a = p; for (let k = 0; k < 3; k++) { const n = []; for (let i = 0; i < a.length; i++) { const P = a[i], Q = a[(i + 1) % a.length]; n.push([0.75 * P[0] + 0.25 * Q[0], 0.75 * P[1] + 0.25 * Q[1]], [0.25 * P[0] + 0.75 * Q[0], 0.25 * P[1] + 0.75 * Q[1]]); } a = n; } return a; }
  let glisse = null;
  cv.addEventListener('pointerdown', e => {
    if (e.button === 2) { glisse = [e.clientX, e.clientY, D.ox, D.oy]; return; }
    if (D.ferme) return;
    const p = versMm(e);
    if (D.pts.length >= 3) { const [sx, sy] = versEcran(...D.pts[0]), r = cv.getBoundingClientRect(); if (Math.hypot((e.clientX - r.left) * devicePixelRatio - sx, (e.clientY - r.top) * devicePixelRatio - sy) < 10 * devicePixelRatio) { D.ferme = true; dessiner(); return; } }
    D.pts.push(p); dessiner();
  });
  cv.addEventListener('pointermove', e => { if (glisse) { D.ox = glisse[2] - (e.clientX - glisse[0]) / D.zoom; D.oy = glisse[3] + (e.clientY - glisse[1]) / D.zoom; } D.souris = versMm(e); dessiner(); });
  cv.addEventListener('pointerup', () => glisse = null);
  cv.addEventListener('contextmenu', e => e.preventDefault());
  cv.addEventListener('wheel', e => { e.preventDefault(); D.zoom = Math.min(40, Math.max(0.8, D.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); dessiner(); }, { passive: false });
  const fermer = () => { el.remove(); document.removeEventListener('keydown', clavier, true); };
  const clavier = e => {
    if (e.target.closest?.('input,select')) return;
    if (e.key === 'Backspace') { e.preventDefault(); e.stopPropagation(); if (D.ferme) D.ferme = false; else D.pts.pop(); dessiner(); }
    if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); if (D.pts.length >= 3) D.ferme = true; dessiner(); }
    if (e.key === 'Escape') { e.stopPropagation(); fermer(); }
  };
  document.addEventListener('keydown', clavier, true);
  q('mode').onchange = e => { D.mode = e.target.value; q('opt-ext').hidden = D.mode !== 'extrusion'; q('opt-rev').hidden = D.mode !== 'revolution';
    q('aidemode').textContent = D.mode === 'revolution' ? 'Dessine la MOITIE du profil, a droite de l\'axe orange : il tourne autour pour faire un vase, un pion, un bouton...' : 'Dessine un contour ferme : il sera extrude vers le haut.';
    if (D.mode === 'revolution') D.ox = 30; dessiner(); };
  q('lisse').onchange = e => { D.lisse = e.target.checked; dessiner(); };
  q('annuler').onclick = () => { if (D.ferme) D.ferme = false; else D.pts.pop(); dessiner(); };
  q('effacer').onclick = () => { D.pts = []; D.ferme = false; dessiner(); };
  q('rect').onclick = () => { D.pts = [[-20, -10], [20, -10], [20, 10], [-20, 10]]; if (D.mode === 'revolution') D.pts = [[0, 0], [20, 0], [20, 20], [0, 20]]; D.ferme = true; dessiner(); };
  q('cercle').onclick = () => { D.pts = Array.from({ length: 48 }, (_, i) => [r2(15 * Math.cos(i / 48 * 2 * Math.PI) + (D.mode === 'revolution' ? 25 : 0)), r2(15 * Math.sin(i / 48 * 2 * Math.PI) + (D.mode === 'revolution' ? 15 : 0))]); D.ferme = true; dessiner(); };
  q('fermer').onclick = fermer;
  q('creer').onclick = async () => {
    if (D.pts.length < 3) return toast('Dessine au moins 3 points');
    const params = { lisse: q('lisse').checked, h: +q('h').value, torsion: +q('torsion').value, echelle_haut: +q('echelle_haut').value, epaisseur: +q('epaisseur').value, angle: +q('angle').value };
    try {
      const r = await api('/api/c3d/dessin', { pts: D.pts, mode: D.mode, params });
      const o = await ajouterObjet({ type: 'dessin', params: { ...params, pts: D.pts, mode: D.mode }, fichier: r.fichier, nom: D.mode === 'revolution' ? 'revolution' : 'extrusion' }, { placer: { x: xLibre(r.analyse.dimensions_mm[0]), y: 0 } });
      fermer(); selectionner([o]); memo(); vue('iso');
    } catch (e) { toast(e.message); }
  };
  new ResizeObserver(taille).observe(cv.parentElement); taille();
}

// ------------------------------------------------------------------ ARRONDI / CHANFREIN sur l'ARETE CLIQUEE
const surbrillance = new THREE.Group(); scene.add(surbrillance);
function modeArete() {
  if (!C.objets.length) return toast('Ajoute d\'abord un objet');
  C.arete = true; ren.domElement.classList.add('c3d-viser'); $('[data-c3="arete"]').classList.add('on');
  $('#c3-info').textContent = 'ARETE : clique sur une arete vive d\'un objet (Echap pour annuler)';
}
function finArete() { C.arete = false; ren.domElement.classList.remove('c3d-viser'); $('[data-c3="arete"]')?.classList.remove('on'); surbrillance.clear(); }
async function cliquerArete(hit) {
  const o = hit.object.userData.o;
  try {
    const info = await api('/api/c3d/outil', { outil: 'arete_info', objets: [pourServeur(o)], params: { point: hit.point.toArray() } });
    surbrillance.clear();
    const pts = info.segments.flat().map(p => new THREE.Vector3(...p));
    const ligne = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xff2d55, depthTest: false }));
    ligne.renderOrder = 10; surbrillance.add(ligne);
    ren.domElement.classList.remove('c3d-viser');
    panneau(`Arete (${info.segments.length} segment${info.segments.length > 1 ? 's' : ''}, ${info.convexe ? 'saillante' : 'rentrante'})`, [
      { k: 'type', label: 'Type', type: 'select', val: 'arrondi', options: [['arrondi', 'Arrondi (conge)'], ['chanfrein', 'Chanfrein (biseau)']] },
      { k: 'r', label: 'Rayon / taille', type: 'range', min: 0.3, max: 20, step: 0.1, val: 2, unite: ' mm' },
      { k: 'i', type: 'info', val: info.convexe ? 'Arete saillante : on enleve de la matiere.' : 'Arete rentrante (angle interieur) : on AJOUTE un conge de matiere = piece plus solide.' },
    ], {
      fermer: () => finArete(),
      appliquer: async v => {
        C.sel = [o];
        await outil('arrondir_arete', { point: hit.point.toArray(), r: v.r, chanfrein: v.type === 'chanfrein' });
      },
    });
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ THEME (plateau clair / sombre)
function themePlateau(t) {
  const clair = t === 'light';
  plaque.material.color.setHex(clair ? 0xe4e8ef : 0x1b2230);
  grille.material.color?.setHex?.(clair ? 0xb3bcc9 : 0x283141);
  fine.material.color?.setHex?.(clair ? 0xd3d9e2 : 0x202733);
  bord.material.color.setHex(clair ? 0x9aa5b5 : 0x3a4658);
}
window.addEventListener('theme', e => themePlateau(e.detail));
themePlateau(document.documentElement.dataset.scene);

// ------------------------------------------------------------------ INTEGRER : clic sur l'objet, puis sur la surface
function integrer() {
  if (C.sel.length !== 1) return toast('Selectionne l\'objet a integrer (logo, texte, image 3D...), puis clique Integrer');
  C.integ = { motif: C.sel[0], m0: C.sel[0].mesh.matrixWorld.clone() };
  tc.detach(); ren.domElement.classList.add('c3d-viser');
  $('#c3-info').textContent = 'INTEGRER : clique maintenant sur la surface ou poser l\'objet (Echap pour annuler)';
  $('[data-c3="integrer"]').classList.add('on');
}
function finIntegrer() { C.integ = null; ren.domElement.classList.remove('c3d-viser'); $('[data-c3="integrer"]').classList.remove('on'); }
function poserSurSurface(hit) {
  const { motif } = C.integ, cible = hit.object.userData.o;
  if (!cible || cible === motif) return;
  const n = hit.face.normal.clone().applyMatrix3(new THREE.Matrix3().getNormalMatrix(hit.object.matrixWorld)).normalize();
  const p = hit.point.clone();
  const g = motif.mesh.geometry; g.computeBoundingBox();
  const bb = g.boundingBox, bc = new THREE.Vector3((bb.min.x + bb.max.x) / 2, (bb.min.y + bb.max.y) / 2, bb.min.z);
  const ech0 = motif.mesh.scale.clone();
  const etat = { n, p, cible, ech0, bc };
  const placer = v => {
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
    // garde le texte "a l'endroit" : on aligne l'axe X local au mieux sur l'horizontale
    const xw = new THREE.Vector3(1, 0, 0).applyQuaternion(q), ref = Math.abs(n.z) > 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 0, 1).cross(n).normalize();
    const ang = Math.atan2(new THREE.Vector3().crossVectors(xw, ref).dot(n), xw.dot(ref));
    q.premultiply(new THREE.Quaternion().setFromAxisAngle(n, ang + THREE.MathUtils.degToRad(v.rotation)));
    const s = ech0.clone().multiplyScalar(v.taille / 100);
    motif.mesh.quaternion.copy(q); motif.mesh.scale.copy(s);
    const off = bc.clone().multiply(s).applyQuaternion(q);
    motif.mesh.position.copy(p).sub(off).addScaledVector(n, v.mode === 'coller' || v.mode === 'relief' ? -0.3 : 0);
    motif.mesh.updateMatrixWorld();
  };
  ren.domElement.classList.remove('c3d-viser');
  panneau('Integrer sur la surface', [
    { k: 'mode', label: 'Mode', type: 'select', val: 'relief', options: [['relief', 'Relief (fusionne, 1 piece)'], ['graver', 'Graver (creuse la surface)'],
      ['incruster', 'Incruster 2 couleurs (logement + piece)'], ['coller', 'Poser seulement (2 objets)']] },
    { k: 'epouser', label: 'Epouser la courbure de la surface', type: 'check', val: true, aide: 'Le motif se plaque sur un cylindre, une sphere, un galbe... (jamais vu chez Tinkercad)' },
    { k: 'profondeur', label: 'Profondeur (graver / incruster)', type: 'range', min: 0.3, max: 5, step: 0.1, val: 1, unite: ' mm' },
    { k: 'rotation', label: 'Rotation', type: 'range', min: -180, max: 180, step: 5, val: 0, unite: ' deg' },
    { k: 'taille', label: 'Taille', type: 'range', min: 10, max: 300, step: 5, val: 100, unite: ' %' },
  ], {
    libelle: 'Integrer',
    changer: v => placer(v),
    fermer: applique => { if (!applique) { C.integ.m0.decompose(motif.mesh.position, motif.mesh.quaternion, motif.mesh.scale); motif.mesh.updateMatrixWorld(); } finIntegrer(); selectionner([motif]); },
    appliquer: async v => {
      placer(v); C.sel = [motif, cible];
      const bm = motif.bobine, bc_ = cible.bobine;
      const res = await outil('integrer', { mode: v.mode, profondeur: v.profondeur, epouser: v.epouser, point: p.toArray(), normale: n.toArray() });
      if (res) {
        const nouveaux = C.objets.slice(-res.objets.length);
        nouveaux.forEach((o, i) => { o.bobine = (v.mode === 'incruster' || v.mode === 'coller') && i === 1 ? bm : bc_; o.mesh.material = materiau(o, C.sel.includes(o)); });
        memo();
        toast({ relief: 'Integre en relief', graver: 'Grave dans la surface', incruster: 'Incruste : 2 pieces, 2 couleurs (onglet impression = 2 plateaux)', coller: 'Pose sur la surface' }[v.mode]);
      }
    },
  });
}

// ------------------------------------------------------------------ EFFETS DE SURFACE (apercu EN DIRECT)
async function effetSurface() {
  if (C.sel.length !== 1) return toast('Selectionne UN objet (applique ensuite aux autres si besoin)');
  const o = C.sel[0];
  $('#c3-info').textContent = 'Preparation d\'un maillage fin pour l\'effet...';
  document.body.style.cursor = 'progress';
  // resolution fine (0.2-0.35 mm selon la taille de l'objet) : traits nets, pas de marches d'escalier
  const ext = boite([o]).getSize(new THREE.Vector3()), aire = 2 * (ext.x * ext.y + ext.y * ext.z + ext.x * ext.z);
  const res = Math.min(0.35, Math.max(0.2, Math.sqrt(aire / 450000)));
  let geo;
  try {
    const r = await fetch('/api/c3d/dense', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outil: 'dense', objets: [pourServeur(o)], params: { taille: res, max_faces: 1500000 } }) });
    if (!r.ok) throw new Error((await r.text()).slice(0, 200));
    const buf = await r.arrayBuffer(), [nv, nf] = new Uint32Array(buf, 0, 2);
    geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(buf.slice(8, 8 + nv * 12)), 3));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(buf.slice(8 + nv * 12, 8 + nv * 12 + nf * 12)), 1));
  } catch (e) { document.body.style.cursor = ''; return toast(e.message); }
  const info = preparer(geo);
  document.body.style.cursor = '';
  const ap = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: couleurBob(o.bobine), roughness: 0.45, metalness: 0.03 }));
  ap.castShadow = true; scene.add(ap); o.mesh.visible = false; tc.detach();
  const opts = Object.entries(MOTIFS).map(([k, m]) => [k, m.nom]);
  let _t = null, dernier = null;
  const maj = v => { dernier = v; clearTimeout(_t); _t = setTimeout(() => { const t0 = performance.now(); appliquer(geo, info, v.rendu === 'percage' ? { ...v, profondeur: -2.5, nettete: 4 } : v);
    ap.material.color.set(v.rendu === 'percage' ? 0xffb07a : couleurBob(o.bobine)); _pan?.d.querySelector('[data-k="profondeur"]')?.closest('label') && (_pan.d.querySelector('[data-k="profondeur"]').closest('label').style.display = v.rendu === 'percage' ? 'none' : ''); $('#c3-info').textContent = `Effet : ${MOTIFS[v.motif].nom} - ${(info.n / 1000).toFixed(0)} k points, calcul ${Math.round(performance.now() - t0)} ms`; }, 30); };
  panneau('Effet de surface (apercu en direct)', [
    { k: 'rendu', label: 'Rendu', type: 'select', val: 'relief', options: [['relief', 'Relief (bosses / creux)'], ['percage', 'PERCAGE traversant (ajoure : lampe, RGB)']] },
    { k: 'motif', label: 'Motif', type: 'select', val: 'alveoles', options: opts },
    { k: 'profondeur', label: 'Relief (negatif = en creux)', type: 'range', min: -3, max: 3, step: 0.05, val: 0.8, unite: ' mm' },
    { k: 'taille', label: 'Taille du motif', type: 'range', min: 1, max: 40, step: 0.5, val: 6, unite: ' mm' },
    { k: 'etirement', label: 'Etirement (largeur / hauteur)', type: 'range', min: 0.25, max: 4, step: 0.05, val: 1 },
    { k: 'rotation', label: 'Rotation', type: 'range', min: -180, max: 180, step: 1, val: 0, unite: ' deg' },
    { k: 'trait', label: 'Epaisseur des parois / traits', type: 'range', min: 0.02, max: 0.45, step: 0.01, val: 0.08 },
    { k: 'nettete', label: 'Nettete (doux <-> vif)', type: 'range', min: 0.3, max: 4, step: 0.05, val: 1 },
    { k: 'alea', label: 'Irregularite (cellules)', type: 'range', min: 0, max: 1, step: 0.05, val: 0.85 },
    { k: 'du', label: 'Decalage horizontal', type: 'range', min: 0, max: 1, step: 0.01, val: 0 },
    { k: 'dv', label: 'Decalage vertical', type: 'range', min: 0, max: 1, step: 0.01, val: 0 },
    { k: 'projection', label: 'Projection', type: 'select', val: 'auto', options: [['auto', info.rond ? 'Auto (cylindrique, sans couture)' : 'Auto (triplanaire)'], ['cylindre', 'Cylindrique'], ['triplanaire', 'Triplanaire (toutes faces)'], ['z', 'Vue de dessus (Z)'], ['x', 'De cote (X)'], ['y', 'De face (Y)']] },
    { k: 'zones', label: 'Ou ?', type: 'select', val: 'cotes', options: [['cotes', 'Cotes'], ['dessus', 'Dessus'], ['tout', 'Partout (sauf dessous)']] },
    { k: 'bas', label: 'Commence a (hauteur)', type: 'range', min: 0, max: 100, step: 1, val: 0, unite: ' %' },
    { k: 'haut', label: 'S\'arrete a (hauteur)', type: 'range', min: 0, max: 100, step: 1, val: 100, unite: ' %' },
    { k: 'fondu', label: 'Fondu aux limites', type: 'range', min: 0, max: 10, step: 0.5, val: 1.5, unite: ' mm' },
    { k: 'inverser', label: 'Inverser le motif', type: 'check', val: false },
  ], {
    changer: maj,
    fermer: applique => { if (!applique) { scene.remove(ap); o.mesh.visible = true; geo.dispose(); selectionner([o]); } },
    appliquer: async v => {
      clearTimeout(_t);
      if (v.rendu === 'percage') {           // les zones creuses du motif traversent la paroi (outil ajourer, meme motif / reglages)
        scene.remove(ap); geo.dispose(); o.mesh.visible = true; selectionner([o]);
        const rond = info.rond || /^gen_(vase|pot)$/.test(o.type) || (o.type === 'texture' && /^Vase/.test(o.nom || ''));
        const pp = o.params || {}, exclure = pp.perso && pp.perso !== 'aucun' ? [[+pp.perso_angle || 0, (+pp.perso_hauteur || 0.5) * (+pp.h || 120), (+pp.perso_largeur || 52) + 8, (+pp.perso_taille || 34) + 8]] : [];
        const proj = v.projection === 'auto' || v.projection === 'triplanaire' ? (rond ? 'cylindre' : v.zones === 'dessus' ? 'z' : 'y') : v.projection;
        return outil('ajourer', { motif: v.motif, taille: v.taille, trait: v.trait, rotation: v.rotation, etirement: v.etirement, alea: v.alea, nettete: v.nettete,
          du: v.du, dv: v.dv, inverser: v.inverser, axe: proj, bas: Math.max(3, v.bas), haut: Math.min(97, v.haut), exclure });
      }
      appliquer(geo, info, v);
      $('#c3-info').textContent = 'Enregistrement de la piece texturee...';
      try {
        const pos = geo.attributes.position.array, idx = geo.index.array;
        const corps = new Blob([new Uint32Array([pos.length / 3, idx.length / 3]), pos, idx instanceof Uint32Array ? idx : new Uint32Array(idx)]);
        const rr = await fetch('/api/c3d/geometrie?nom=texture', { method: 'POST', body: corps });
        if (!rr.ok) throw new Error((await rr.text()).slice(0, 200));
        const r = await rr.json();
        const s0 = serial(o); retirer(o); scene.remove(ap); geo.dispose();
        const n = await ajouterObjet({ ...s0, id: undefined, fichier: r.fichier, matrice: null, type: 'texture', params: null, nom: (s0.nom || 'objet') + ' + ' + MOTIFS[v.motif].nom });
        selectionner([n]); memo(); toast('Effet applique (Ctrl+Z pour revenir)');
      } catch (e) { toast(e.message); scene.remove(ap); o.mesh.visible = true; }
    },
  });
  const P = $('.c3d-pan'); P.querySelector('.corps').style.maxHeight = '62vh';
}

// ------------------------------------------------------------------ copier / coller
function copier() { if (C.sel.length) { C.presse = C.sel.map(serial); toast(`${C.sel.length} objet(s) copie(s)`); } }
async function coller(pt) {
  if (!C.presse?.length) return;
  const n = [];
  for (const s of C.presse) n.push(await ajouterObjet({ ...s, id: undefined }));
  const b = boite(n), c = b.getCenter(new THREE.Vector3());
  for (const o of n) { if (pt) { o.mesh.position.x += pt.x - c.x; o.mesh.position.y += pt.y - c.y; } else o.mesh.position.x += 10; }
  selectionner(n); memo();
}

// ------------------------------------------------------------------ vues camera
function vue(nom) {
  const b = C.sel.length ? boite(C.sel) : (C.objets.length ? boite(C.objets) : new THREE.Box3(new THREE.Vector3(-110, -107, 0), new THREE.Vector3(110, 107, 40)));
  const c = b.getCenter(new THREE.Vector3()), r = Math.max(b.getSize(new THREE.Vector3()).length(), 30);
  const d = r / Math.tan(THREE.MathUtils.degToRad(cam.fov / 2)) * 0.62;
  const dir = { dessus: [0, -0.001, 1], face: [0, -1, 0.0001], cote: [1, 0, 0.0001], arriere: [0, 1, 0.0001], iso: [-0.6, -1, 0.85] }[nom];
  const v = new THREE.Vector3(...dir).normalize();
  orb.target.copy(c); cam.position.copy(c).addScaledVector(v, d); orb.update();
}

// ------------------------------------------------------------------ MENU CLIC DROIT
let _menu = null, _bd = null;
function fermerMenu() { _menu?.remove(); _menu = null; }
document.addEventListener('pointerdown', e => { if (_menu && !e.target.closest('.c3d-menu')) fermerMenu(); });
ren.domElement.addEventListener('pointerdown', e => { if (e.button === 2) _bd = [e.clientX, e.clientY]; });
ren.domElement.addEventListener('contextmenu', e => {
  e.preventDefault();
  if (!_bd || Math.hypot(e.clientX - _bd[0], e.clientY - _bd[1]) > 5) return;      // clic droit glisse = deplacer la vue
  const r = ren.domElement.getBoundingClientRect();
  souris.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(souris, cam);
  const hit = ray.intersectObjects(C.objets.map(o => o.mesh), false)[0];
  const pt = hit?.point || ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), new THREE.Vector3());
  if (hit && !C.sel.includes(hit.object.userData.o)) selectionner([hit.object.userData.o]);
  if (!hit && !e.shiftKey) selectionner([]);
  ouvrirMenu(e.clientX, e.clientY, hit, pt);
});
function ouvrirMenu(x, y, hit, pt) {
  fermerMenu();
  const m = document.createElement('div'); m.className = 'c3d-menu';
  const it = (lab, fn, kbd = '', off = false) => ({ lab, fn, kbd, off });
  const sel = C.sel.length, groupe = C.sel.some(o => o.enfants);
  const L = [];
  if (sel) {
    L.push({ titre: sel > 1 ? `${sel} objets` : (C.sel[0].nom || C.sel[0].type) });
    L.push(it('&#10148; Integrer sur une surface...', integrer, 'I', sel !== 1), it('Effet de surface...', effetSurface));
    L.push('-', it('Dupliquer', dupliquer, 'Ctrl+D'), it('Copier', copier, 'Ctrl+C'), it(C.sel.every(o => o.trou) ? 'Rendre SOLIDE' : 'Rendre PERCAGE', basculerTrou, 'H'));
    if (sel > 1) L.push(it('Grouper (solides - percages)', grouper, 'Ctrl+G'), it('Intersection', () => outil('intersection')));
    if (groupe) L.push(it('Degrouper', degrouper, 'Ctrl+Maj+G'));
    L.push({ couleurs: true });
    L.push('-', it('Poser sur le plateau', poser, 'D'), it('Centrer sur le plateau', centrer), it('Orienter pour l\'impression', OUTILS.orienter),
      it('Miroir X', () => miroir('x')), it('Miroir Y', () => miroir('y')));
    L.push('-', it('Arrondir / chanfreiner une arete...', modeArete, 'A'), it('Couper...', OUTILS.couper, '', sel !== 1), it('Arrondir toutes les aretes...', OUTILS.arrondir), it('Creuser...', OUTILS.coque), it('Reseau de copies...', reseau, '', sel !== 1));
    L.push('-', it('Cadrer la selection', () => vue('iso'), 'F'), it('Exporter en STL', () => $('#c3-export').click()), it('Supprimer', supprimer, 'Suppr'));
  } else {
    L.push({ titre: 'Plateau' }, it('<span style="color:#ff6410">Logo SHWork...</span>', () => ouvrirLogo()), it('Dessin 2D -> 3D...', ouvrirDessin), it('Vase...', () => ouvrirGen('vase')));
    if (C.presse?.length) L.push(it(`Coller ici (${C.presse.length})`, () => coller(pt), 'Ctrl+V'));
    for (const [f, lab] of [['boite', 'Boite'], ['cylindre', 'Cylindre'], ['sphere', 'Sphere'], ['texte', 'Texte']])
      L.push(it(`Ajouter ici : ${lab}`, () => ajouterForme(f, f === 'texte' ? texteParams() : {}, { x: pt?.x || 0, y: pt?.y || 0, surDessus: true })));
    L.push('-', it('Tout selectionner', () => selectionner([...C.objets]), 'Ctrl+A'), it('Annuler', annuler, 'Ctrl+Z', C.hist.length < 2), it('Refaire', refaire, 'Ctrl+Y', !C.futur.length));
  }
  L.push('-', { titre: 'Vue' }, it('Dessus', () => vue('dessus'), '7'), it('Face', () => vue('face'), '1'), it('Cote', () => vue('cote'), '3'), it('Perspective', () => vue('iso'), '0'),
    it(document.documentElement.dataset.scene === 'light' ? 'Scene sombre' : 'Scene claire', () => $('#theme-btn').click()));
  m.innerHTML = L.map((l, i) => l === '-' ? '<div class="sep"></div>' : l.titre ? `<div class="titre">${l.titre}</div>`
    : l.couleurs ? `<div class="titre">Couleur</div><div class="pastilles">${(A().S.etat?.bobines || []).map(b => `<i data-bob="${b.id}" title="${b.nom}" style="background:${b.couleur}"></i>`).join('')}</div>`
    : `<div class="it ${l.off ? 'off' : ''}" data-i="${i}"><span>${l.lab}</span><kbd>${l.kbd}</kbd></div>`).join('');
  document.body.appendChild(m);
  const w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = Math.min(x, innerWidth - w - 8) + 'px'; m.style.top = Math.min(y, innerHeight - h - 8) + 'px';
  m.querySelectorAll('[data-i]').forEach(d => d.onclick = () => { fermerMenu(); L[+d.dataset.i].fn(); });
  m.querySelectorAll('[data-bob]').forEach(d => d.onclick = () => { fermerMenu(); C.sel.forEach(o => { o.bobine = d.dataset.bob; o.mesh.material = materiau(o, true); }); memo(); majInspecteur(); });
  _menu = m;
}

C.exporter = () => ({ objets: C.objets.map(serial) });
C.baseImportee = async (r, nom) => { const o = await ajouterObjet({ type: 'import', fichier: r.fichier, nom: 'BASE ' + nom }, { placer: { x: 0, y: 0 } }); selectionner([o]); memo(); vue('iso'); };
C.charger = async d => { await restaurer(JSON.stringify(d.objets || [])); C.hist = []; memo(); vue('iso'); };
C.vider = async () => { for (const o of [...C.objets]) retirer(o); selectionner([]); memo(); };
C.miniature = () => { tc.detach(); ren.render(scene, cam); const c = document.createElement('canvas'); c.width = 320; c.height = 220;
  c.getContext('2d').drawImage(ren.domElement, 0, 0, 320, 220); if (C.sel.length) tc.attach(pivot); return c.toDataURL('image/png'); };
C._ajout = async (x, bobine) => {           // ajout depuis un autre onglet (Keycaps, SHWork...)
  const o = await ajouterObjet({ type: 'import', fichier: x.fichier, nom: x.nom || x.role || 'objet', bobine }, { placer: { x: xLibre(x.analyse?.dimensions_mm?.[0] || 20), y: 0 } });
  memo(); return o;
};
Object.assign(C, { _f: { integrer, poserSurSurface, effetSurface, ouvrirMenu, vue, coller, copier, cliquerArete, modeArete, ouvrirGen } });   // debogage

// ------------------------------------------------------------------ clavier
document.addEventListener('keydown', e => {
  if (!$('#tab-c3d').classList.contains('on') || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
  const k = e.key.toLowerCase(), ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && k === 'z') { e.preventDefault(); annuler(); }
  else if (ctrl && k === 'y') { e.preventDefault(); refaire(); }
  else if (ctrl && k === 'd') { e.preventDefault(); dupliquer(); }
  else if (ctrl && k === 'g') { e.preventDefault(); e.shiftKey ? degrouper() : grouper(); }
  else if (ctrl && k === 'a') { e.preventDefault(); selectionner([...C.objets]); }
  else if (ctrl && k === 'c') { e.preventDefault(); copier(); }
  else if (ctrl && k === 'v') { e.preventDefault(); coller(); }
  else if (k === 'i' && !ctrl) integrer();
  else if (k === 'a' && !ctrl) modeArete();
  else if (k === 'f') vue('iso');
  else if (['7', '1', '3', '0'].includes(k)) vue({ 7: 'dessus', 1: 'face', 3: 'cote', 0: 'iso' }[k]);
  else if (k === 'delete' || k === 'backspace') supprimer();
  else if (k === 'w') modeGizmo('translate'); else if (k === 'e') modeGizmo('rotate'); else if (k === 'r') modeGizmo('scale');
  else if (k === 'h') basculerTrou(); else if (k === 'd') poser(); else if (k === 'm') ACTIONS.mesure();
  else if (k === 'escape') { if (_menu) fermerMenu(); else if (_pan) fermerPanneau(); else if (C.integ) { finIntegrer(); selectionner(C.sel); } else if (C.arete) finArete(); else selectionner([]); }
  else if (k.startsWith('arrow') && C.sel.length) {           // deplacement fin au clavier (pas de la grille)
    e.preventDefault(); const s = +$('#c3-snap').value || 1;
    const v = { arrowleft: [-s, 0], arrowright: [s, 0], arrowup: [0, s], arrowdown: [0, -s] }[k];
    for (const o of C.sel) { if (e.shiftKey) o.mesh.position.z += v[1]; else { o.mesh.position.x += v[0]; o.mesh.position.y += v[1]; } }
    finirEdition();
  }
});

// ------------------------------------------------------------------ demarrage
(async function init() {
  for (let i = 0; i < 50 && !(A()?.S?.polices && A()?.S?.etat); i++) await new Promise(r => setTimeout(r, 100));
  $('#c3-police').innerHTML = Object.entries(A().S.polices || {}).map(([k, p]) => `<option value="${k}">${p.label}</option>`).join('');
  try {
    const s = JSON.parse(localStorage.getItem('c3d_scene') || '[]');
    for (const o of s) { try { await ajouterObjet({ ...o }); } catch { } }
  } catch { }
  memo(); majInspecteur(); taille();
})();
