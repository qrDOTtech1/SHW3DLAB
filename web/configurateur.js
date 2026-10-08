// CONFIGURATEUR DE PROJET : chaque modele de projet (Vibe Deck, ...) a sa propre interface de personnalisation,
// construite a partir de son schema (groupes de reglages) : apercu 3D monte / eclate, versions, liste d'achats,
// export STL, impression, enregistrement dans l'onglet Projets.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { simuler, tracer } from './simpneu.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const A = () => window.ATELIER;
const api = (u, b) => A().api(u, b);
const toast = m => A().toast(m);

const F = { modeles: {}, modele: null, params: {}, versions: {}, version: null, eclate: false, info: null, objets: [], geo: {}, projet: null };
window.__CFG = F;

// ------------------------------------------------------------------ scene (rendu soigne : lumiere douce, sol a ombre)
const el = $('#cfg-view');
const ren = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
ren.setPixelRatio(Math.min(devicePixelRatio, 2)); ren.shadowMap.enabled = true; ren.shadowMap.type = THREE.PCFSoftShadowMap;
ren.toneMapping = THREE.ACESFilmicToneMapping; ren.outputColorSpace = THREE.SRGBColorSpace;
el.appendChild(ren.domElement);
const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(30, 1, 1, 5000); cam.up.set(0, 0, 1); cam.position.set(-160, -260, 190);
const orb = new OrbitControls(cam, ren.domElement); orb.enableDamping = true; orb.target.set(0, 0, 30);
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a93a3, 1.6));
const cle = new THREE.DirectionalLight(0xffffff, 2.4); cle.position.set(-180, -240, 420); cle.castShadow = true;
cle.shadow.mapSize.set(2048, 2048); cle.shadow.radius = 6; Object.assign(cle.shadow.camera, { left: -250, right: 250, top: 250, bottom: -250 });
scene.add(cle);
const contre = new THREE.DirectionalLight(0xcfe0ff, 0.9); contre.position.set(200, 260, 160); scene.add(contre);
const sol = new THREE.Mesh(new THREE.PlaneGeometry(3000, 3000), new THREE.ShadowMaterial({ opacity: 0.22 })); sol.receiveShadow = true; scene.add(sol);
const groupe = new THREE.Group(); scene.add(groupe);
function taille() { const w = el.clientWidth, h = el.clientHeight; if (!w) return; ren.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix(); }
new ResizeObserver(taille).observe(el);
(function boucle() { requestAnimationFrame(boucle); orb.update(); ren.render(scene, cam); })();
const loader = new STLLoader();
const charger = f => F.geo[f] || (F.geo[f] = new Promise((ok, ko) => loader.load(`/c3d/${f}.stl`, g => { g.computeVertexNormals(); ok(g); }, undefined, ko)));
const MATIERE = c => new THREE.MeshPhysicalMaterial({ color: c, roughness: 0.42, metalness: 0.05, clearcoat: 0.25, clearcoatRoughness: 0.6 });

// ------------------------------------------------------------------ interface (construite depuis le schema)
const COUL_CHASSIS = [['plancher', '#3d9970'], ['faux', '#2ecc71'], ['tiroir_b', '#f1c40f'], ['tiroir_e', '#e67e22'], ['cage', '#8e44ad'], ['module', '#7f8c8d'],
  ['triangle', '#34495e'], ['porte_moyeu', '#c0392b'], ['pushrod', '#ecf0f1'], ['culbuteur', '#e74c3c'], ['verin', '#3498db'], ['distrib', '#16a085'], ['tiroir_d', '#f39c12']];
function couleurPiece(nom) {
  const c = F.couleurs?.[nom] || F.modeles[F.modele]?.couleurs?.[nom];
  if (c) return c;
  if (nom?.startsWith('ch_')) { const k = COUL_CHASSIS.find(([a]) => nom.slice(3).startsWith(a)); if (k) return k[1]; }
  return '#cfd3da';
}
function construireInterface() {
  const m = F.modeles[F.modele];
  $('#cfg-titre').textContent = m.nom; $('#cfg-desc').textContent = m.description;
  const groupes = {};
  for (const c of m.champs) (groupes[c.groupe || 'Reglages'] ||= []).push(c);
  $('#cfg-reglages').innerHTML = Object.entries(groupes).map(([g, l], gi) => `<details class="cfg-groupe" ${gi < 3 ? 'open' : ''}><summary>${g}</summary>
    ${l.map(c => {
      const v = F.params[c.k] ?? c.val;
      if (c.type === 'bool') return `<label class="cfg-ligne chk"><span>${c.label}</span><input type="checkbox" data-k="${c.k}" ${v ? 'checked' : ''}></label>`;
      if (c.type === 'choix') return `<label class="cfg-ligne"><span>${c.label}</span><div class="cfg-segments" data-k="${c.k}">${c.options.map(o => `<button class="${o == v ? 'on' : ''}" data-v="${o}">${LIBELLES[o] || o}</button>`).join('')}</div></label>`;
      return `<label class="cfg-ligne"><span>${c.label}<b data-v="${c.k}">${v}</b></span><input type="range" data-k="${c.k}" min="${c.min}" max="${c.max}" step="${c.pas}" value="${v}"></label>`;
    }).join('')}</details>`).join('');
  $$('#cfg-reglages input[data-k]').forEach(i => i.addEventListener('input', () => {
    F.params[i.dataset.k] = i.type === 'checkbox' ? (i.checked ? 1 : 0) : +i.value;
    const b = $(`#cfg-reglages [data-v="${i.dataset.k}"]`); if (b) b.textContent = i.value;
    F.version = null; majVersions(); regenerer();
  }));
  $$('#cfg-reglages .cfg-segments button').forEach(b => b.onclick = e => {
    e.preventDefault(); const k = b.parentElement.dataset.k; F.params[k] = b.dataset.v;
    b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); F.version = null; majVersions(); regenerer();
  });
  majVersions();
}
const LIBELLES = { placo: 'Vis placo', imprimee: 'Imprimee', m3: 'Vis M3', lego: 'Tube LEGO', tube8: 'Tube d8', cannele: 'Cannele', g18: 'G1/8', m5: 'M5', perceuse: 'Perceuse', compact: 'Compact (moteur)', guition_43: 'Guition 4.3"', oled_096: 'OLED 0.96"', oled_13: 'OLED 1.3"', aucun: 'Aucun', crans: 'A crans', servo: 'Motorise', fixe: 'Fixe', sg90: 'SG90', mg90s: 'MG90S' };

// ------------------------------------------------------------------ generation + affichage
let _t = null, _n = 0;
function regenerer() { clearTimeout(_t); _t = setTimeout(generer, 220); }
async function generer() {
  const n = ++_n; $('#cfg-etat').textContent = 'Calcul...';
  try {
    const r = await api('/api/meca/piece', { nom: F.modele, params: avecBase() });
    if (n !== _n) return;
    F.info = r.info; F.objets = r.objets;
    groupe.clear();
    const noms = r.info.noms || r.objets.map((_, i) => 'piece ' + (i + 1));
    let x = 0;
    for (const [i, o] of r.objets.entries()) {
      const mesh = new THREE.Mesh(await charger(o.fichier), MATIERE(couleurPiece(noms[i])));
      mesh.castShadow = true; mesh.receiveShadow = true; mesh.userData.nom = noms[i]; mesh.userData.fichier = o.fichier;
      if (F.masques?.has(noms[i])) mesh.visible = false;
      if (F.sel?.has(noms[i])) surligner(mesh, true);
      const T = r.info.assemblage?.[i];
      if (T && !F.eclate) new THREE.Matrix4().fromArray(T.flat()).transpose().decompose(mesh.position, mesh.quaternion, mesh.scale);
      else { mesh.updateMatrixWorld(); const b = new THREE.Box3().setFromObject(mesh); mesh.position.x = x - b.min.x; x += b.max.x - b.min.x + 12; }
      groupe.add(mesh);
    }
    const b = new THREE.Box3().setFromObject(groupe), c = b.getCenter(new THREE.Vector3());
    groupe.position.x = -c.x; groupe.position.y = -c.y;
    infos(); performances(); if (!F.cadre) { cadrer(); F.cadre = true; }
  } catch (e) { if (n === _n) $('#cfg-etat').textContent = e.message; }
}
function infos() {
  const i = F.info || {};
  const poids = F.objets.reduce((a, o) => a + (o.analyse?.poids_g || 0), 0);
  $('#cfg-etat').innerHTML = [i.dimensions_socle_mm ? `${i.dimensions_socle_mm.join(' x ')} mm` : '', i.touches ? `${i.touches} touches` : '', `${F.objets.length} pieces`, `${poids.toFixed(0)} g de filament`].filter(Boolean).join(' &middot; ');
  $('#cfg-achats').innerHTML = (i.quincaillerie || []).map(x => `<li>${x}</li>`).join('');
  $('#cfg-verif').innerHTML = i.a_verifier ? `<p class="badge warn">${i.a_verifier}</p>` : '';
  const noms = i.noms || [];
  $('#cfg-pieces').innerHTML = F.objets.map((o, k) => `<div class="cfg-piece"><i style="background:${couleurPiece(noms[k])}"></i><span>${noms[k] || 'piece'}</span><b>${o.analyse?.poids_g ?? '-'} g</b></div>`).join('');
}
function cadrer() {
  const b = new THREE.Box3().setFromObject(groupe); if (b.isEmpty()) return;
  const c = b.getCenter(new THREE.Vector3()), r = b.getSize(new THREE.Vector3()).length();
  orb.target.copy(c); cam.position.copy(c).add(new THREE.Vector3(-0.35, -0.85, 0.55).normalize().multiplyScalar(r * 1.55)); orb.update();
}
$('#cfg-eclate').onclick = () => { F.eclate = !F.eclate; $('#cfg-eclate').classList.toggle('on', F.eclate); F.cadre = false; generer(); };
$('#cfg-cadrer').onclick = cadrer;

// ------------------------------------------------------------------ performances du compresseur (simulation du cycle reel)
let _tp = null;
async function performances(optimiser = false) {
  const m = F.modeles[F.modele], z = $('#cfg-perf');
  z.hidden = m?.simulation !== 'pneumatique'; if (z.hidden) return simulation();
  clearTimeout(_tp);
  _tp = setTimeout(async () => {
    $('#perf-msg').textContent = optimiser ? 'Optimisation des lumieres (simulation de ~300 cycles)...' : 'Simulation du cycle...';
    try {
      const r = await api('/api/compresseur/performances', { params: F.params, rpm: +$('#perf-rpm').value || 1200, optimiser });
      F.perf = r;
      if (r.optimum) {
        F.params.angle_admission = r.optimum.angle_admission; F.params.angle_refoulement = r.optimum.angle_refoulement;
        construireInterface(); regenerer();
        $('#perf-msg').textContent = `Lumieres optimisees : admission ${r.optimum.angle_admission} deg, refoulement ${r.optimum.angle_refoulement} deg (geometrie regeneree)`;
      } else $('#perf-msg').textContent = '';
      tracerPerf(); simulation();
    } catch (e) { $('#perf-msg').textContent = e.message; }
  }, optimiser ? 0 : 400);
}
function tracerPerf() {
  const r = F.perf; if (!r) return;
  const cv = $('#cfg-perf-graph'), ctx = cv.getContext('2d'), W = cv.width, H = cv.height, mg = 30;
  ctx.fillStyle = '#10141b'; ctx.fillRect(0, 0, W, H);
  const pts = r.courbe, pm = Math.max(...pts.map(q => q.p_reservoir_bar), 1), qm = Math.max(...pts.map(q => q.debit_libre_L_min), 0.5), cm = Math.max(...pts.map(q => q.couple_max_Nm), 0.05);
  const X = p => mg + (W - mg - 30) * p / pm, Yq = q => H - 20 - (H - 34) * q / qm, Yc = c => H - 20 - (H - 34) * c / cm;
  ctx.strokeStyle = '#232934'; ctx.fillStyle = '#8a93a3'; ctx.font = '10px Inter, sans-serif';
  for (let k = 0; k <= 4; k++) { const y = Yq(qm * k / 4); ctx.beginPath(); ctx.moveTo(mg, y); ctx.lineTo(W - 30, y); ctx.stroke(); ctx.fillText((qm * k / 4).toFixed(1), 2, y + 3); }
  ctx.fillText('L/min', 2, 10); ctx.fillText(`${pm.toFixed(1)} bar`, W - 60, H - 5);
  const courbe = (f, col) => { ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.beginPath(); pts.forEach((q, i) => i ? ctx.lineTo(X(q.p_reservoir_bar), f(q)) : ctx.moveTo(X(q.p_reservoir_bar), f(q))); ctx.stroke(); };
  courbe(q => Yq(q.debit_libre_L_min), '#ff7a2f'); courbe(q => Yc(q.couple_max_Nm), '#7fb8a4');
  ctx.fillStyle = '#ff7a2f'; ctx.fillText('debit', W - 70, 14); ctx.fillStyle = '#7fb8a4'; ctx.fillText('couple max', W - 70, 26);
  const c = r.cycle;
  $('#cfg-perf-stats').innerHTML = `<div><span>Debit a 0 bar</span><b>${pts[0].debit_libre_L_min.toFixed(1)} L/min</b></div>
    <div><span>Pression maxi</span><b>${typeof r.pression_maxi_bar === 'number' ? r.pression_maxi_bar.toFixed(2) + ' bar' : r.pression_maxi_bar + ' bar'}</b></div>
    <div><span>Couple moyen / pointe (1 bar)</span><b>${c.couple_moyen_Nm} / ${c.couple_max_Nm} N.m</b></div>
    <div><span>Puissance (1 bar)</span><b>${c.puissance_W} W</b></div>
    <div><span>Rendement volumetrique (1 bar)</span><b>${(c.rendement_volumetrique * 100).toFixed(0)} %</b></div>
    <div><span>Chambre : pression maxi</span><b>${c.p_chambre_max_bar} bar</b></div>`;
}
$('#perf-rpm').addEventListener('change', () => performances());
$('#perf-optimiser').onclick = () => performances(true);

// ------------------------------------------------------------------ simulation (modeles qui en declarent une)
F.sim = { mode: 'tor' };
function simulation() {
  const m = F.modeles[F.modele], z = $('#cfg-sim');
  z.hidden = m?.simulation !== 'pneumatique';
  if (z.hidden || !F.info) return;
  const c = { ...F.sim, cyl_cm3: F.info.cylindree_chambre_cm3 || 5, taux_geo: F.info.taux_compression_geometrique || 10, dt: 0.05, courbe: F.perf?.courbe, rpm_ref: F.perf?.rpm };
  $$('#cfg-sim [data-s]').forEach(i => c[i.dataset.s] = +i.value);
  const r = simuler(c);
  tracer($('#cfg-sim-graph'), r, c);
  const debit = F.perf?.courbe?.length ? F.perf.courbe[0].debit_libre_L_min * c.n_max / (F.perf.rpm || c.n_max) : c.cyl_cm3 / 1000 * c.n_max * 0.85;   // cycle reel simule
  $('#cfg-sim-stats').innerHTML = `<div><span>Debit a vide</span><b>${debit.toFixed(1)} L/min</b></div>
    <div><span>Pression max</span><b>${r.pmax.toFixed(2)} bar</b></div>
    <div><span>Consigne atteinte</span><b>${r.tConsigne === null ? 'jamais' : r.tConsigne.toFixed(1) + ' s'}</b></div>
    <div><span>Moteur en marche</span><b>${r.marche_pct.toFixed(0)} %</b></div>
    <div><span>Force du verin</span><b>${r.force_verin_N.toFixed(0)} N</b></div>
    <div><span>Limite joints</span><b>${(r.pmaxAbs - 1).toFixed(1)} bar</b></div>`;
}
$$('#cfg-sim [data-s]').forEach(i => i.addEventListener('input', () => { const b = $(`#cfg-sim [data-sv="${i.dataset.s}"]`); if (b) b.textContent = i.value; simulation(); }));
$$('#sim-mode button').forEach(b => b.onclick = e => { e.preventDefault(); F.sim.mode = b.dataset.v; $$('#sim-mode button').forEach(x => x.classList.toggle('on', x === b)); simulation(); });

// ------------------------------------------------------------------ versions (a la volee)
function majVersions() {
  const z = $('#cfg-versions');
  const noms = Object.keys(F.versions);
  z.innerHTML = noms.map(n => `<button class="cfg-version ${n === F.version ? 'on' : ''}" data-ver="${n}">${n}<span data-suppr="${n}" title="Supprimer">&#10005;</span></button>`).join('')
    || '<p class="mute">Aucune version : regle puis "Enregistrer la version".</p>';
  z.querySelectorAll('[data-ver]').forEach(b => b.onclick = e => {
    if (e.target.dataset.suppr) { delete F.versions[e.target.dataset.suppr]; if (F.version === e.target.dataset.suppr) F.version = null; return majVersions(); }
    F.version = b.dataset.ver; F.params = JSON.parse(JSON.stringify(F.versions[F.version])); construireInterface(); generer();
  });
}
$('#cfg-version-save').onclick = () => {
  const n = $('#cfg-version-nom').value.trim() || `Version ${Object.keys(F.versions).length + 1}`;
  F.versions[n] = JSON.parse(JSON.stringify(F.params)); F.version = n; $('#cfg-version-nom').value = ''; majVersions(); toast(`Version "${n}" enregistree`);
};

// ------------------------------------------------------------------ actions
$('#cfg-export').onclick = async () => {
  const r = await fetch('/api/meca/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nom: F.modele, params: avecBase() }) });
  if (!r.ok) return toast((await r.text()).slice(0, 200));
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = `${F.modele}${F.version ? '_' + F.version : ''}.zip`; a.click();
};
$('#cfg-imprimer').onclick = async () => {
  if (!F.objets.length) return;
  const noms = F.info?.noms || [];
  const objets = F.objets.map((o, k) => ({ fichier: o.fichier, matrice: null, trou: false, nom: noms[k] || 'piece', bobine: F.bobines?.[noms[k]] || A().S.etat.bobines[0].id }));
  try {
    const { job } = await api('/api/c3d/imprimer', { outil: 'imprimer', objets });
    await A().suivre(job, '#cfg-prog', res => { const S = A().S; S.gen = res; S.tranches = {}; A().renderPlateauxImp(); toast(`${res.plateaux.length} plateau(x) prets`); $('[data-tab="imprimer"]').click(); });
  } catch (e) { toast(e.message); }
};
$('#cfg-keycaps').onclick = async () => {
  const n = F.info?.touches || 0; if (!n || !window.__KC) return;
  document.getElementById('kc-clavier').value = F.projet?.nom || F.modeles[F.modele].nom;
  $('[data-tab="kc"]').click(); await new Promise(r => setTimeout(r, 300));
  const sel = document.getElementById('kc-rangee'); sel.value = 'macro'; sel.dispatchEvent(new Event('change'));
  toast(`Touches macro ajoutees au lot (${n} switchs sur ce ${F.modeles[F.modele].nom})`);
};

// ------------------------------------------------------------------ couleurs par piece (bobines)
function majCouleurs() {
  const noms = F.info?.noms || []; const bobs = A().S.etat?.bobines || [];
  F.bobines ||= {};
  $('#cfg-couleurs').innerHTML = noms.map(n => `<label class="cfg-ligne"><span>${n}</span><select data-piece="${n}">${bobs.map(b => `<option value="${b.id}" ${F.bobines[n] === b.id ? 'selected' : ''}>${b.nom}</option>`).join('')}</select></label>`).join('');
  $$('#cfg-couleurs [data-piece]').forEach(s => s.onchange = () => { F.bobines[s.dataset.piece] = s.value; (F.couleurs ||= {})[s.dataset.piece] = A().bobine(s.value)?.couleur; generer(); });
}
const _infos = infos; // eslint
// ------------------------------------------------------------------ module de projet (onglet Projets)
F.ouvrirModele = async (modele, donnees = {}) => {
  F.modele = modele; F.cadre = false;
  F.params = JSON.parse(JSON.stringify(donnees.params || {}));
  F.reference = donnees.reference || null; afficherReference();
  F.versions = donnees.versions || {}; F.version = donnees.version || null; F.bobines = donnees.bobines || {}; F.couleurs = donnees.couleurs || {};
  const m = F.modeles[modele];
  for (const c of m.champs) if (F.params[c.k] === undefined) F.params[c.k] = c.val;
  $('#nav-cfg').hidden = false; $('#nav-cfg').textContent = m.nom; $('#nav-cfg').click();
  construireInterface(); await generer(); majCouleurs(); setTimeout(taille, 30);
};
// le STL de base du projet (id 12 hex) est passe au calcul
const avecBase = () => { const id = (String(F.reference?.fichier || '').match(/[0-9a-f]{12}/) || [])[0]; return id ? { ...F.params, base: id } : F.params; };
F.baseImportee = async (r, nom) => { F.reference = { fichier: r.fichier, nom }; afficherReference(); };
function afficherReference() {
  scene.getObjectByName('reference') && scene.remove(scene.getObjectByName('reference'));
  if (!F.reference) return;
  charger(F.reference.fichier).then(g => { const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x9fb4d0, transparent: true, opacity: 0.3, depthWrite: false })); m.name = 'reference'; scene.add(m); });
}
F.exporter = () => ({ reference: F.reference || null, modele: F.modele, params: F.params, versions: F.versions, version: F.version, bobines: F.bobines, couleurs: F.couleurs });
F.charger = d => F.ouvrirModele(d.modele || F.modele, d);
F.vider = type => F.ouvrirModele(type || F.modele, {});
F.miniature = () => { ren.render(scene, cam); const c = document.createElement('canvas'); c.width = 320; c.height = 220; c.getContext('2d').drawImage(ren.domElement, 0, 0, 320, 220); return c.toDataURL('image/png'); };

(async function init() {
  for (let i = 0; i < 60 && !(A()?.S?.etat && window.__PROJETS); i++) await new Promise(r => setTimeout(r, 100));
  F.modeles = await api('/api/modeles');
  // chaque modele devient un TYPE de projet (sa propre interface) dans l'onglet Projets
  window.__PROJETS?.enregistrerModeles?.(F.modeles);
  document.addEventListener('click', e => { if (e.target.closest('#nav-cfg')) setTimeout(taille, 30); });
})();

// ------------------------------------------------------------------ PINCEAU DE CARROSSIER (clic droit sur une piece)
// Retouches stockees dans F.params.retouches : { decoupe: {piece: [[x,y,z,nx,ny,nz,r,'+'|'-']]}, surface: [[...,'lisser'|'raboter']] }
// Coordonnees = repere du modele (vue montee : point monde - position du groupe).
const PZ = { actif: false, mode: null, cible: null, r: 4, trait: [], peint: false, marques: new THREE.Group() };
scene.add(PZ.marques);
const rc = new THREE.Raycaster(), souris = new THREE.Vector2();
function viser(e) {
  const b = ren.domElement.getBoundingClientRect();
  souris.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
  rc.setFromCamera(souris, cam);
  const h = rc.intersectObjects(groupe.children, false)[0];
  if (!h) return null;
  const n = h.face.normal.clone().transformDirection(h.object.matrixWorld).normalize();
  const p = h.point.clone().sub(groupe.position);
  return { p, n, nom: h.object.userData.nom, monde: h.point };
}
const piecesDetachables = () => (F.info?.noms || []).filter(n => !/^troncon|^eclisse|^ch_/.test(n));
const COUL_MODE = { '+': 0x2ecc71, '-': 0xe74c3c, lisser: 0x3498db, raboter: 0xf39c12 };
function marque(h) {
  const m = new THREE.Mesh(new THREE.CircleGeometry(PZ.r, 20), new THREE.MeshBasicMaterial({ color: COUL_MODE[PZ.mode], transparent: true, opacity: 0.45, depthWrite: false, side: THREE.DoubleSide }));
  m.position.copy(h.monde).addScaledVector(h.n, 0.25); m.lookAt(h.monde.clone().add(h.n)); PZ.marques.add(m);
}
function quitterPinceau() { PZ.actif = false; orb.enabled = true; barre(); }
function barre() {
  let d = $('#pz-barre');
  if (!PZ.actif) { d?.remove(); return; }
  if (!d) { d = document.createElement('div'); d.id = 'pz-barre'; el.parentElement.appendChild(d); }
  d.style.cssText = 'position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:20;background:rgba(20,22,28,.92);color:#fff;padding:8px 12px;border-radius:12px;display:flex;gap:8px;align-items:center;font-size:13px;box-shadow:0 6px 24px rgba(0,0,0,.3)';
  const lib = { '+': `Ajouter a <b>${PZ.cible}</b>`, '-': `Rendre a la caisse (retirer de <b>${PZ.cible}</b>)`, lisser: 'Lisser la tole', raboter: 'Raboter (aplanir)' }[PZ.mode];
  d.innerHTML = `<span style="width:10px;height:10px;border-radius:50%;background:#${COUL_MODE[PZ.mode].toString(16).padStart(6, '0')}"></span>${lib}
    <span style="opacity:.6">pinceau</span>${[2, 4, 8, 15].map(r => `<button data-pzr="${r}" class="${r === PZ.r ? 'on' : ''}" style="padding:2px 8px">${r} mm</button>`).join('')}
    <button data-pz="annuler">Annuler trait</button><button class="primary" data-pz="ok">Appliquer</button><button data-pz="fin">Quitter</button>`;
  d.querySelectorAll('[data-pzr]').forEach(b => b.onclick = () => { PZ.r = +b.dataset.pzr; barre(); });
  d.querySelector('[data-pz="annuler"]').onclick = annulerTrait;
  d.querySelector('[data-pz="ok"]').onclick = () => { quitterPinceau(); PZ.marques.clear(); regenerer(); toast('Retouches appliquees : recalcul des pieces...'); };
  d.querySelector('[data-pz="fin"]').onclick = quitterPinceau;
}
function liste() {
  F.params.retouches = F.params.retouches || { decoupe: {}, surface: [] };
  const R = F.params.retouches;
  R.decoupe = R.decoupe || {}; R.surface = R.surface || [];
  if (PZ.mode === '+' || PZ.mode === '-') return (R.decoupe[PZ.cible] = R.decoupe[PZ.cible] || []);
  return R.surface;
}
function annulerTrait() {
  const H = F.params.retouches?._hist || [];
  const der = H.pop(); if (!der) return toast('Rien a annuler');
  const l = der.cle === 'surface' ? F.params.retouches.surface : F.params.retouches.decoupe[der.cle];
  l.splice(l.length - der.n, der.n);
  for (let i = 0; i < der.n && PZ.marques.children.length; i++) PZ.marques.remove(PZ.marques.children[PZ.marques.children.length - 1]);
}
function demarrer(mode, cible) {
  if (F.eclate) return toast('Repasse en vue montee (bouton Eclate) pour peindre');
  PZ.actif = true; PZ.mode = mode; PZ.cible = cible; orb.enabled = false; barre();
  toast('Glisse sur la carrosserie pour peindre - clic milieu pour tourner - Echap pour quitter');
}
ren.domElement.addEventListener('contextmenu', e => {
  e.preventDefault();
  const h = viser(e);
  if (!h) return menuVide(e);
  $('#pz-menu')?.remove();
  const m = document.createElement('div'); m.id = 'pz-menu';
  m.style.cssText = `position:fixed;left:${e.clientX}px;top:${e.clientY}px;z-index:50;background:#1c1f26;color:#eee;border-radius:10px;padding:6px;min-width:260px;box-shadow:0 8px 30px rgba(0,0,0,.4);font-size:13px`;
  const det = piecesDetachables(), ici = det.includes(h.nom) ? h.nom : null;
  m.innerHTML = `<div style="padding:4px 10px;opacity:.6">${h.nom}</div>`;
  const sep = () => { const d = document.createElement('div'); d.style.cssText = 'height:1px;background:#333;margin:4px 6px'; m.appendChild(d); };
  const it0 = (t, f) => { const b = document.createElement('div'); b.innerHTML = t; b.style.cssText = 'padding:6px 10px;border-radius:6px;cursor:pointer'; b.onmouseenter = () => b.style.background = '#2c313c'; b.onmouseleave = () => b.style.background = ''; b.onclick = () => { m.remove(); f(); }; m.appendChild(b); };
  it0('&#11015; Exporter cette piece (STL)', () => exporterPieces([h.nom]));
  if (F.sel.size) it0(`&#11015; Exporter la selection (${F.sel.size} piece${F.sel.size > 1 ? 's' : ''}, ZIP)`, () => exporterPieces([...F.sel]));
  it0(F.sel.has(h.nom) ? 'Retirer de la selection' : 'Ajouter a la selection (Ctrl+clic)', () => basculerSel(h.nom));
  it0('Tout selectionner', () => { groupe.children.forEach(x => { F.sel.add(x.userData.nom); surligner(x, true); }); infosSel(); });
  if (F.sel.size) it0('Vider la selection', viderSel);
  it0('Masquer cette piece', () => masquer([h.nom]));
  it0('Isoler cette piece', () => masquer(groupe.children.map(x => x.userData.nom).filter(n => n !== h.nom)));
  if (F.masques.size) it0(`Tout afficher (${F.masques.size} masquee${F.masques.size > 1 ? 's' : ''})`, toutAfficher);
  it0('&#11015; Exporter tout le projet (ZIP)', () => exporterPieces(groupe.children.map(x => x.userData.nom)));
  if (!F.info?.pinceau) { document.body.appendChild(m); setTimeout(() => document.addEventListener('pointerdown', ev => { if (!m.contains(ev.target)) m.remove(); }, { once: true }), 0); return; }
  sep();
  const it = (t, f) => { const b = document.createElement('div'); b.innerHTML = t; b.style.cssText = 'padding:6px 10px;border-radius:6px;cursor:pointer'; b.onmouseenter = () => b.style.background = '#2c313c'; b.onmouseleave = () => b.style.background = ''; b.onclick = () => { m.remove(); f(); }; m.appendChild(b); };
  if (ici) it(`<span style="color:#2ecc71">&#9679;</span> Ajouter une zone a <b>${ici}</b>`, () => demarrer('+', ici));
  if (ici) it(`<span style="color:#e74c3c">&#9679;</span> Rendre une zone a la caisse`, () => demarrer('-', ici));
  const s = document.createElement('div'); s.style.cssText = 'padding:6px 10px';
  s.innerHTML = `<span style="color:#2ecc71">&#9679;</span> Donner une zone a : <select style="margin-left:4px">${det.map(n => `<option>${n}</option>`).join('')}</select> <button>Peindre</button>`;
  s.querySelector('button').onclick = () => { m.remove(); demarrer('+', s.querySelector('select').value); };
  m.appendChild(s);
  it(`<span style="color:#3498db">&#9679;</span> Lisser la tole (poncage)`, () => demarrer('lisser', null));
  it(`<span style="color:#f39c12">&#9679;</span> Raboter : aplanir bosse / carre / creux`, () => demarrer('raboter', null));
  if (ici && F.params.retouches?.decoupe?.[ici]?.length) it(`Effacer les retouches de ${ici}`, () => { delete F.params.retouches.decoupe[ici]; regenerer(); });
  if (F.params.retouches?.surface?.length) it('Effacer les retouches de tole', () => { F.params.retouches.surface = []; regenerer(); });
  document.body.appendChild(m);
  setTimeout(() => document.addEventListener('pointerdown', ev => { if (!m.contains(ev.target)) m.remove(); }, { once: true }), 0);
});
function peindre(e) {
  const h = viser(e); if (!h) return;
  const der = PZ.trait[PZ.trait.length - 1];
  if (der && Math.hypot(der[0] - h.p.x, der[1] - h.p.y, der[2] - h.p.z) < PZ.r * 0.5) return;
  PZ.trait.push([+h.p.x.toFixed(2), +h.p.y.toFixed(2), +h.p.z.toFixed(2), +h.n.x.toFixed(3), +h.n.y.toFixed(3), +h.n.z.toFixed(3), PZ.r, PZ.mode]);
  marque(h);
}
ren.domElement.addEventListener('pointerdown', e => {
  if (!PZ.actif) return;
  if (e.button === 1) { orb.enabled = true; return; }      // clic milieu : tourner la vue
  if (e.button !== 0) return;
  PZ.peint = true; PZ.trait = []; peindre(e);
});
ren.domElement.addEventListener('pointermove', e => { if (PZ.actif && PZ.peint) peindre(e); });
window.addEventListener('pointerup', e => {
  if (PZ.actif && e.button === 1) orb.enabled = false;
  if (!PZ.peint) return;
  PZ.peint = false;
  if (!PZ.trait.length) return;
  liste().push(...PZ.trait);
  const R = F.params.retouches; R._hist = R._hist || [];
  R._hist.push({ cle: (PZ.mode === '+' || PZ.mode === '-') ? PZ.cible : 'surface', n: PZ.trait.length });
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && PZ.actif) quitterPinceau(); });

// ------------------------------------------------------------------ selection / masquage / export de pieces (tous les projets)
F.sel = new Set(); F.masques = new Set();
function surligner(mesh, on) { const m = mesh.material; if (!m?.emissive) return; m.emissive.set(on ? 0xff6a13 : 0x000000); m.emissiveIntensity = on ? 0.35 : 0; }
function infosSel() { const n = F.sel.size; const t = $('#cfg-etat'); if (!t) return; t.dataset.sel = n; if (n) toast(`${n} piece${n > 1 ? 's' : ''} selectionnee${n > 1 ? 's' : ''} - clic droit pour exporter`); }
function basculerSel(nom, seul = false) {
  if (seul) viderSel(false);
  F.sel.has(nom) ? F.sel.delete(nom) : F.sel.add(nom);
  groupe.children.forEach(x => surligner(x, F.sel.has(x.userData.nom)));
  infosSel();
}
function viderSel(msg = true) { F.sel.clear(); groupe.children.forEach(x => surligner(x, false)); }
function masquer(noms) { noms.forEach(n => F.masques.add(n)); groupe.children.forEach(x => x.visible = !F.masques.has(x.userData.nom)); }
function toutAfficher() { F.masques.clear(); groupe.children.forEach(x => x.visible = true); }
async function exporterPieces(noms) {
  const pieces = groupe.children.filter(x => noms.includes(x.userData.nom)).map(x => ({ fichier: x.userData.fichier, nom: x.userData.nom }));
  if (!pieces.length) return;
  const base = (F.projet?.nom || F.modele || 'projet').replace(/[^\w-]+/g, '_');
  const dl = (href, nom) => { const a = document.createElement('a'); a.href = href; a.download = nom; a.click(); };
  if (pieces.length === 1) return dl(`/c3d/${pieces[0].fichier}.stl`, `${base}_${pieces[0].nom}.stl`);
  const r = await fetch('/api/c3d/zip', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pieces, nom: base }) });
  if (!r.ok) return toast('Export impossible');
  dl(URL.createObjectURL(await r.blob()), `${base}_${pieces.length}_pieces.zip`);
  toast(`${pieces.length} pieces exportees (STL orientes pour l'impression)`);
}
function menuVide(e) {
  $('#pz-menu')?.remove();
  const m = document.createElement('div'); m.id = 'pz-menu';
  m.style.cssText = `position:fixed;left:${e.clientX}px;top:${e.clientY}px;z-index:50;background:#1c1f26;color:#eee;border-radius:10px;padding:6px;min-width:220px;box-shadow:0 8px 30px rgba(0,0,0,.4);font-size:13px`;
  const it = (t, f) => { const b = document.createElement('div'); b.innerHTML = t; b.style.cssText = 'padding:6px 10px;border-radius:6px;cursor:pointer'; b.onmouseenter = () => b.style.background = '#2c313c'; b.onmouseleave = () => b.style.background = ''; b.onclick = () => { m.remove(); f(); }; m.appendChild(b); };
  if (F.sel.size) it(`&#11015; Exporter la selection (${F.sel.size}, ZIP)`, () => exporterPieces([...F.sel]));
  it('&#11015; Exporter tout le projet (ZIP)', () => exporterPieces(groupe.children.map(x => x.userData.nom)));
  if (F.sel.size) it('Vider la selection', viderSel);
  if (F.masques.size) it('Tout afficher', toutAfficher);
  it('Recentrer la vue', cadrer);
  document.body.appendChild(m);
  setTimeout(() => document.addEventListener('pointerdown', ev => { if (!m.contains(ev.target)) m.remove(); }, { once: true }), 0);
}
// clic gauche (sans glisser) = selectionner ; Ctrl / Maj = selection multiple ; clic dans le vide = vider
let _down = null;
ren.domElement.addEventListener('pointerdown', e => { if (e.button === 0 && !PZ.actif) _down = [e.clientX, e.clientY]; });
ren.domElement.addEventListener('pointerup', e => {
  if (e.button !== 0 || PZ.actif || !_down) return;
  const bouge = Math.hypot(e.clientX - _down[0], e.clientY - _down[1]) > 4; _down = null;
  if (bouge) return;
  const h = viser(e);
  if (!h) return viderSel();
  basculerSel(h.nom, !(e.ctrlKey || e.shiftKey || e.metaKey));
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !PZ.actif && F.sel.size) viderSel(); });
