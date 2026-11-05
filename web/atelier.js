// ATELIER UNIFIE : rail de modules, recherche universelle (Ctrl+K), cotes au clavier (N), pinceau de modelage (B),
// Image vers 3D niveau 2 (IA locale), tuto (i). Tout passe par la scene de Creation 3D : le mode equipe suit tout seul.
import * as THREE from 'three';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { STLExporter } from 'three/addons/exporters/STLExporter.js';
import { TessellateModifier } from 'three/addons/modifiers/TessellateModifier.js';

const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const A = () => window.ATELIER, api = (u, b) => A().api(u, b), toast = m => A().toast(m);
const C = () => window.__C3D, I = () => window.__C3D._int;
const aller = t => document.querySelector(`#tabs [data-tab="${t}"]`)?.click();
const el = (h) => { const d = document.createElement('div'); d.innerHTML = h.trim(); return d.firstChild; };
const dansSaisie = () => /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || '');

// ------------------------------------------------------------------ styles
document.head.appendChild(Object.assign(document.createElement('style'), { textContent: `
#at-rail{position:fixed;left:0;top:var(--at-haut,64px);bottom:0;width:58px;z-index:50;background:#0d0f13;border-right:1px solid #2a2e37;display:none;flex-direction:column;align-items:center;gap:4px;padding:8px 0}
body.at-actif #at-rail{display:flex} body.at-actif main{margin-left:58px}
#at-rail button{width:48px;min-height:46px;background:none;border:0;border-radius:10px;color:#9aa1ad;cursor:pointer;font:10px 'Segoe UI',sans-serif;display:grid;place-items:center;padding:4px 0;line-height:1.1}
#at-rail button i{font-style:normal;font-size:17px;color:inherit}
#at-rail button:hover{background:#1d2027;color:#fff} #at-rail button.on{background:#ff641022;color:#ff6410}
#at-rail .bas{margin-top:auto}
.at-voile{position:fixed;inset:0;background:#0007;z-index:9500;display:flex;justify-content:center;align-items:flex-start;padding-top:12vh}
.at-boite{width:min(620px,92vw);background:#14171d;color:#e9ebef;border:1px solid #2a2e37;border-radius:14px;box-shadow:0 20px 60px #000a;font:13px 'Segoe UI',sans-serif;overflow:hidden}
#at-q{width:100%;box-sizing:border-box;padding:14px 16px;background:none;border:0;border-bottom:1px solid #2a2e37;color:#fff;font-size:15px;outline:0}
#at-res{max-height:50vh;overflow:auto}
#at-res div{padding:8px 16px;cursor:pointer;display:flex;justify-content:space-between;gap:10px} #at-res div.on{background:#ff641022}
#at-res small{color:#8b919c}
.at-flot{position:fixed;right:16px;top:90px;z-index:9400;width:270px;background:#14171d;color:#e9ebef;border:1px solid #2a2e37;border-radius:12px;padding:12px 14px;box-shadow:0 12px 40px #0009;font:12px 'Segoe UI',sans-serif}
.at-flot h3{margin:0 0 8px;font-size:13px;display:flex;justify-content:space-between}
.at-flot h3 button{background:none;border:0;color:#8b919c;cursor:pointer}
.at-flot label{display:grid;grid-template-columns:62px 1fr 22px;align-items:center;gap:6px;margin:4px 0}
.at-flot input[type=number]{width:100%;box-sizing:border-box;background:#0d0f13;color:#fff;border:1px solid #2a2e37;border-radius:6px;padding:5px 6px}
.at-flot .ax{font-weight:700} .ax-x{color:#ff5a4f}.ax-y{color:#3ddc97}.ax-z{color:#4aa3ff}
.at-flot .act{display:flex;gap:6px;margin-top:8px}.at-flot .act button,.at-seg button{flex:1;background:#1d2027;color:#e9ebef;border:1px solid #2a2e37;border-radius:7px;padding:6px;cursor:pointer}
.at-flot .act button.ok{background:#ff6410;color:#0d0f13;border-color:#ff6410;font-weight:600}
.at-seg{display:flex;gap:4px;margin:6px 0}.at-seg button.on{background:#ff6410;color:#0d0f13}
.at-gal{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:8px 0}.at-gal img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px}
#at-tuto{position:fixed;z-index:9700;width:320px;background:#ff6410;color:#14171d;border-radius:12px;padding:12px 14px;font:13px 'Segoe UI',sans-serif;box-shadow:0 12px 40px #000a}
#at-tuto b{display:block;margin-bottom:4px}#at-tuto .act{display:flex;justify-content:space-between;margin-top:8px}#at-tuto button{background:#14171d;color:#fff;border:0;border-radius:6px;padding:4px 10px;cursor:pointer}
.at-cible{outline:3px solid #ff6410!important;outline-offset:2px;border-radius:6px}
.at-av{position:fixed;left:50%;top:76px;transform:translateX(-50%);z-index:9600;max-width:640px;background:#14171d;border:1px solid #f5c542;color:#f5e6b0;padding:10px 16px;border-radius:10px;font:13px 'Segoe UI',sans-serif;box-shadow:0 10px 30px #0008}
` }));

// ------------------------------------------------------------------ RAIL : tous les modules de creation au meme endroit
const MODULES = [['c3d', '&#9651;', 'Atelier'], ['creer', '&#9998;', 'Prenoms'], ['kc', '&#9000;', 'Keycaps'], ['sw', '&#9881;', 'Pieces']];
const CREATION = new Set(MODULES.map(m => m[0]));
const rail = el(`<div id="at-rail">${MODULES.map(([t, i, n]) => `<button data-m="${t}" title="${n}"><i>${i}</i>${n}</button>`).join('')}
  <button data-a="biblio" title="Tous les modeles parametriques, dans la meme scene (L)"><i>&#9638;</i>Biblio</button>
  <button data-a="pieces" title="Mes pieces : reutilisables et partagees (P)"><i>&#10070;</i>Pieces+</button>
  <button data-a="design" title="Outils de placement (G)"><i>&#8982;</i>Design</button>
  <button data-a="coupe" title="Vue en coupe (C)"><i>&#9707;</i>Coupe</button>
  <button data-a="ia" title="Image vers 3D niveau 2 (IA locale)"><i>&#10022;</i>IA 3D</button>
  <button data-a="cotes" title="Cotes au clavier (N)"><i>&#8645;</i>Cotes</button>
  <button data-a="pinceau" title="Pinceau de modelage (B)"><i>&#9673;</i>Modeler</button>
  <button class="bas" data-a="cherche" title="Tout chercher (Ctrl+K)"><i>&#8981;</i>Chercher</button>
  <button data-a="tuto" title="Guide de l'atelier"><i>i</i>Tuto</button></div>`);
document.body.appendChild(rail);
function majRail() {
  const on = document.querySelector('.tab.on')?.id?.replace('tab-', '');
  document.body.classList.toggle('at-actif', CREATION.has(on));
  $$('#at-rail [data-m]').forEach(b => b.classList.toggle('on', b.dataset.m === on));
  document.documentElement.style.setProperty('--at-haut', document.querySelector('header').offsetHeight + 'px');
  $$('#tabs [data-tab]').forEach(b => { if (['creer', 'kc', 'sw'].includes(b.dataset.tab)) b.hidden = true; });
  const n = $('#tabs [data-tab="c3d"]'); if (n) { n.classList.toggle('on', CREATION.has(on)); }
}
new MutationObserver(majRail).observe(document.querySelector('main'), { attributes: true, subtree: true, attributeFilter: ['class'] });
rail.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.m) return aller(b.dataset.m);
  ({ pieces: ouvrirPieces, design: ouvrirDesign, biblio: ouvrirBiblio, coupe: ouvrirCoupe, ia: ouvrirIA, cotes: ouvrirCotes, pinceau: ouvrirPinceau, cherche: ouvrirRecherche, tuto: () => lancerTuto() })[b.dataset.a]();
});
majRail(); setTimeout(() => { if (document.querySelector('.tab.on')?.id === 'tab-creer') aller('c3d'); majRail(); }, 400);

// ------------------------------------------------------------------ RECHERCHE UNIVERSELLE
function index() {
  const out = [];
  const texte = b => (b.getAttribute('title') || b.innerText || '').replace(/\s+/g, ' ').trim();
  const zone = (sel, tab, famille) => $$(sel).forEach(b => { const t = texte(b); if (t) out.push({ t, famille, run: () => { aller(tab); setTimeout(() => b.click(), 50); } }); });
  zone('#tab-c3d [data-forme]', 'c3d', 'Forme');
  zone('#tab-c3d [data-gen]', 'c3d', 'Generateur');
  zone('#tab-c3d [data-c3]', 'c3d', 'Outil');
  zone('#tab-c3d [data-mode]', 'c3d', 'Gizmo');
  zone('#tab-sw button[data-type], #tab-sw [data-piece]', 'sw', 'Piece mecanique');
  for (const [t, , n] of MODULES) out.push({ t: n, famille: 'Module', run: () => aller(t) });
  for (const b of $$('#tabs [data-tab]')) if (!b.hidden) out.push({ t: b.innerText, famille: 'Page', run: () => b.click() });
  out.push({ t: 'Cotes au clavier : position, dimensions, rotation (N)', famille: 'Outil', run: ouvrirCotes });
  out.push({ t: 'Pinceau de modelage : tirer, pousser, lisser, aplatir (B)', famille: 'Outil', run: ouvrirPinceau });
  out.push({ t: 'Image vers 3D niveau 2 (IA locale)', famille: 'IA', run: ouvrirIA });
  out.push({ t: 'Mes pieces : enregistrer et reutiliser (P)', famille: 'Outil', run: ouvrirPieces });
  for (const [t, f] of OUTILS_DESIGN) out.push({ t, famille: 'Design', run: f });
  out.push({ t: 'Scene shop : photos d annonce, plusieurs versions (V)', famille: 'Outil', run: ouvrirShop });
  out.push({ t: 'Vue en coupe (C)', famille: 'Outil', run: ouvrirCoupe });
  for (const [k, m] of Object.entries(window.__CFG?.modeles || {})) if (!m.archive) out.push({ t: m.nom + ' : ajouter a la scene', famille: 'Bibliotheque', run: () => ouvrirBiblio(k) });
  out.push({ t: 'Guide de l atelier', famille: 'Aide', run: () => lancerTuto() });
  for (const p of window.__PROJETS?.P?.liste || []) out.push({ t: p.nom, famille: 'Projet', run: () => window.SHWOuvrirProjet(p.id) });
  for (const [k, m] of Object.entries(window.__CFG?.modeles || {})) if (!m.archive) out.push({ t: m.nom, famille: 'Projet parametrique', run: () => window.__CFG.ouvrirModele(k, {}) });
  return out;
}
function ouvrirRecherche() {
  if ($('#at-voile-r')) return;
  const liste = index(); let sel = 0, vus = [];
  const v = el(`<div class="at-voile" id="at-voile-r"><div class="at-boite"><input id="at-q" placeholder="Chercher un outil, une forme, un projet..."><div id="at-res"></div></div></div>`);
  document.body.appendChild(v);
  const fermer = () => v.remove();
  const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const rendre = () => {
    const q = norm($('#at-q').value).split(/\s+/).filter(Boolean);
    vus = liste.filter(x => q.every(m => norm(x.t + ' ' + x.famille).includes(m))).slice(0, 40);
    sel = Math.min(sel, Math.max(0, vus.length - 1));
    $('#at-res').innerHTML = vus.map((x, i) => `<div class="${i === sel ? 'on' : ''}" data-i="${i}"><span>${x.t}</span><small>${x.famille}</small></div>`).join('');
    $('#at-res .on')?.scrollIntoView({ block: 'nearest' });
  };
  const lancer = i => { fermer(); vus[i]?.run(); };
  v.addEventListener('mousedown', e => { if (e.target === v) fermer(); const d = e.target.closest('[data-i]'); if (d) lancer(+d.dataset.i); });
  $('#at-q').addEventListener('input', () => { sel = 0; rendre(); });
  $('#at-q').addEventListener('keydown', e => {
    if (e.key === 'Escape') fermer();
    if (e.key === 'ArrowDown') { sel++; rendre(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); rendre(); e.preventDefault(); }
    if (e.key === 'Enter') lancer(sel);
    e.stopPropagation();
  });
  rendre(); $('#at-q').focus();
}

// ------------------------------------------------------------------ COTES AU CLAVIER
function ouvrirCotes() {
  aller('c3d');
  if (!C().sel.length) return toast('Selectionne d abord un objet');
  $('#at-cotes')?.remove();
  const b = I().boite(C().sel), t = b.getSize(new THREE.Vector3());
  const ligne = (k, ax, fl, v, u = 'mm') => `<label><span class="ax ax-${ax}">${fl}</span><input type="number" step="any" data-k="${k}" value="${(+v).toFixed(2)}"><span>${u}</span></label>`;
  const d = el(`<div class="at-flot" id="at-cotes"><h3>Cotes <button data-f>&#10005;</button></h3>
    <div class="at-seg"><button data-rel="0" class="on">Absolu</button><button data-rel="1">Decaler de</button></div>
    ${ligne('px', 'x', 'X &rarr;', b.min.x)}${ligne('py', 'y', 'Y &nearr;', b.min.y)}${ligne('pz', 'z', 'Z &uarr;', b.min.z)}
    <hr style="border-color:#2a2e37">
    ${ligne('dx', 'x', 'Long. X', t.x)}${ligne('dy', 'y', 'Larg. Y', t.y)}${ligne('dz', 'z', 'Haut. Z', t.z)}
    <hr style="border-color:#2a2e37">
    ${ligne('rx', 'x', 'Rot. X', 0, '&deg;')}${ligne('ry', 'y', 'Rot. Y', 0, '&deg;')}${ligne('rz', 'z', 'Rot. Z', 0, '&deg;')}
    <div class="act"><button data-f>Fermer</button><button class="ok" data-v>Valider (Entree)</button></div></div>`);
  document.body.appendChild(d);
  let rel = false;
  const q = k => +d.querySelector(`[data-k="${k}"]`).value;
  const valeurs = { px: b.min.x, py: b.min.y, pz: b.min.z };
  d.addEventListener('click', e => {
    if (e.target.closest('[data-f]')) d.remove();
    const r = e.target.closest('[data-rel]');
    if (r) {
      rel = r.dataset.rel === '1'; d.querySelectorAll('[data-rel]').forEach(x => x.classList.toggle('on', x === r));
      for (const k of ['px', 'py', 'pz']) d.querySelector(`[data-k="${k}"]`).value = rel ? 0 : (+valeurs[k]).toFixed(2);
    }
    if (e.target.closest('[data-v]')) valider();
  });
  d.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter') valider(); if (e.key === 'Escape') d.remove(); });
  function valider() {
    const sel = C().sel, b0 = I().boite(sel), t0 = b0.getSize(new THREE.Vector3()), c = b0.getCenter(new THREE.Vector3());
    const E = new THREE.Vector3(q('dx') / t0.x, q('dy') / t0.y, q('dz') / t0.z);
    const R = new THREE.Euler(THREE.MathUtils.degToRad(q('rx')), THREE.MathUtils.degToRad(q('ry')), THREE.MathUtils.degToRad(q('rz')));
    const M = new THREE.Matrix4().makeTranslation(c.x, c.y, c.z).multiply(new THREE.Matrix4().makeRotationFromEuler(R)).multiply(new THREE.Matrix4().makeScale(E.x, E.y, E.z)).multiply(new THREE.Matrix4().makeTranslation(-c.x, -c.y, -c.z));
    for (const o of sel) { o.mesh.updateMatrixWorld(); M.clone().multiply(o.mesh.matrixWorld).decompose(o.mesh.position, o.mesh.quaternion, o.mesh.scale); o.mesh.updateMatrixWorld(); }
    const b1 = I().boite(sel);
    const dep = rel ? new THREE.Vector3(q('px'), q('py'), q('pz')) : new THREE.Vector3(q('px') - b1.min.x, q('py') - b1.min.y, q('pz') - b1.min.z);
    for (const o of sel) { o.mesh.position.add(dep); o.mesh.updateMatrixWorld(); }
    I().selectionner(sel); I().memo();
    d.remove(); toast('Cotes appliquees');
  }
  d.querySelector('[data-k="pz"]').select();
}

// ------------------------------------------------------------------ PINCEAU DE MODELAGE
const PI = { actif: false, mode: 'tirer', r: 8, force: 0.5, sym: false, o: null, geo: null, trait: false, modifie: false };
function ouvrirPinceau() {
  aller('c3d');
  const o = C().sel[0]; if (!o) return toast('Selectionne d abord l objet a modeler');
  if ($('#at-pinceau')) return;
  // surface continue et assez fine pour etre modelee : pas de couture aux aretes, sommets ajoutes si besoin
  let g = o.mesh.geometry.clone(); g.deleteAttribute('normal'); g.deleteAttribute('uv');
  g.computeBoundingSphere();
  const ech0 = (o.mesh.scale.x + o.mesh.scale.y + o.mesh.scale.z) / 3;
  const nb = g.index ? g.index.count / 3 : g.attributes.position.count / 3;
  if (nb < 150000) g = new TessellateModifier(Math.max(g.boundingSphere.radius / 45, 0.6 / ech0), 8).modify(g.index ? g.toNonIndexed() : g);
  g.deleteAttribute('normal'); g.deleteAttribute('uv');
  g = mergeVertices(g, 1e-3);
  g.computeVertexNormals(); g.computeBoundingSphere();
  o.mesh.geometry = g; Object.assign(PI, { actif: true, o, geo: g, modifie: false });
  I().tc.detach();
  const d = el(`<div class="at-flot" id="at-pinceau"><h3>Modeler : ${o.nom || 'objet'} <button data-f>&#10005;</button></h3>
    <div class="at-seg">${[['tirer', 'Tirer'], ['pousser', 'Pousser'], ['lisser', 'Lisser'], ['aplatir', 'Aplatir']].map(([m, n]) => `<button data-mode="${m}" class="${m === PI.mode ? 'on' : ''}">${n}</button>`).join('')}</div>
    <label style="grid-template-columns:62px 1fr 34px"><span>Taille</span><input type="range" min="1" max="60" step="0.5" value="${PI.r}" data-r><b data-vr>${PI.r}</b></label>
    <label style="grid-template-columns:62px 1fr 34px"><span>Force</span><input type="range" min="0.05" max="1" step="0.05" value="${PI.force}" data-fo><b data-vf>${PI.force}</b></label>
    <label style="grid-template-columns:18px 1fr"><input type="checkbox" data-sym><span>Symetrie gauche / droite</span></label>
    <small style="color:#8b919c">Glisse sur la surface. [ et ] : taille. Alt : mode inverse. Ctrl+Z apres validation.</small>
    <div class="act"><button data-f>Annuler</button><button class="ok" data-v>Valider</button></div></div>`);
  document.body.appendChild(d);
  const fin = async garder => {
    PI.actif = false; d.remove(); I().orb.enabled = true;
    if (garder && PI.modifie) {
      const stl = new STLExporter().parse(new THREE.Mesh(PI.geo), { binary: true });
      const blob = new Blob([stl]); const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(blob); });
      const r = await api('/api/c3d/importer', { data, nom: 'modele.stl', garder: true });
      PI.o.fichier = (r.objets?.[0] || r).fichier; PI.o.type = 'import'; PI.o.params = null;
      I().memo(); toast('Modelage enregistre');
    } else if (!garder) { I().recharger(PI.o); }
    I().selectionner(C().sel);
  };
  d.addEventListener('click', e => {
    if (e.target.closest('[data-f]')) fin(false);
    if (e.target.closest('[data-v]')) fin(true);
    const m = e.target.closest('[data-mode]');
    if (m) { PI.mode = m.dataset.mode; d.querySelectorAll('[data-mode]').forEach(x => x.classList.toggle('on', x === m)); }
  });
  d.addEventListener('input', e => {
    if (e.target.dataset.r !== undefined) { PI.r = +e.target.value; d.querySelector('[data-vr]').textContent = PI.r; }
    if (e.target.dataset.fo !== undefined) { PI.force = +e.target.value; d.querySelector('[data-vf]').textContent = PI.force; }
    if (e.target.dataset.sym !== undefined) PI.sym = e.target.checked;
  });
}
function touche(e, vue) {
  const r = vue.getBoundingClientRect();
  const s = new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
  const ray = new THREE.Raycaster(); ray.setFromCamera(s, I().cam);
  return ray.intersectObject(PI.o.mesh, false)[0];
}
function coup(h, alt) {
  const p = PI.geo.attributes.position, nrm = PI.geo.attributes.normal, m = PI.o.mesh;
  const ech = (m.scale.x + m.scale.y + m.scale.z) / 3, R = PI.r / ech;
  const appliquer = (c, sx) => {
    const n0 = new THREE.Vector3(); const idx = [], poids = [];
    let cx = 0, cy = 0, cz = 0, tot = 0;
    for (let i = 0; i < p.count; i++) {
      const d = Math.hypot(p.getX(i) - c.x, p.getY(i) - c.y, p.getZ(i) - c.z);
      if (d < R) {
        const w = Math.pow(1 - d / R, 2) * (3 - 2 * (1 - d / R)) ; idx.push(i); poids.push(w);
        n0.x += nrm.getX(i) * w; n0.y += nrm.getY(i) * w; n0.z += nrm.getZ(i) * w;
        cx += p.getX(i) * w; cy += p.getY(i) * w; cz += p.getZ(i) * w; tot += w;
      }
    }
    if (!tot) return; n0.normalize(); cx /= tot; cy /= tot; cz /= tot;
    let mode = PI.mode; if (alt) mode = { tirer: 'pousser', pousser: 'tirer' }[mode] || mode;
    const pas = R * 0.06 * PI.force;
    idx.forEach((i, k) => {
      const w = poids[k]; let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      if (mode === 'tirer' || mode === 'pousser') { const s = (mode === 'tirer' ? 1 : -1) * pas * w; x += n0.x * s; y += n0.y * s; z += n0.z * s; }
      else if (mode === 'lisser') { const a = 0.35 * PI.force * w; x += (cx - x) * a; y += (cy - y) * a; z += (cz - z) * a; }
      else { const dist = (x - cx) * n0.x + (y - cy) * n0.y + (z - cz) * n0.z, a = 0.5 * PI.force * w * dist; x -= n0.x * a; y -= n0.y * a; z -= n0.z * a; }
      p.setXYZ(i, x, y, z);
    });
  };
  const c = m.worldToLocal(h.point.clone());
  appliquer(c);
  if (PI.sym) { const bs = PI.geo.boundingSphere.center; appliquer(new THREE.Vector3(2 * bs.x - c.x, c.y, c.z)); }
  p.needsUpdate = true; PI.modifie = true;
}
let _normT = 0;
document.addEventListener('pointerdown', e => {
  if (!PI.actif || !e.target.closest?.('#c3d-view') || e.button !== 0) return;
  const h = touche(e, $('#c3d-view')); if (!h) return;
  PI.trait = true; I().orb.enabled = false; e.stopPropagation(); coup(h, e.altKey);
}, true);
document.addEventListener('pointermove', e => {
  if (!PI.actif || !PI.trait) return;
  const h = touche(e, $('#c3d-view')); if (h) coup(h, e.altKey);
  if (performance.now() - _normT > 120) { PI.geo.computeVertexNormals(); _normT = performance.now(); }
}, true);
document.addEventListener('pointerup', () => {
  if (PI.trait) { PI.trait = false; I().orb.enabled = true; PI.geo.computeVertexNormals(); PI.geo.computeBoundingSphere(); PI.geo.computeBoundingBox(); }
}, true);
document.addEventListener('click', e => { if (PI.actif && e.target.closest?.('#c3d-view')) e.stopPropagation(); }, true);

// ------------------------------------------------------------------ IMAGE VERS 3D NIVEAU 2
const IA = { images: [], etat: null };
async function ouvrirIA() {
  aller('c3d');
  if ($('#at-ia')) return;
  const e = await (await fetch('/api/ia/etat')).json();
  const d = el(`<div class="at-flot" id="at-ia" style="width:310px"><h3>Image vers 3D niveau 2 <button data-f>&#10005;</button></h3>
    ${e.dispo ? `<small style="color:#8b919c">${e.carte} : ${e.vram_go} Go. ${e.installation === 'pret' ? 'IA prete.' : 'Installation : ' + e.installation}</small>
    <p style="margin:8px 0">Jusqu a 6 photos d un objet, d une piece ou d une personne. Chaque photo donne un essai de 3 a 5 min : garde le meilleur.</p>
    <input type="file" multiple accept="image/*" data-img><div class="at-gal" data-gal></div>
    <label style="grid-template-columns:62px 1fr 22px"><span>Taille</span><input type="number" data-t value="100"><span>mm</span></label>
    <label style="grid-template-columns:62px 1fr 22px"><span>Variante</span><input type="number" data-var value="42"><span></span></label>
    <div class="act"><button class="ok" data-go>Generer</button></div><div data-suivi style="margin-top:8px;color:#ffb48a"></div>`
    : `<p>L IA locale n est pas disponible sur cette machine : ${e.raison}.</p>`}</div>`);
  document.body.appendChild(d);
  const gal = () => { d.querySelector('[data-gal]').innerHTML = IA.images.map(x => `<img src="${x.url}">`).join(''); };
  d.addEventListener('click', async ev => {
    if (ev.target.closest('[data-f]')) d.remove();
    if (ev.target.closest('[data-go]')) {
      if (!IA.images.length) return toast('Ajoute au moins une photo');
      const suivi = d.querySelector('[data-suivi]');
      const { job } = await api('/api/ia/generer', { images: IA.images.map(x => x.id), taille: +d.querySelector('[data-t]').value, variante: +d.querySelector('[data-var]').value });
      window.dispatchEvent(new CustomEvent('shw:ia', { detail: 'lance une generation IA' }));
      let vus = 0;
      const t = setInterval(async () => {
        const j = await (await fetch('/api/ia/job/' + job)).json();
        suivi.textContent = j.message;
        for (; vus < j.objets.length; vus++) await C()._ajout(j.objets[vus], undefined);
        if (j.fini) { clearInterval(t); if (j.erreur) toast(j.erreur); else toast('Generation terminee'); }
      }, 3000);
    }
  });
  d.addEventListener('change', async ev => {
    if (ev.target.dataset.img === undefined) return;
    for (const f of [...ev.target.files].slice(0, 6 - IA.images.length)) {
      const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(f); });
      const { id } = await api('/api/image', { data }); IA.images.push({ id, url: data });
    }
    gal();
  });
  d.addEventListener('keydown', ev => ev.stopPropagation());
  if (IA.images.length) gal();
}

// avertissement au demarrage si la machine ne peut pas faire tourner l IA
setTimeout(async () => {
  try {
    const e = await (await fetch('/api/ia/etat')).json();
    if (e.installation === 'attente') return;
    if (e.dispo) return;
    const a = el(`<div class="at-av"><b>Image vers 3D niveau 2 (IA locale) indisponible sur cette machine.</b><br>${e.raison}. Pour l utiliser, lance SHW 3DLAB sur un PC avec une carte NVIDIA de 8 Go de memoire graphique ou plus. Tout le reste fonctionne normalement.</div>`);
    document.body.appendChild(a); setTimeout(() => a.remove(), 14000);
  } catch { }
}, 3000);

// ------------------------------------------------------------------ BIBLIOTHEQUE : tout le catalogue dans la meme scene
const lotId = () => Math.random().toString(36).slice(2, 9);
function champHTML(c, v) {
  v = v ?? c.val;
  if (c.type === 'image') return '';
  if (c.type === 'bool') return `<label style="grid-template-columns:1fr 18px"><span>${c.label}</span><input type="checkbox" data-k="${c.k}" ${v ? 'checked' : ''}></label>`;
  if (c.type === 'choix') return `<label style="grid-template-columns:1fr 1fr"><span>${c.label}</span><select data-k="${c.k}">${c.options.map(o => `<option ${o == v ? 'selected' : ''}>${o}</option>`).join('')}</select></label>`;
  if (c.type === 'texte') return `<label style="grid-template-columns:1fr 1fr"><span>${c.label}</span><input data-k="${c.k}" value="${String(v ?? '').replace(/"/g, '&quot;')}"></label>`;
  return `<label style="grid-template-columns:1fr 70px"><span>${c.label}</span><input type="number" data-k="${c.k}" min="${c.min}" max="${c.max}" step="${c.pas}" value="${v}"></label>`;
}
async function poserModele(modele, params, lot, origine) {
  const r = await api('/api/meca/piece', { nom: modele, params });
  const noms = r.info?.noms || [], poses = r.info?.assemblage;
  const x0 = origine?.x ?? I().xLibre(60), y0 = origine?.y ?? 0;
  const objs = [];
  for (let i = 0; i < r.objets.length; i++) {
    const m = poses?.[i] ? new THREE.Matrix4().fromArray(poses[i].flat ? poses[i].flat() : poses[i]) : new THREE.Matrix4();
    if (poses?.[i]) m.transpose();
    m.premultiply(new THREE.Matrix4().makeTranslation(x0, y0, 0));
    objs.push(await I().ajouterObjet({ type: 'import', fichier: r.objets[i].fichier, nom: noms[i] || modele, matrice: m.toArray(), params: { biblio: { modele, params, lot } } }));
  }
  const b = I().boite(objs);
  if (b.min.z < 0) for (const o of objs) { o.mesh.position.z -= b.min.z; o.mesh.updateMatrixWorld(); }
  return objs;
}
async function ouvrirBiblio(cle) {
  aller('c3d');
  $('#at-biblio')?.remove();
  const M = await catalogue();
  const d = el(`<div class="at-flot" id="at-biblio" style="width:320px;max-height:78vh;overflow:auto"><h3>Bibliotheque <button data-f>&#10005;</button></h3>
    <input data-cherche placeholder="Chercher un modele..." style="width:100%;box-sizing:border-box;background:#0d0f13;color:#fff;border:1px solid #2a2e37;border-radius:6px;padding:6px"><div data-corps style="margin-top:8px"></div></div>`);
  document.body.appendChild(d);
  const corps = d.querySelector('[data-corps]');
  const liste = () => {
    const q = d.querySelector('[data-cherche]').value.toLowerCase(), cats = {};
    for (const [k, m] of Object.entries(M)) if (!m.archive && m.nom.toLowerCase().includes(q)) (cats[m.cat || 'Autres'] ||= []).push([k, m]);
    corps.innerHTML = Object.entries(cats).sort().map(([c, l]) => `<div style="color:#ff6410;margin:8px 0 3px;font-weight:600">${c}</div>` + l.map(([k, m]) => `<div data-mod="${k}" style="padding:4px 6px;cursor:pointer;border-radius:5px">${m.nom}</div>`).join('')).join('');
  };
  const fiche = k => {
    const m = M[k];
    corps.innerHTML = `<a data-ret style="cursor:pointer;color:#8b919c">&larr; Retour</a><p style="font-weight:600;margin:6px 0 2px">${m.nom}</p><small style="color:#8b919c">${m.description || ''}</small>
      ${(m.champs || []).map(c => champHTML(c)).join('')}<div class="act"><button class="ok" data-aj="${k}">Ajouter a la scene</button><button data-ajshop="${k}">Scene shop</button></div>`;
  };
  d.addEventListener('click', async e => {
    if (e.target.closest('[data-f]')) d.remove();
    if (e.target.closest('[data-ret]')) liste();
    const m = e.target.closest('[data-mod]'); if (m) fiche(m.dataset.mod);
    const sh = e.target.closest('[data-ajshop]');
    if (sh) { try { const o = await poserModele(sh.dataset.ajshop, lireChamps(corps), lotId()); I().selectionner(o); I().memo(); ouvrirShop(); } catch (er) { toast(er.message); } }
    const a = e.target.closest('[data-aj]');
    if (a) {
      a.disabled = true; a.textContent = 'Calcul...';
      try { const o = await poserModele(a.dataset.aj, lireChamps(corps), lotId()); I().selectionner(o); I().memo(); toast('Ajoute a la scene'); }
      catch (er) { toast(er.message); }
      a.disabled = false; a.textContent = 'Ajouter a la scene';
    }
  });
  d.addEventListener('input', e => { if (e.target.dataset.cherche !== undefined) liste(); });
  d.addEventListener('keydown', e => e.stopPropagation());
  cle ? fiche(cle) : liste();
}
function lireChamps(z) {
  const p = {};
  z.querySelectorAll('[data-k]').forEach(i => { p[i.dataset.k] = i.type === 'checkbox' ? (i.checked ? 1 : 0) : i.type === 'number' ? +i.value : i.value; });
  return p;
}
// re-regler un modele deja dans la scene : il suffit de le selectionner
let _lotVu = null;
setInterval(async () => {
  if (!$('#tab-c3d').classList.contains('on') || PI.actif) return;
  const b = window.__C3D?.sel?.[0]?.params?.biblio, ouvert = $('#at-regl');
  if (!b) { ouvert?.remove(); _lotVu = null; return; }
  if (_lotVu === b.lot && ouvert) return;
  ouvert?.remove(); _lotVu = b.lot;
  const M = (await catalogue())[b.modele]; if (!M) return;
  const d = el(`<div class="at-flot" id="at-regl" style="width:290px;max-height:70vh;overflow:auto"><h3>${M.nom} <button data-f>&#10005;</button></h3>${(M.champs || []).map(c => champHTML(c, b.params?.[c.k])).join('')}<div class="act"><button data-shop>Scene shop</button><button class="ok" data-maj>Mettre a jour</button></div></div>`);
  document.body.appendChild(d);
  d.addEventListener('keydown', e => e.stopPropagation());
  d.addEventListener('click', async e => {
    if (e.target.closest('[data-f]')) d.remove();
    if (e.target.closest('[data-shop]')) return ouvrirShop();
    if (!e.target.closest('[data-maj]')) return;
    const lot = window.__C3D.objets.filter(o => o.params?.biblio?.lot === b.lot), bb = I().boite(lot);
    const bt = e.target.closest('[data-maj]'); bt.textContent = 'Calcul...';
    try {
      const n = await poserModele(b.modele, lireChamps(d), b.lot, { x: 0, y: 0 });
      const nb = I().boite(n), dep = new THREE.Vector3(bb.min.x - nb.min.x, bb.min.y - nb.min.y, bb.min.z - nb.min.z);
      for (const o of n) { o.mesh.position.add(dep); o.mesh.updateMatrixWorld(); }
      lot.forEach(o => I().retirer(o));
      d.remove(); _lotVu = null; I().selectionner(n); I().memo(); toast('Modele mis a jour');
    } catch (er) { toast(er.message); bt.textContent = 'Mettre a jour'; }
  });
}, 500);

// ------------------------------------------------------------------ MES PIECES
async function ouvrirPieces() {
  aller('c3d');
  $('#at-pieces')?.remove();
  const d = el(`<div class="at-flot" id="at-pieces" style="width:300px;max-height:75vh;overflow:auto"><h3>Mes pieces <button data-f>&#10005;</button></h3>
    <div class="act"><button class="ok" data-sauve>Enregistrer la selection</button></div><div data-l style="margin-top:8px"></div></div>`);
  document.body.appendChild(d);
  const rendre = async () => {
    const l = await (await fetch('/api/pieces')).json();
    d.querySelector('[data-l]').innerHTML = l.length ? l.map(p => `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0"><a data-pose="${p.id}" style="cursor:pointer">${p.nom}</a><button data-sup="${p.id}" style="background:none;border:0;color:#8b919c;cursor:pointer">&#10005;</button></div>`).join('') : '<small style="color:#8b919c">Vide. Comme le coffre d une supercar.</small>';
    d._l = l;
  };
  d.addEventListener('click', async e => {
    if (e.target.closest('[data-f]')) d.remove();
    if (e.target.closest('[data-sauve]')) {
      const sel = C().sel; if (!sel.length) return toast('Selectionne d abord une piece');
      const nom = prompt('Nom de la piece :', sel[0].nom || 'piece'); if (!nom) return;
      const b = I().boite(sel), base = new THREE.Matrix4().makeTranslation(-(b.min.x + b.max.x) / 2, -(b.min.y + b.max.y) / 2, -b.min.z);
      const objets = sel.map(o => { o.mesh.updateMatrixWorld(); return { fichier: o.fichier, nom: o.nom, trou: !!o.trou, bobine: o.bobine, matrice: base.clone().multiply(o.mesh.matrixWorld).toArray() }; });
      await api('/api/pieces', { nom, objets }); toast('Piece rangee. Enfin de l ordre dans ce garage.'); rendre();
    }
    const s = e.target.closest('[data-sup]');
    if (s) { await fetch('/api/pieces/' + s.dataset.sup, { method: 'DELETE' }); rendre(); }
    const p = e.target.closest('[data-pose]');
    if (p) {
      const x = I().xLibre(40), T = new THREE.Matrix4().makeTranslation(x, 0, 0), n = [];
      for (const o of d._l.find(q => q.id === p.dataset.pose).objets) {
        const r = await fetch(`/c3d/${o.fichier}.stl`); if (!r.ok) { toast('Maillage pas encore arrive, patiente un instant'); continue; }
        n.push(await I().ajouterObjet({ type: 'import', fichier: o.fichier, nom: o.nom, trou: o.trou, bobine: o.bobine, matrice: T.clone().multiply(new THREE.Matrix4().fromArray(o.matrice)).toArray() }));
      }
      I().selectionner(n); I().memo();
    }
  });
  rendre();
}

// ------------------------------------------------------------------ OUTILS DE PLACEMENT
function applique(f) { const s = C().sel; if (!s.length) return toast('Selectionne d abord un objet'); f(s); s.forEach(o => o.mesh.updateMatrixWorld()); I().selectionner(s); I().memo(); }
const decale = (s, v) => s.forEach(o => { o.mesh.position.add(v); o.mesh.updateMatrixWorld(); });
function repartir(ax) {
  applique(s => {
    if (s.length < 3) return toast('Il faut au moins 3 objets');
    const t = [...s].sort((a, b) => I().boite([a]).min[ax] - I().boite([b]).min[ax]);
    const b0 = I().boite([t[0]]), bn = I().boite([t.at(-1)]);
    const tailles = t.map(o => { const b = I().boite([o]); return b.max[ax] - b.min[ax]; });
    const vide = (bn.max[ax] - b0.min[ax] - tailles.reduce((a, b) => a + b, 0)) / (t.length - 1);
    let pos = b0.min[ax];
    t.forEach((o, i) => { const v = new THREE.Vector3(); v[ax] = pos - I().boite([o]).min[ax]; decale([o], v); pos += tailles[i] + vide; });
  });
}
const OUTILS_DESIGN = [
  ['Centrer sur le plateau', () => applique(s => { const c = I().boite(s).getCenter(new THREE.Vector3()); decale(s, new THREE.Vector3(-c.x, -c.y, 0)); })],
  ['Poser au sol', () => applique(s => decale(s, new THREE.Vector3(0, 0, -I().boite(s).min.z)))],
  ['Empiler sur le 1er selectionne', () => applique(s => { let z = I().boite([s[0]]).max.z; const c = I().boite([s[0]]).getCenter(new THREE.Vector3()); for (const o of s.slice(1)) { const b = I().boite([o]), cb = b.getCenter(new THREE.Vector3()); decale([o], new THREE.Vector3(c.x - cb.x, c.y - cb.y, z - b.min.z)); z = I().boite([o]).max.z; } })],
  ['Repartir sur X', () => repartir('x')], ['Repartir sur Y', () => repartir('y')], ['Repartir sur Z', () => repartir('z')],
  ['Isoler la selection', () => { const s = C().sel; C().objets.forEach(o => { o.mesh.visible = s.includes(o); }); }],
  ['Tout afficher', () => C().objets.forEach(o => { o.mesh.visible = true; })],
];
function ouvrirDesign() {
  aller('c3d');
  if ($('#at-design')) return $('#at-design').remove();
  const d = el(`<div class="at-flot" id="at-design"><h3>Design <button data-f>&#10005;</button></h3>${OUTILS_DESIGN.map(([t], i) => `<button data-o="${i}" style="display:block;width:100%;text-align:left;margin:3px 0;padding:6px 8px;background:#1d2027;color:#e9ebef;border:1px solid #2a2e37;border-radius:7px;cursor:pointer">${t}</button>`).join('')}</div>`);
  document.body.appendChild(d);
  d.addEventListener('click', e => { if (e.target.closest('[data-f]')) d.remove(); const b = e.target.closest('[data-o]'); if (b) OUTILS_DESIGN[+b.dataset.o][1](); });
}

// ------------------------------------------------------------------ SCENE SHOP : photos d'annonce, plusieurs versions
const PALETTE = ['#ff6410', '#e9ebef', '#2d3340', '#3f8efc', '#3ddc97', '#f5c542', '#c77dff', '#d94f4f'];
const FONDS = [['Blanc', '#f6f6f4'], ['Sable', '#e8dfd0'], ['Gris', '#c9ced6'], ['Nuit', '#16181d'], ['Orange', '#ff6410']];
const SH = { actif: false, groupe: null, sol: null, caches: [], fond0: null, tourne: false, mode: 'couleurs', n: 3, fond: '#f6f6f4', num: 0 };
async function geosVersion(o, k, total) {
  // k = numero de version ; une seule source par objet : le generateur s'il existe, sinon le maillage
  const fact = total > 1 ? 0.75 + 0.5 * k / (total - 1) : 1;
  const varier = p => { const q = { ...p }; let n = 0; for (const c of Object.keys(q)) if (typeof q[c] === 'number' && q[c] > 0 && n < 3 && !/rand|seed|graine/i.test(c)) { q[c] = +(q[c] * (n % 2 ? 2 - fact : fact)).toFixed(2); n++; } return q; };
  if (SH.mode === 'formes') {
    try {
      if (o.type?.startsWith('gen_')) { const r = await api('/api/c3d/generer', { nom: o.type.slice(4), params: varier(o.params || {}) }); return I().geometrie(r.objets[0].fichier); }
      if (o.params?.biblio) { const r = await api('/api/meca/piece', { nom: o.params.biblio.modele, params: varier(o.params.biblio.params || {}) }); return I().geometrie(r.objets[0].fichier); }
    } catch { }
  }
  return o.mesh.geometry;
}
// mode equipe : qui ouvre, regle ou ferme la vitrine le fait pour les deux ; rien n'est renvoye quand ca vient de l'autre
let shopDistant = false;
const annonceShop = () => { if (!shopDistant) window.dispatchEvent(new CustomEvent('shw:shop', { detail: { on: SH.actif, mode: SH.mode, n: SH.n, fond: SH.fond, sel: C().sel.map(o => o.id) } })); };
window.__SHOP = {
  ouvrir: () => ouvrirShop(),
  etat: () => ({ on: SH.actif, mode: SH.mode, n: SH.n, fond: SH.fond, sel: C().sel.map(o => o.id) }),
  appliquer(d) {
    shopDistant = true;
    try {
      Object.assign(SH, { mode: d.mode, n: d.n, fond: d.fond });
      if (d.on && !SH.actif) { const s = C().objets.filter(o => d.sel?.includes(o.id)); if (s.length) C().sel = s; ouvrirShop(); }
      else if (!d.on && SH.actif) fermerShop();
      else if (d.on) {
        I().scene.background = new THREE.Color(SH.fond);
        const f = $('#at-shop');
        if (f) { f.querySelectorAll('[data-m]').forEach(x => x.classList.toggle('on', x.dataset.m === SH.mode)); f.querySelector('[data-n]').value = SH.n; f.querySelector('[data-vn]').textContent = SH.n; }
        poserVersions();
      }
    } finally { shopDistant = false; }
  },
};
async function poserVersions() {
  const num = ++SH.num, sel = C().sel.length ? C().sel : C().objets;
  if (!sel.length) return;
  const g = new THREE.Group(); const b0 = I().boite(sel), t0 = b0.getSize(new THREE.Vector3());
  const ecart = Math.max(t0.x, t0.y) * 1.35, cx = (b0.min.x + b0.max.x) / 2, cy = (b0.min.y + b0.max.y) / 2;
  for (let k = 0; k < SH.n; k++) {
    const dx = (k - (SH.n - 1) / 2) * ecart, ech = SH.mode === 'tailles' ? 0.6 + 0.8 * k / Math.max(1, SH.n - 1) : 1;
    const dy = Math.abs(k - (SH.n - 1) / 2) * ecart * 0.28;
    let i = 0;
    for (const o of sel) {
      const geo = await geosVersion(o, k, SH.n); if (num !== SH.num) return;
      const coul = SH.mode === 'couleurs' ? PALETTE[(k + i) % PALETTE.length] : PALETTE[i % PALETTE.length];
      const m = new THREE.Mesh(geo, new THREE.MeshPhysicalMaterial({ color: coul, roughness: 0.42, clearcoat: 0.3, clearcoatRoughness: 0.5 }));
      o.mesh.updateMatrixWorld(); m.applyMatrix4(o.mesh.matrixWorld);
      m.position.x -= cx; m.position.y -= cy; m.position.z -= b0.min.z;
      m.position.multiplyScalar(ech); m.scale.multiplyScalar(ech); m.position.x += dx; m.position.y += dy;
      m.castShadow = m.receiveShadow = true; g.add(m); i++;
    }
  }
  if (SH.groupe) I().scene.remove(SH.groupe);
  SH.groupe = g; I().scene.add(g);
  const b = new THREE.Box3().setFromObject(g), c = b.getCenter(new THREE.Vector3()), r = b.getSize(new THREE.Vector3()).length();
  const lum = I().scene.children.find(x => x.isDirectionalLight);
  if (lum) { const s = r * 1.3; Object.assign(lum.shadow.camera, { left: -s, right: s, top: s, bottom: -s, far: r * 8 }); lum.shadow.camera.updateProjectionMatrix(); lum.position.set(c.x - r * 0.6, c.y - r * 0.9, r * 1.6); lum.target.position.copy(c); lum.target.updateMatrixWorld(); }
  I().orb.target.copy(c); I().cam.position.set(c.x - r * 0.25, c.y - r * 1.05, c.z + r * 0.5); I().orb.update();
}
function ouvrirShop() {
  aller('c3d');
  if (SH.actif) return;
  if (!C().objets.length) return toast('Rien a mettre en vitrine. Une vitrine vide, c est juste une fenetre.');
  SH.actif = true;
  const sc = I().scene;
  I().tc.detach();
  SH.caches = sc.children.filter(x => !x.isLight && x.visible); SH.caches.forEach(x => { x.visible = false; });
  SH.fond0 = sc.background; sc.background = new THREE.Color(SH.fond);
  SH.sol = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000), new THREE.ShadowMaterial({ opacity: 0.25 })); SH.sol.receiveShadow = true; sc.add(SH.sol);
  const d = el(`<div class="at-flot" id="at-shop"><h3>Scene shop <button data-f>&#10005;</button></h3>
    <div class="at-seg">${[['couleurs', 'Couleurs'], ['tailles', 'Tailles'], ['formes', 'Formes']].map(([m, n]) => `<button data-m="${m}" class="${SH.mode === m ? 'on' : ''}">${n}</button>`).join('')}</div>
    <label style="grid-template-columns:62px 1fr 26px"><span>Versions</span><input type="range" min="1" max="7" value="${SH.n}" data-n><b data-vn>${SH.n}</b></label>
    <div class="at-seg">${FONDS.map(([n, c]) => `<button data-fond="${c}" title="${n}" style="background:${c};color:${c === '#16181d' ? '#fff' : '#14171d'}">${n}</button>`).join('')}</div>
    <label style="grid-template-columns:18px 1fr"><input type="checkbox" data-t><span>Plateau tournant</span></label>
    <div class="act"><button class="ok" data-photo>Photo pour l annonce</button></div>
    <small style="color:#8b919c">Les versions n existent que dans cette vue : ton projet ne change pas. Formes : pour les modeles issus d un generateur.</small></div>`);
  document.body.appendChild(d);
  d.addEventListener('click', e => {
    if (e.target.closest('[data-f]')) return fermerShop();
    const m = e.target.closest('[data-m]');
    if (m) { SH.mode = m.dataset.m; d.querySelectorAll('[data-m]').forEach(x => x.classList.toggle('on', x === m)); poserVersions(); annonceShop(); }
    const f = e.target.closest('[data-fond]');
    if (f) { SH.fond = f.dataset.fond; sc.background = new THREE.Color(SH.fond); annonceShop(); }
    if (e.target.closest('[data-photo]')) photoShop();
  });
  d.addEventListener('input', e => {
    if (e.target.dataset.n !== undefined) { SH.n = +e.target.value; d.querySelector('[data-vn]').textContent = SH.n; poserVersions(); annonceShop(); }
    if (e.target.dataset.t !== undefined) I().orb.autoRotate = e.target.checked;
  });
  poserVersions(); annonceShop();
}
function fermerShop() {
  SH.actif = false; SH.num++; const sc = I().scene;
  if (SH.groupe) sc.remove(SH.groupe); sc.remove(SH.sol); SH.groupe = null;
  SH.caches.forEach(x => { x.visible = true; }); sc.background = SH.fond0; I().orb.autoRotate = false;
  $('#at-shop')?.remove(); I().selectionner(C().sel); annonceShop();
}
function photoShop() {
  const { ren, scene, cam } = I(); ren.render(scene, cam);
  const a = document.createElement('a'); a.download = `shop_${Date.now()}.png`; a.href = ren.domElement.toDataURL('image/png'); a.click();
  toast('Photo enregistree. Vendue d avance. Probablement.');
}
const btnShop = el(`<button id="at-shop-btn" style="position:fixed;z-index:60;right:calc(50% - 60px);top:76px;background:#ff6410;color:#14171d;border:0;border-radius:18px;padding:6px 14px;font:600 12px 'Segoe UI',sans-serif;cursor:pointer;display:none">&#128722; Scene shop</button>`);
document.body.appendChild(btnShop); btnShop.onclick = ouvrirShop;
setInterval(() => { btnShop.style.display = $('#tab-c3d').classList.contains('on') && !SH.actif && window.__C3D?.sel?.length ? 'block' : 'none'; }, 300);

// ------------------------------------------------------------------ TOUTES les petites fenetres se deplacent
document.head.appendChild(Object.assign(document.createElement('style'), { textContent: '.at-flot h3,.c3d-pan>h2,.c3d-pan>h3,.c3d-pan>b:first-child{cursor:move;user-select:none}' }));
document.addEventListener('pointerdown', e => {
  const f = e.target.closest?.('.at-flot,.c3d-pan'); if (!f) return;
  if (e.target.closest('input,select,textarea,button,a,label')) return;
  const titre = e.target.closest('h2,h3') || (e.clientY - f.getBoundingClientRect().top < 34);
  if (!titre) return;
  const r = f.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
  Object.assign(f.style, { position: 'fixed', left: r.left + 'px', top: r.top + 'px', right: 'auto', bottom: 'auto', transform: 'none', margin: 0 });
  const bouge = ev => { f.style.left = Math.max(0, Math.min(innerWidth - 60, ev.clientX - dx)) + 'px'; f.style.top = Math.max(0, Math.min(innerHeight - 30, ev.clientY - dy)) + 'px'; };
  const fin = () => { removeEventListener('pointermove', bouge); removeEventListener('pointerup', fin); try { if (f.id) localStorage.setItem('at-pos-' + f.id, JSON.stringify([f.style.left, f.style.top])); } catch { } };
  addEventListener('pointermove', bouge); addEventListener('pointerup', fin); e.preventDefault();
}, true);
new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.id && n.classList?.contains('at-flot')) { try { const p = JSON.parse(localStorage.getItem('at-pos-' + n.id)); if (p) Object.assign(n.style, { left: p[0], top: p[1], right: 'auto' }); } catch { } } }).observe(document.body, { childList: true });
document.addEventListener('click', e => { const b = e.target.closest?.('[data-biblio]'); if (b) ouvrirBiblio(b.dataset.biblio); });

// ------------------------------------------------------------------ VUE EN COUPE
const COUPE = { plan: new THREE.Plane(new THREE.Vector3(0, 0, -1), 0) };
function ouvrirCoupe() {
  aller('c3d');
  if ($('#at-coupe')) return;
  const b = I().boite(C().objets), z = b.isEmpty() ? [0, 100] : [b.min.z, b.max.z];
  I().ren.localClippingEnabled = true; I().ren.clippingPlanes = [COUPE.plan];
  const d = el(`<div class="at-flot" id="at-coupe"><h3>Vue en coupe <button data-f>&#10005;</button></h3>
    <div class="at-seg"><button data-ax="x">X</button><button data-ax="y">Y</button><button data-ax="z" class="on">Z</button></div>
    <input type="range" style="width:100%" data-pos min="${z[0]}" max="${z[1]}" step="0.1" value="${z[1]}"><small style="color:#8b919c">Pour voir l interieur. Ne change pas les pieces.</small></div>`);
  document.body.appendChild(d);
  const maj = () => { COUPE.plan.constant = +d.querySelector('[data-pos]').value; };
  maj();
  d.addEventListener('input', maj);
  d.addEventListener('click', e => {
    if (e.target.closest('[data-f]')) { I().ren.clippingPlanes = []; d.remove(); }
    const a = e.target.closest('[data-ax]');
    if (a) {
      const k = a.dataset.ax, bb = I().boite(C().objets);
      COUPE.plan.normal.set(k === 'x' ? -1 : 0, k === 'y' ? -1 : 0, k === 'z' ? -1 : 0);
      const r = d.querySelector('[data-pos]'); r.min = bb.min[k]; r.max = bb.max[k]; r.value = bb.max[k];
      d.querySelectorAll('[data-ax]').forEach(x => x.classList.toggle('on', x === a)); maj();
    }
  });
}

// ------------------------------------------------------------------ TUTO
const ETAPES = [
  ['[data-a="biblio"]', 'La bibliotheque', 'Touche L : tous les modeles parametriques. Ils arrivent dans cette scene et se re-reglent quand tu les selectionnes.'],
  ['[data-a="pieces"]', 'Mes pieces', 'Touche P : range une piece reussie. Hugo la retrouve chez lui, et elle se pose en un clic.'],
  ['#at-rail', 'Tous les modules ici', 'Atelier, prenoms, keycaps, pieces mecaniques et IA 3D. Tout ce que tu crees peut rejoindre la meme scene.'],
  ['#tab-c3d .c3d-lib', 'Formes et generateurs', 'Clique ou glisse une forme sur le plan. Les generateurs creent des objets complets : vase, keycap, texte, image...'],
  ['#c3d-view', 'La scene', 'Clic : selectionner. Clic droit : menu de l objet. W, E, R : deplacer, tourner, etirer.'],
  ['[data-a="cotes"]', 'Cotes au clavier', 'Touche N : tape X, Y, Z, les dimensions ou la rotation, puis Entree. La piece s adapte.'],
  ['[data-a="pinceau"]', 'Modeler', 'Touche B : tire, pousse, lisse ou aplatis la surface, avec la taille de pinceau que tu veux.'],
  ['[data-a="ia"]', 'IA 3D', 'Depose des photos : l IA de ton PC reconstruit l objet en 3D, puis il arrive dans la scene.'],
  ['[data-a="cherche"]', 'Tout chercher', 'Ctrl+K : tape ce que tu veux, outil, forme ou projet, et Entree.'],
  ['#eq-fen', 'Travailler a deux', 'Travailler avec : meme page, memes objets, meme vue, en direct.'],
];
function lancerTuto(i = 0) {
  aller('c3d');
  $('#at-tuto')?.remove(); $$('.at-cible').forEach(x => x.classList.remove('at-cible'));
  if (i >= ETAPES.length) return;
  const [s, t, m] = ETAPES[i], c = $(s); c?.classList.add('at-cible');
  const r = c?.getBoundingClientRect() || { right: 200, top: 100 };
  const d = el(`<div id="at-tuto"><b>${t}</b>${m}<div class="act"><button data-q>Fermer</button><span>${i + 1} / ${ETAPES.length}</span><button data-n>${i === ETAPES.length - 1 ? 'Fin' : 'Suivant'}</button></div></div>`);
  d.style.left = Math.min(innerWidth - 340, Math.max(70, r.left > innerWidth / 2 ? r.left - 340 : r.right + 12)) + 'px';
  d.style.top = Math.min(innerHeight - 170, Math.max(70, r.top + 10)) + 'px';
  document.body.appendChild(d);
  d.querySelector('[data-q]').onclick = () => lancerTuto(99);
  d.querySelector('[data-n]').onclick = () => lancerTuto(i + 1);
}
try { if (!localStorage.getItem('shw-tuto')) { localStorage.setItem('shw-tuto', '1'); setTimeout(() => lancerTuto(), 2500); } } catch { }

// ------------------------------------------------------------------ raccourcis
document.addEventListener('keydown', e => {
  const ctrl = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
  if (ctrl && k === 'k') { e.preventDefault(); e.stopPropagation(); return ouvrirRecherche(); }
  if (dansSaisie() || !$('#tab-c3d').classList.contains('on')) return;
  if (k === 'v' && !ctrl) { e.preventDefault(); ouvrirShop(); }
  if (k === 'p' && !ctrl) { e.preventDefault(); ouvrirPieces(); }
  if (k === 'g' && !ctrl) { e.preventDefault(); ouvrirDesign(); }
  if (k === 'l' && !ctrl) { e.preventDefault(); ouvrirBiblio(); }
  if (k === 'c' && !ctrl) { e.preventDefault(); ouvrirCoupe(); }
  if (k === 'n' && !ctrl) { e.preventDefault(); ouvrirCotes(); }
  if (k === 'b' && !ctrl) { e.preventDefault(); ouvrirPinceau(); }
  if (PI.actif && (k === '[' || k === ']')) { PI.r = Math.max(1, Math.min(60, PI.r + (k === ']' ? 1 : -1))); const b = $('#at-pinceau [data-vr]'); if (b) { b.textContent = PI.r; $('#at-pinceau [data-r]').value = PI.r; } }
}, true);
let _cat = null;
const catalogue = async () => _cat ||= await (await fetch('/api/catalogue')).json();
