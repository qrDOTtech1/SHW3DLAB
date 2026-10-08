import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const api = async (u, body, method) => {
  const r = await fetch(u, body !== undefined ? { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { method: method || 'GET' });
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
};
const toast = m => { const t = $('#toast'); t.textContent = m; t.classList.add('on'); setTimeout(() => t.classList.remove('on'), 2600); };
const fmtT = s => s == null ? '-' : (s >= 3600 ? `${Math.floor(s / 3600)} h ${String(Math.round(s % 3600 / 60)).padStart(2, '0')}` : `${Math.round(s / 60)} min`);
const eur = v => (v == null ? '-' : v.toFixed(2).replace('.', ',') + ' EUR');

const S = { etat: null, police: 'arial_black', gen: null, vue: 'assemble', qualite: 'normal', tranches: {}, produit: 'porte_cle' };
$$('[data-prod]').forEach(b => b.onclick = () => {
  S.produit = b.dataset.prod; $$('[data-prod]').forEach(x => x.classList.toggle('on', x === b));
  renderCouleurs();
  const jet = S.produit === 'porte_jeton' || S.produit === 'porte_cle_jeton';
  $('#opt-jeton').hidden = !jet; $('#opt-jeton-pro').hidden = S.produit !== 'porte_jeton'; $('#opt-pcj').hidden = S.produit !== 'porte_cle_jeton'; $('#opt-ps').hidden = S.produit !== 'porte_serviette';
  $('#opt-cle').hidden = false;
  for (const id of ['hauteur', 'contour']) $('#' + id).closest('label').hidden = S.produit !== 'porte_cle';
  $('#btn-generer').textContent = { porte_jeton: 'Generer les porte-jetons', porte_cle_jeton: 'Generer les porte-cles a jeton', porte_serviette: 'Generer les porte-serviettes' }[S.produit] || 'Generer les porte-cles';
});

// ------------------------------------------------------------------ onglets
$$('#tabs button').forEach(b => b.onclick = () => {
  $$('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  $$('.tab').forEach(t => t.classList.toggle('on', t.id === 'tab-' + b.dataset.tab));
  if (b.dataset.tab === 'creer') resize();
});

// ------------------------------------------------------------------ viewer 3D
const V = {};
function initViewer() {
  const el = $('#viewer');
  V.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  V.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  V.renderer.shadowMap.enabled = true;
  el.appendChild(V.renderer.domElement);
  V.scene = new THREE.Scene();
  V.cam = new THREE.PerspectiveCamera(35, 1, 1, 5000);
  V.cam.position.set(0, -260, 220);
  V.ctl = new OrbitControls(V.cam, V.renderer.domElement);
  V.ctl.enableDamping = true;
  V.scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.4));
  const d = new THREE.DirectionalLight(0xffffff, 2.2);
  d.position.set(-120, -160, 300); d.castShadow = true; d.shadow.mapSize.set(2048, 2048);
  Object.assign(d.shadow.camera, { left: -200, right: 200, top: 200, bottom: -200 });
  V.scene.add(d);
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000), new THREE.ShadowMaterial({ opacity: 0.35 }));
  plane.receiveShadow = true; V.scene.add(plane);
  V.grid = new THREE.GridHelper(220, 22, 0x3a4250, 0x232934); V.grid.rotation.x = Math.PI / 2; V.grid.position.z = 0.01;
  V.scene.add(V.grid);
  V.group = new THREE.Group(); V.scene.add(V.group);
  V.loader = new STLLoader();
  resize(); window.addEventListener('resize', resize);
  (function loop() { requestAnimationFrame(loop); V.ctl.update(); V.renderer.render(V.scene, V.cam); })();
}
function resize() {
  const el = $('#viewer'); if (!V.renderer || !el.clientWidth) return;
  V.renderer.setSize(el.clientWidth, el.clientHeight); V.cam.aspect = el.clientWidth / el.clientHeight; V.cam.updateProjectionMatrix();
}
const loadSTL = url => new Promise((res, rej) => V.loader.load(url, res, undefined, rej));
function mat(color) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.02 });
}
async function afficher() {
  const g = S.gen; if (!g) return;
  V.group.clear();
  const pr = g.produit || 'porte_cle';
  const colB = colT({ porte_cle: 'base', porte_jeton: 'corps', porte_cle_jeton: 'corps', porte_serviette: 'plaque' }[pr]);
  const colP = colT('prenom');
  const base = `/fichier/${g.job}/`;
  const box = new THREE.Box3();
  if (S.vue === 'plateaux') {
    const geos = await Promise.all(g.plateaux.map(p => loadSTL(base + p.fichier)));
    geos.forEach((geo, k) => {
      const m = new THREE.Mesh(geo, mat(bobine(g.plateaux[k].bobine)?.couleur || '#888'));
      m.position.x = (k % 3) * 220; m.position.y = -Math.floor(k / 3) * 220; m.castShadow = true; V.group.add(m);
      const cadre = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(195, 195, 0.2)),
        new THREE.LineBasicMaterial({ color: 0x556070 }));
      cadre.position.set(m.position.x + 97.5, m.position.y + 97.5, 0); V.group.add(cadre);
    });
  } else {
    for (const pc of g.pieces) {
      const [b, p] = await Promise.all([loadSTL(base + pc.base), loadSTL(base + (pc.prenom || pc.base))]);
      const mb = new THREE.Mesh(b, mat(colB)), mp = new THREE.Mesh(p, mat(colP));
      if (S.gen.produit === 'porte_serviette') {
        const cr = new THREE.Mesh(await loadSTL(base + pc.crochets), mat(colT('crochets')));
        const dy = -g.pieces.indexOf(pc) * 80;
        for (const m of [mb, mp, cr]) m.position.y += dy;
        if (S.vue === 'eclate') { mp.position.z += 14; cr.position.z += 30; }
        for (const m of [mb, mp, cr]) { m.castShadow = true; V.group.add(m); }
        continue;
      }
      if (S.gen.produit === 'porte_jeton' || S.gen.produit === 'porte_cle_jeton') {
        const co = new THREE.Mesh(await loadSTL(base + pc.coulisseau), mat(colT('coulisseau')));
        const bo = new THREE.Mesh(await loadSTL(base + pc.bouton), mat(colT('bouton')));
        const parts = [mb, co, bo];
        if (pc.prenom) { mp.geometry = await loadSTL(base + pc.prenom); parts.push(mp); }
        const dy = -g.pieces.indexOf(pc) * 40;
        for (const m of parts) m.position.y += dy;
        if (S.vue === 'eclate') { co.position.z += 12; bo.position.z += 24; mp.position.z += 12; }
        const dx = 0;
        const jet = new THREE.Mesh(new THREE.CylinderGeometry(11.625, 11.625, 2.33, 64),
          new THREE.MeshStandardMaterial({ color: 0xc9a227, metalness: 0.7, roughness: 0.3 }));
        const rj = (g.rapport.jeton_mm[0]) / 2;
        jet.geometry = new THREE.CylinderGeometry(rj, rj, 2.33, 64);
        jet.rotation.x = Math.PI / 2; jet.position.set(dx + (S.vue === 'eclate' ? 38 : 0), dy, 2.52);
        if (pc.jeton) {      // jeton IMPRIME : on montre la vraie piece (et son motif)
          const pz = (pc.jeton_rep || {}).pause_z;
          const geo = await loadSTL(base + pc.jeton);
          const jm = new THREE.Mesh(geo, mat(colT('jeton')));
          const ex = S.vue === 'eclate' ? 38 : 0;
          jm.position.set(ex, dy, 0); parts.push(jm);
          if (pc.jeton_motif) { const mm = new THREE.Mesh(await loadSTL(base + pc.jeton_motif), mat(colT('jeton_motif'))); mm.position.set(ex, dy, S.vue === 'eclate' ? 6 : 0); parts.push(mm); }
          else if (pz) {   // pause : tout ce qui est au-dessus de pause_z sort dans la couleur du motif
            jm.material = new THREE.MeshStandardMaterial({ color: colT('jeton'), roughness: 0.55 });
            const haut = new THREE.Mesh(geo, mat(colT('jeton_motif')));
            haut.position.copy(jm.position); haut.position.z += 0.001;
            const zc = 1.2 + 0.16 + pz;
            haut.material.clippingPlanes = [new THREE.Plane(new THREE.Vector3(0, 0, 1), -zc)];
            jm.material.clippingPlanes = [new THREE.Plane(new THREE.Vector3(0, 0, -1), zc)];
            V.renderer.localClippingEnabled = true; parts.push(haut);
          }
          for (const m of parts) { m.castShadow = true; V.group.add(m); }
          continue;
        }
        for (const m of [...parts, jet]) { m.castShadow = true; V.group.add(m); }
        continue;
      }
      if (S.vue === 'assemble') mp.position.z = 3.0 - 1.2;   // prenom pose au fond de l'empreinte
      else mp.position.z = 12;
      for (const m of [mb, mp]) { m.castShadow = true; V.group.add(m); }
    }
  }
  box.setFromObject(V.group);
  const c = box.getCenter(new THREE.Vector3()), sz = box.getSize(new THREE.Vector3());
  V.group.position.set(-c.x, -c.y, 0);
  // cadrage : distance telle que toute la scene tienne dans le champ (horizontal ET vertical)
  const fov = THREE.MathUtils.degToRad(V.cam.fov);
  const hfov = 2 * Math.atan(Math.tan(fov / 2) * V.cam.aspect);
  const dist = Math.max(sz.y / 2 / Math.tan(fov / 2), sz.x / 2 / Math.tan(hfov / 2)) * 1.35 + sz.z;
  const el = THREE.MathUtils.degToRad(48);
  V.cam.position.set(0, -dist * Math.cos(el), dist * Math.sin(el)); V.ctl.target.set(0, 0, 0); V.ctl.update();
  $('#stage-empty').hidden = true;
}
$$('.stage-tools button').forEach(b => b.onclick = () => {
  $$('.stage-tools button').forEach(x => x.classList.toggle('on', x === b)); S.vue = b.dataset.vue; afficher();
});



// ------------------------------------------------------------------ jeton imprime (initiale / QR / logo)
S.jm = { image: '' };
function jmParams() {
  const m = $('#jm-motif').value, s = +$('#jm-seuil').value;
  return { jeton_motif: m, jeton_texte: $('#jm-texte').value.trim(), jeton_mode: $('#jm-mode').value,
    jeton_image: S.jm.image, jeton_seuil: s ? s : null, jeton_inverser: $('#jm-inv').checked ? true : null };
}
let _tJm = null;
async function jmApercu() {
  const p = jmParams(), m = p.jeton_motif;
  $('#jm-texte-l').hidden = !(m === 'initiale' || m === 'qr'); $('#jm-logo').hidden = m !== 'logo';
  $('#jm-apercu-box').hidden = m === 'aucun' || (m === 'logo' && !S.jm.image);
  if ($('#jm-apercu-box').hidden) return;
  const premier = nomsSaisis()[0] || 'S';
  const q = new URLSearchParams({ motif: m, texte: p.jeton_texte || (m === 'qr' ? 'https://monsite.fr' : premier[0]),
    police: S.polNom[premier] || S.police, image: S.jm.image, d: $('#jeton-d').value, mode: p.jeton_mode });
  if (p.jeton_seuil) q.set('seuil', p.jeton_seuil); if (p.jeton_inverser) q.set('inverser', true);
  const r = await fetch('/api/apercu_motif?' + q);
  if (!r.ok) { $('#jm-info').textContent = (await r.json()).detail; return; }
  $('#jm-apercu').src = URL.createObjectURL(await r.blob());
  const rep = JSON.parse(r.headers.get('X-Rapport') || '{}');
  $('#jm-info').innerHTML = [rep.mode === 'pause' ? '1 impression, pause a ' + rep.pause_z + ' mm' : '2 impressions, motif affleurant',
    rep.mode_force ? '<span class="badge warn">' + rep.mode_force + '</span>' : '',
    rep.qr_modules ? `QR ${rep.qr_modules}x${rep.qr_modules}, module ${rep.qr_module_mm} mm <span class="badge ${rep.qr_lisible ? 'ok' : 'bad'}">${rep.qr_lisible ? 'lisible' : 'trop fin'}</span> ${rep.qr_conseil || ''}` : '',
    rep.logo ? `logo : ${rep.logo.morceaux} morceau(x), seuil ${rep.logo.seuil}${rep.logo.inverse ? ', inverse' : ''}` : ''].filter(Boolean).join('<br>');
}
const jmMaj = () => { clearTimeout(_tJm); _tJm = setTimeout(jmApercu, 350); };
for (const id of ['#jm-motif', '#jm-mode', '#jm-texte', '#jm-inv', '#jeton-d']) $(id).addEventListener('input', jmMaj);
$('#jm-seuil').addEventListener('input', e => { $('#v-jm-seuil').textContent = +e.target.value || 'auto'; jmMaj(); });
$('#jm-fichier').onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  const data = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(f); });
  try { S.jm.image = (await api('/api/image', { data })).id; toast('Image chargee'); jmApercu(); } catch (er) { toast(er.message); }
};

// ------------------------------------------------------------------ couleur par element
const ELEMENTS = { porte_cle: [['base', 'Base'], ['prenom', 'Prenom']],
  porte_cle_jeton: [['corps', 'Corps'], ['coulisseau', 'Coulisseau'], ['bouton', 'Bouton poussoir'], ['prenom', 'Prenom'], ['jeton', 'Jeton'], ['jeton_motif', 'Motif du jeton']],
  porte_jeton: [['corps', 'Corps'], ['coulisseau', 'Coulisseau'], ['bouton', 'Bouton poussoir'], ['prenom', 'Prenom'], ['jeton', 'Jeton'], ['jeton_motif', 'Motif du jeton']],
  porte_serviette: [['plaque', 'Plaque'], ['crochets', 'Crochets'], ['prenom', 'Prenom']] };
S.couleurs = {}; S.coulProd = {};
const colT = t => bobine(S.couleurs[t])?.couleur || '#888';
function defautCouleurs() {
  const bs = S.etat?.bobines || []; if (!bs.length) return;
  const blanc = (bs.find(b => /blanc|white/i.test(b.nom)) || bs[0]).id, noir = (bs.find(b => /noir|black/i.test(b.nom)) || bs[bs.length - 1]).id;
  for (const [p, els] of Object.entries(ELEMENTS)) els.forEach(([t], k) => {
    const key = p + ':' + t; if (!bobine(S.coulProd?.[key])) (S.coulProd ||= {})[key] = t === 'prenom' ? noir : blanc; });
}
function syncCouleurs() {   // couleurs du produit courant -> S.couleurs (type -> bobine)
  S.couleurs = {}; for (const [t] of ELEMENTS[S.produit] || []) S.couleurs[t] = S.coulProd?.[S.produit + ':' + t];
}
function renderCouleurs() {
  if (!S.etat) return; defautCouleurs(); syncCouleurs();
  const bs = S.etat.bobines;
  $('#couleurs').innerHTML = (ELEMENTS[S.produit] || []).map(([t, lab]) => `<div class="ligne coul">
    <span><i class="pastille" style="background:${colT(t)}"></i>${lab}</span>
    <select data-coul="${t}">${bs.map(b => `<option value="${b.id}" ${b.id === S.couleurs[t] ? 'selected' : ''}>${b.nom} (${Math.round(b.restant_g)} g)</option>`).join('')}</select></div>`).join('');
  $$('[data-coul]').forEach(sel => sel.onchange = async () => {
    S.coulProd[S.produit + ':' + sel.dataset.coul] = sel.value; renderCouleurs();
    if (S.gen && S.gen.produit === S.produit) {
      const r = await api('/api/plateaux', { job: S.gen.job, couleurs: S.couleurs });
      S.gen.plateaux = r.plateaux; S.gen.couleurs = { ...S.couleurs }; S.tranches = {};
      renderResultats(); renderPlateauxImp();
    }
    afficher();
  });
}

// ------------------------------------------------------------------ etat / filaments
const bobine = id => S.etat?.bobines.find(b => b.id === id);
async function chargerEtat() {
  S.etat = await api('/api/etat');
  const opts = S.etat.bobines.map(b => `<option value="${b.id}">${b.nom} (${Math.round(b.restant_g)} g)</option>`).join('');
  renderCouleurs();
  renderKPIs(); renderBobines(); renderHisto(); renderCoutsForm();
  $('#imp-ip').textContent = S.etat.imprimante.adresse;
}
function renderKPIs() {
  const bs = S.etat.bobines, tot = bs.reduce((a, b) => a + b.restant_g, 0);
  const val = bs.reduce((a, b) => a + b.restant_g / 1000 * b.prix_kg, 0);
  const bas = bs.filter(b => b.restant_g < 150);
  $('#kpis').innerHTML = `<div class="kpi"><span>Stock filament</span><b>${Math.round(tot)} g</b></div>
    <div class="kpi"><span>Valeur stock</span><b>${eur(val)}</b></div>
    <div class="kpi ${bas.length ? 'alerte' : ''}"><span>Bobines basses</span><b>${bas.length ? bas.map(b => b.nom).join(', ') : 'aucune'}</b></div>`;
}
function renderBobines() {
  $('#bobines').innerHTML = S.etat.bobines.map(b => {
    const pct = Math.max(0, Math.min(100, 100 * b.restant_g / b.initial_g));
    const col = pct < 15 ? 'var(--bad)' : pct < 35 ? 'var(--warn)' : b.couleur;
    return `<div class="bob"><div class="ring" style="background:conic-gradient(${col} ${pct}%, #262c36 0)"><div>${Math.round(b.restant_g)} g</div></div>
      <div style="flex:1"><h3><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:${b.couleur};border:1px solid #555;margin-right:6px"></span>${b.nom}</h3>
      <div class="mute">${b.marque} &middot; ${b.matiere} &middot; ${b.prix_kg} EUR/kg &middot; ${b.temp[0]} / ${b.temp[1]} C</div>
      <div class="mute">${pct.toFixed(0)} % restant &middot; valeur ${eur(b.restant_g / 1000 * b.prix_kg)}</div>
      <div class="acts"><button data-edit="${b.id}">Modifier</button><button data-conso="${b.id}">- Consommer</button></div></div></div>`;
  }).join('');
  $$('[data-edit]').forEach(x => x.onclick = () => editBobine(bobine(x.dataset.edit)));
  $$('[data-conso]').forEach(x => x.onclick = async () => {
    const g = parseFloat(prompt('Grammes consommes ?', '10')); if (!g) return;
    S.etat = await api('/api/consommer', { bobine: x.dataset.conso, grammes: g, libelle: 'manuel' }); chargerEtat();
  });
}
async function editBobine(b) {
  b = b || { nom: 'Nouvelle bobine', marque: '', matiere: 'PLA', couleur: '#888888', restant_g: 1000, initial_g: 1000, prix_kg: 20, temp: [220, 60] };
  const f = {};
  for (const [k, lab] of [['nom', 'Nom'], ['marque', 'Marque'], ['matiere', 'Matiere (PLA, PLA+, PETG, TPU)'], ['couleur', 'Couleur (#rrggbb)'],
    ['restant_g', 'Restant (g)'], ['initial_g', 'Poids initial (g)'], ['prix_kg', 'Prix (EUR/kg)']]) {
    const v = prompt(lab, b[k]); if (v === null) return; f[k] = ['restant_g', 'initial_g', 'prix_kg'].includes(k) ? parseFloat(v) : v;
  }
  await api('/api/bobines', { ...b, ...f }); toast('Bobine enregistree'); chargerEtat();
}
$('#btn-add-bob').onclick = () => editBobine(null);
function renderHisto() {
  const h = S.etat.historique.slice(-30).reverse();
  $('#histo').innerHTML = '<tr><th>Date</th><th>Bobine</th><th>Grammes</th><th>Impression</th></tr>' +
    (h.length ? h.map(x => `<tr><td>${x.t}</td><td>${x.bobine}</td><td>${x.g} g</td><td>${x.libelle}</td></tr>`).join('') : '<tr><td colspan=4 class="mute">Rien encore.</td></tr>');
}

// ------------------------------------------------------------------ creer
async function initPolices() {
  S.polices = await api('/api/polices');
  renderPolices();
}
function renderPolices() {
  const t = encodeURIComponent(($('#noms').value.split(String.fromCharCode(10)).map(x => x.trim()).find(Boolean)) || 'Steven');
  $('#polices').innerHTML = Object.entries(S.polices).map(([k, p]) =>
    `<button data-pol="${k}" class="pol ${k === S.police ? 'on' : ''}" title="${p.label} - ${p.licence}">
       <img src="/api/apercu_police/${k}?texte=${t}" alt="${p.label}">
       <span>${p.label}${p.vente_perso ? '' : ' <em class="lic">licence perso</em>'}</span></button>`).join('');
  renderLignes();
  $$('[data-pol]').forEach(b => b.onclick = () => {
    const ancienne = S.police;
    S.police = b.dataset.pol; $$('[data-pol]').forEach(x => x.classList.toggle('on', x === b));
    // les lignes qui suivaient la police par defaut la suivent encore
    for (const k of Object.keys(S.polNom)) if (S.polNom[k] === ancienne) delete S.polNom[k];
    renderLignes();
    const p = S.polices[S.police];
    if (!p.vente_perso) toast(p.label + ' : ' + p.licence);
  });
}
let _tPol = null;
$('#noms').addEventListener('input', () => { clearTimeout(_tPol); _tPol = setTimeout(renderPolices, 500); });
S.polNom = {};
const nomsSaisis = () => $('#noms').value.split(String.fromCharCode(10)).map(s => s.trim()).filter(Boolean);
function renderLignes() {
  if (!S.polices) return;
  const opts = k => Object.entries(S.polices).map(([key, p]) => `<option value="${key}" ${key === k ? 'selected' : ''}>${p.label}${p.vente_perso ? '' : ' (licence perso)'}</option>`).join('');
  $('#lignes').innerHTML = nomsSaisis().map((n, i) => {
    const k = S.polNom[n] || S.police;
    return `<div class="ligne"><img src="/api/apercu_police/${k}?texte=${encodeURIComponent(n)}" alt="${n}">
      <select data-ligne="${encodeURIComponent(n)}">${opts(k)}</select></div>`;
  }).join('');
  $$('[data-ligne]').forEach(sel => sel.onchange = () => {
    const n = decodeURIComponent(sel.dataset.ligne);
    if (sel.value === S.police) delete S.polNom[n]; else S.polNom[n] = sel.value;
    sel.previousElementSibling.src = `/api/apercu_police/${sel.value}?texte=${encodeURIComponent(n)}`;
    const p = S.polices[sel.value]; if (!p.vente_perso) toast(p.label + ' : ' + p.licence);
  });
}
$('#crochets').oninput = e => $('#v-croch').textContent = e.target.value;
for (const id of ['hauteur', 'contour', 'jeu']) $('#' + id).oninput = e => $('#v-' + id).textContent = e.target.value;


async function suivre(jid, prog, onDone) {
  const el = $(prog); el.hidden = false;
  for (;;) {
    const j = await api('/api/job/' + jid);
    el.querySelector('div').style.width = (100 * j.progres) + '%';
    el.querySelector('span').textContent = j.etat === 'en attente' ? 'En file d attente (un calcul a la fois)...' : j.etat === 'en cours' ? `${j.log.at(-1) || 'Demarrage'} (${j.duree_s} s)` : j.etat === 'termine' ? `Termine en ${j.duree_s} s` : 'Erreur';
    if (j.etat === 'termine') { onDone(j.resultat); return; }
    if (j.etat === 'erreur') { toast('Erreur : ' + j.log.at(-1)); return; }
    await new Promise(r => setTimeout(r, 600));
  }
}
$('#btn-generer').onclick = async () => {
  const noms = $('#noms').value.split('\n').map(s => s.trim()).filter(Boolean);
  if (S.produit === 'porte_cle' && !noms.length) return toast('Ajoute au moins un prenom');
  if (S.produit === 'porte_serviette' && !noms.length) return toast('Ajoute au moins un prenom');
  $('#btn-generer').disabled = true;
  try {
    const { job } = await api('/api/generer', { produit: S.produit, quantite: +$('#qte-jeton').value, noms: noms.length ? noms : ['x'], polices: noms.map(n => S.polNom[n] || S.police), crochets: +$('#crochets').value, couleurs: S.couleurs, ...jmParams(), jeton_d: +$('#jeton-d').value, police: S.police, hauteur: +$('#hauteur').value, contour: +$('#contour').value, jeu: +$('#jeu').value, mode: $('#mode').value });
    await suivre(job, '#gen-prog', async res => { S.gen = res; S.tranches = {}; for (const [t, b] of Object.entries(res.couleurs || {})) S.coulProd[res.produit + ':' + t] = b; renderCouleurs(); renderResultats(); await afficher(); renderPlateauxImp(); toast(`${res.pieces.length} porte-cles generes`); });
  } catch (e) { toast(e.message); }
  $('#btn-generer').disabled = false;
};
function renderResultats() {
  const g = S.gen;
  if (g.produit === 'porte_jeton' || g.produit === 'porte_cle_jeton') { renderJeton(g); return; }
  const ok = g.pieces.filter(p => p.controles.ok).length;
  $('#resultats').innerHTML = `<h2>Controles</h2>
    <p><span class="badge ${ok === g.pieces.length ? 'ok' : 'bad'}">${ok}/${g.pieces.length} conformes</span>
    <span class="badge ${g.tient ? 'ok' : 'bad'}">${g.plateaux.length} plateau(x)</span></p>` +
    g.pieces.map(p => {
      const c = p.controles;
      return `<div class="piece"><div class="t">${p.nom} <span class="badge">${(S.polices[p.police] || {}).label || ''}</span><span class="badge ${c.ok ? 'ok' : 'bad'}">${c.ok ? 'OK' : 'A revoir'}</span></div>
      <div class="d">${c.dimensions_mm[0]} x ${c.dimensions_mm[1]} mm &middot; prenom ${c.prenom_monobloc ? 'monobloc' : c.pieces_prenom + ' pieces'}
      ${c.details_a_placer ? `&middot; <span class="badge warn">${c.details_a_placer} detail(s) a placer</span>` : ''}
      ${c.entraxe_vis_mm ? `<br>Percage : 2 vis a <b>${c.entraxe_vis_mm} mm</b> d'entraxe &middot; crochets x${c.crochets} (coef ${c.crochet_coef}) &middot; serrures coef ${c.serrure_coef}` : ''}
      &middot; anneau ${c.mur_anneau_mm} mm</div></div>`;
    }).join('') +
    dlPlateaux(g);
}


function renderJeton(g) {
  const r = g.rapport, sim = g.simulation, mx = Math.max(...sim.map(x => x[1]));
  const pts = sim.map(([c, v]) => (10 + c * 20) + ',' + (80 - 70 * v / mx)).join(' ');
  const xf = 10 + r.course_ejecteur_mm * 20;
  $('#resultats').innerHTML = '<h2>Controles porte-jeton</h2>'
    + '<p><span class="badge ' + (r.ok ? 'ok' : 'bad') + '">' + (r.ok ? 'conforme' : 'a revoir') + '</span> '
    + '<span class="badge">' + r.dimensions_mm.join(' x ') + ' mm</span></p>'
    + '<div class="piece"><div class="d">Jeton d ' + r.jeton_mm[0] + ' &middot; alesage ' + r.alesage_mm
    + ' &middot; cavite ' + r.cavite_h_mm + ' mm<br>Cran de repos 0.3 mm + bosses 0.6 mm &middot; doigts flexibles '
    + r.doigts_flexibles_mm + ' mm<br>Course du poussoir ' + r.course_ejecteur_mm + ' mm &rarr; <b>jeton sorti de '
    + r.sortie_jeton_mm + ' mm</b></div></div>'
    + '<h2>Simulation de la course</h2><p class="mute">Resistance au deplacement du jeton (0 = libre). Creux = positions stables.</p>'
    + '<svg viewBox="0 0 260 90" style="width:100%;background:var(--bg2);border-radius:8px">'
    + '<polyline fill="none" stroke="#ff7a2f" stroke-width="2" points="' + pts + '"/>'
    + '<line x1="' + xf + '" y1="5" x2="' + xf + '" y2="85" stroke="#3ddc97" stroke-dasharray="3 3"/>'
    + '<text x="12" y="88" fill="#8a93a3" font-size="8">repos</text>'
    + '<text x="' + (xf + 4) + '" y="12" fill="#3ddc97" font-size="8">fin de course</text></svg>'
    + dlPlateaux(g);
}

// ------------------------------------------------------------------ imprimer
async function initQualites() {
  const q = await api('/api/qualites');
  $('#qualites').innerHTML = Object.entries(q).map(([k, v]) => `<div class="qcard ${k === S.qualite ? 'on' : ''}" data-q="${k}">
     <h3>${v.label}</h3><div class="lh">couches ${v.couche_mm} mm</div><p>${v.desc}</p></div>`).join('');
  $$('[data-q]').forEach(c => c.onclick = () => { S.qualite = c.dataset.q; $$('[data-q]').forEach(x => x.classList.toggle('on', x === c)); });
}
const labT = t => (ELEMENTS[S.gen?.produit] || []).find(e => e[0] === t)?.[1] || S.gen?.elements?.find(e => e.type === t)?.label || t;
function dlPlateaux(g) {
  return '<div class="dl">' + g.plateaux.map(p => `<a href="/fichier/${g.job}/${p.fichier}" download>Plateau ${p.id} - ${bobine(p.bobine)?.nom || p.bobine} (STL)</a>`).join('') + '</div>';
}
function renderPlateauxImp() {
  if (!S.gen) return;
  $('#plateaux-imp').innerHTML = S.gen.plateaux.map(p => {
    const k = p.id, t = S.tranches[k], b = bobine(p.bobine);
    const lab = `<i class="pastille" style="background:${b?.couleur || '#888'}"></i>Plateau ${k} : ${p.types.map(labT).join(' + ')}`;
    return `<div class="plateau"><div class="row-head"><b>${lab}</b><span class="badge">${p.nb} elements &middot; ${b ? b.nom : p.bobine}</span>${p.tient ? '' : '<span class="badge bad">deborde</span>'}</div>
      ${t ? `<div class="stats"><div class="stat"><span>Temps</span><b>${fmtT(t.temps_s)}</b></div><div class="stat"><span>Filament</span><b>${t.filament_g} g</b></div>
        <div class="stat"><span>Cout</span><b>${eur(t.cout.total)}</b></div><div class="stat"><span>Qualite</span><b>${t.qualite}</b></div></div>
        ${t.stock_suffisant ? '' : '<p class="badge bad">Stock insuffisant sur cette bobine</p>'}
        <div class="dl"><a href="/fichier/${S.gen.job}/${t.gcode}" download>Telecharger le G-code</a>
        <button data-fini="${k}">Imprime : deduire ${t.filament_g} g du stock</button></div>`
        : `<p class="mute">Pas encore tranche.</p>`}
      <button class="primary" data-tr="${k}" style="margin-top:8px">Trancher (${S.qualite})</button>
      <div class="progress" id="prog-${k}" hidden><div></div><span></span></div></div>`;
  }).join('');
  $$('[data-tr]').forEach(b => b.onclick = async () => {
    const k = b.dataset.tr; b.disabled = true;
    const bob = S.gen.plateaux.find(p => p.id === k).bobine;
    const { job } = await api('/api/trancher', { job: S.gen.job, plateau: k, qualite: S.qualite, bobine: bob });
    await suivre(job, '#prog-' + k, res => { S.tranches[k] = res; renderPlateauxImp(); majCoutPiece(); toast(`Tranche : ${fmtT(res.temps_s)}, ${res.filament_g} g`); });
  });
  $$('[data-fini]').forEach(b => b.onclick = async () => {
    const k = b.dataset.fini, t = S.tranches[k];
    if (!confirm(`Confirmer : l'impression "${k}" est terminee ? ${t.filament_g} g seront deduits.`)) return;
    await api('/api/consommer', { bobine: t.bobine, grammes: t.filament_g, libelle: `${k} x${S.gen.pieces.length} (${t.qualite})` });
    toast('Stock mis a jour'); chargerEtat();
  });
}
function majCoutPiece() {
  const t = Object.values(S.tranches); if (!t.length || !S.gen) return;
  const tot = t.reduce((a, x) => a + x.cout.total, 0) / S.gen.pieces.length;
  $('#p-cout').value = tot.toFixed(3);
  $('#p-cout-src').textContent = `Cout reel par piece : ${t.map(x => x.gcode).join(' + ')} / ${S.gen.pieces.length} pieces` + (t.length < S.gen.plateaux.length ? ' (tranche tous les plateaux pour le total)' : '');
}

// ------------------------------------------------------------------ couts & prix
const COUT_LAB = { electricite_kwh: 'Electricite (EUR/kWh)', puissance_w: 'Conso imprimante (W)', machine_prix: 'Prix machine (EUR)',
  machine_vie_h: 'Duree de vie (h)', buse_eur_h: 'Usure buse/plateau (EUR/h)', emballage: 'Emballage (EUR)', anneau: 'Anneau (EUR)', colle: 'Colle (EUR)',
  etsy_annonce: 'Etsy : annonce (EUR)', etsy_transaction_pct: 'Etsy : transaction (%)', etsy_paiement_pct: 'Etsy : paiement (%)',
  etsy_paiement_fixe: 'Etsy : paiement fixe (EUR)', main_oeuvre_h: 'Ta main d\'oeuvre (EUR/h)', temps_assemblage_min: 'Assemblage (min/piece)', marge_cible_pct: 'Marge nette visee (%)' };
function renderCoutsForm() {
  const c = S.etat.couts;
  $('#couts-form').innerHTML = Object.entries(COUT_LAB).map(([k, l]) => `<label>${l}<input type="number" step="any" data-cout="${k}" value="${c[k]}"></label>`).join('');
}
$('#btn-couts').onclick = async () => {
  const c = {}; $$('[data-cout]').forEach(i => c[i.dataset.cout] = parseFloat(i.value));
  await api('/api/couts', { couts: c }); toast('Parametres enregistres'); chargerEtat();
};
$('#btn-prix').onclick = async () => {
  const pv = $('#p-prix').value;
  const r = await api('/api/prix', { cout_impression_piece: +$('#p-cout').value, prix_vente: pv ? +pv : null, quantite: +$('#p-qte').value });
  const [lo, hi] = r.marche_etsy, mx = hi * 1.4;
  $('#prix-res').innerHTML = `<div class="prix-big">
      <div class="stat"><span>Prix de vente</span><b>${eur(r.prix_vente)}</b></div>
      <div class="stat net"><span>Net par piece</span><b>${eur(r.net_piece)}</b></div>
      <div class="stat"><span>Marge nette</span><b>${r.marge_pct} %</b></div>
      <div class="stat"><span>Cout de revient</span><b>${eur(r.cout_revient)}</b></div>
      <div class="stat"><span>Frais Etsy</span><b>${eur(r.frais_etsy)}</b></div>
      <div class="stat net"><span>Net x ${$('#p-qte').value}</span><b>${eur(r.net_total)}</b></div></div>
    <div class="barre"><div class="zone" style="left:${100 * lo / mx}%;width:${100 * (hi - lo) / mx}%"></div><i style="left:${Math.min(99, 100 * r.prix_vente / mx)}%"></i></div>
    <div class="mute">Marche Etsy observe : ${eur(lo)} - ${eur(hi)} &rarr; ton prix est <b>${r.position_marche}</b>. Prix conseille pour ${S.etat.couts.marge_cible_pct} % net : <b>${eur(r.prix_conseille)}</b>.</div>
    <table class="tbl" style="margin-top:10px"><tr><th>Poste</th><th>Montant</th></tr>${Object.entries(r.detail).map(([k, v]) => `<tr><td>${k.replace('_', ' ')}</td><td>${eur(v)}</td></tr>`).join('')}</table>`;
};

// ------------------------------------------------------------------ demarrage
// ------------------------------------------------------------------ theme clair / sombre
function appliquerTheme(t) {      // n'eclaire QUE les scenes 3D (l'interface reste sombre)
  document.documentElement.dataset.scene = t; $('#theme-btn').innerHTML = t === 'light' ? '&#9790;' : '&#9728;';
  $('#theme-btn').title = t === 'light' ? 'Scene 3D sombre' : 'Scene 3D claire';
  try { localStorage.setItem('scene', t); } catch { }
  window.dispatchEvent(new CustomEvent('theme', { detail: t }));
}
$('#theme-btn').onclick = () => appliquerTheme(document.documentElement.dataset.scene === 'light' ? 'dark' : 'light');
window.ATELIER = { S, api, toast, bobine, suivre, renderPlateauxImp, majCoutPiece, chargerEtat };
window.__V = V; initViewer(); appliquerTheme((() => { try { return localStorage.getItem('scene') || 'dark'; } catch { return 'dark'; } })()); initPolices(); initQualites(); chargerEtat();
