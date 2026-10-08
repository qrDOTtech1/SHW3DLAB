// EFFETS DE SURFACE : motifs procéduraux calculés dans le navigateur (aperçu en direct = résultat final).
// Chaque motif f(u, v) renvoie une hauteur dans [0, 1] ; (u, v) sont en "cellules" (déjà divisés par la taille).

const fract = x => x - Math.floor(x);
const clamp01 = x => x < 0 ? 0 : x > 1 ? 1 : x;
const lisse = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const tri = x => 1 - Math.abs(fract(x) * 2 - 1);                 // onde triangle 0..1
function hash2(x, y) { const h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return h - Math.floor(h); }
function bruit(x, y) {                                          // value noise lissé
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash2(xi, yi), b = hash2(xi + 1, yi), c = hash2(xi, yi + 1), d = hash2(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
const fbm = (x, y, o = 4) => { let s = 0, a = 0.5, f = 1; for (let i = 0; i < o; i++) { s += a * bruit(x * f, y * f); f *= 2.03; a *= 0.5; } return s / (1 - Math.pow(0.5, o)); };
function voronoi(x, y, alea) {                                   // -> [F1, F2, id]
  const xi = Math.floor(x), yi = Math.floor(y); let f1 = 9, f2 = 9, id = 0;
  for (let j = -1; j <= 1; j++) for (let i = -1; i <= 1; i++) {
    const cx = xi + i, cy = yi + j;
    const px = cx + 0.5 + (hash2(cx, cy) - 0.5) * alea, py = cy + 0.5 + (hash2(cy + 17.3, cx - 4.1) - 0.5) * alea;
    const d = Math.hypot(x - px, y - py);
    if (d < f1) { f2 = f1; f1 = d; id = hash2(cx * 1.7, cy * 3.1); } else if (d < f2) f2 = d;
  }
  return [f1, f2, id];
}
function hexa(x, y) {                                            // -> [distance hex au centre (0..0.5 au bord), id]
  const sx = 1, sy = 1.7320508;
  const ax = ((x % sx) + sx) % sx - sx / 2, ay = ((y % sy) + sy) % sy - sy / 2;
  const bx = (((x - sx / 2) % sx) + sx) % sx - sx / 2, by = (((y - sy / 2) % sy) + sy) % sy - sy / 2;
  const g = ax * ax + ay * ay < bx * bx + by * by ? [ax, ay] : [bx, by];
  const gx = Math.abs(g[0]), gy = Math.abs(g[1]);
  return Math.max(gx * 0.5 + gy * 0.8660254, gx);               // 0 au centre, 0.5 sur l'arete
}

// p = { trait (0.02..0.45), nettete, alea } ; renvoie 0..1 (1 = relief max)
export const MOTIFS = {
  alveoles: { nom: 'Nid d\'abeille (alvéoles)', f: (u, v, p) => lisse(0.5 - p.trait - p.flou, 0.5 - p.trait + p.flou, hexa(u, v)) },
  hexa_bombe: { nom: 'Hexagones bombés', f: (u, v, p) => Math.pow(clamp01(1 - hexa(u, v) * 2), 0.6) },
  gaufre: { nom: 'Gaufre (grille carrée)', f: (u, v, p) => { const g = Math.max(Math.abs(fract(u) - 0.5), Math.abs(fract(v) - 0.5)); return lisse(0.5 - p.trait - p.flou, 0.5 - p.trait + p.flou, g); } },
  triangles: { nom: 'Triangles (géodésique)', f: (u, v, p) => {
    const d = [u, u * 0.5 + v * 0.8660254, -u * 0.5 + v * 0.8660254].map(t => Math.abs(fract(t) - 0.5));
    return 1 - lisse(p.trait - p.flou, p.trait + p.flou, 0.5 - Math.max(...d)); } },
  voronoi: { nom: 'Cellules organiques', f: (u, v, p) => { const [a, b] = voronoi(u, v, p.alea); return 1 - lisse(p.trait * 0.6 - p.flou, p.trait * 0.6 + p.flou, b - a); } },
  pierre: { nom: 'Pierres bombées', f: (u, v, p) => { const [a, b] = voronoi(u, v, p.alea); return Math.pow(clamp01((b - a) * 2.2), 0.55); } },
  mosaique: { nom: 'Mosaïque / facettes', f: (u, v, p) => { const [a, b, id] = voronoi(u, v, p.alea); return (0.35 + 0.65 * id) * lisse(0, p.trait + p.flou, b - a); } },
  ecailles: { nom: 'Écailles', f: (u, v, p) => {
    // écailles de poisson : rangées espacées d'une demi-écaille, décalées ; la rangée du dessus recouvre
    const H = 0.5, R = 0.62, r = Math.floor(v / H);
    for (let rr = r + 2; rr >= r - 1; rr--) {
      const cy = rr * H; if (v > cy) continue;
      const off = (((rr % 2) + 2) % 2) * 0.5, cx = Math.floor(u + off) + 0.5 - off;
      for (const c of [cx - 1, cx, cx + 1]) {
        const d = Math.hypot(u - c, v - cy);
        if (d < R) { const t = d / R; return Math.sqrt(1 - t * t) * 0.6 + 0.4 * (1 - (cy - v) / R); }
      }
    }
    return 0; } },
  briques: { nom: 'Briques', f: (u, v, p) => {
    const r = Math.floor(v * 2), x = fract(u + (r % 2) * 0.5), y = fract(v * 2);
    const g = Math.min(Math.min(x, 1 - x) * 2, Math.min(y, 1 - y)); return lisse(p.trait * 0.5 - p.flou, p.trait * 0.5 + p.flou, g); } },
  diamant: { nom: 'Moletage diamant', f: (u, v, p) => Math.pow(1 - Math.max(Math.abs(fract(u + v) - 0.5), Math.abs(fract(u - v) - 0.5)) * 2, p.nettete) },
  rainures: { nom: 'Rainures droites', f: (u, v, p) => Math.pow(tri(u), p.nettete) },
  cannelures: { nom: 'Cannelures arrondies', f: (u) => { const x = fract(u) * 2 - 1; return Math.sqrt(Math.max(0, 1 - x * x)); } },
  vagues: { nom: 'Vagues', f: (u, v, p) => 0.5 + 0.5 * Math.sin(2 * Math.PI * (u + 0.35 * Math.sin(2 * Math.PI * v * 0.5))) },
  chevrons: { nom: 'Chevrons', f: (u, v, p) => Math.pow(tri(u + Math.abs(fract(v) - 0.5) * 1.5), p.nettete) },
  tressage: { nom: 'Tressage (vannerie)', f: (u, v) => {
    const cu = Math.floor(u * 2), cv = Math.floor(v * 2), sens = (cu + cv) % 2;
    const t = sens ? fract(v * 2) : fract(u * 2), b = sens ? fract(u * 2) : fract(v * 2);
    return Math.sin(Math.PI * t) * (0.55 + 0.45 * Math.sin(Math.PI * b)); } },
  picots: { nom: 'Picots (dôme)', f: (u, v, p) => { const r = Math.hypot(fract(u) - 0.5, fract(v) - 0.5) / (0.5 - p.trait * 0.5); return Math.sqrt(Math.max(0, 1 - r * r)); } },
  damier: { nom: 'Damier', f: (u, v, p) => { const a = lisse(-p.flou * 4, p.flou * 4, Math.sin(Math.PI * 2 * u) * Math.sin(Math.PI * 2 * v)); return a; } },
  bois: { nom: 'Veines de bois', f: (u, v) => 0.5 + 0.5 * Math.sin(2 * Math.PI * (u + 1.2 * fbm(u * 0.15, v * 0.6, 3))) },
  cuir: { nom: 'Cuir / grain', f: (u, v, p) => { const [a, b] = voronoi(u * 3, v * 3, 1); return 0.65 * clamp01((b - a) * 3) + 0.35 * fbm(u * 4, v * 4); } },
  bruit: { nom: 'Granuleux doux', f: (u, v) => clamp01((fbm(u * 2, v * 2, 5) - 0.5) * 2.4 + 0.5) },
};

// ------------------------------------------------------------------ calcul du déplacement
// geo : BufferGeometry INDEXÉE (positions monde). info : prépa (normales, masque de zone, centre...).
export function preparer(geo) {
  const P = geo.attributes.position.array.slice(), n = P.length / 3, I = geo.index.array;
  geo.computeVertexNormals();
  const N = geo.attributes.normal.array.slice();
  // normales de faces -> zone par sommet (TOUTES ses faces doivent être dans la zone : arêtes vives nettes)
  const nf = I.length / 3, FN = new Float32Array(nf * 3), FZ = new Float32Array(nf);
  for (let f = 0; f < nf; f++) {
    const a = I[f * 3] * 3, b = I[f * 3 + 1] * 3, c = I[f * 3 + 2] * 3;
    const ux = P[b] - P[a], uy = P[b + 1] - P[a + 1], uz = P[b + 2] - P[a + 2], vx = P[c] - P[a], vy = P[c + 1] - P[a + 1], vz = P[c + 2] - P[a + 2];
    let x = uy * vz - uz * vy, y = uz * vx - ux * vz, z = ux * vy - uy * vx; const l = Math.hypot(x, y, z) || 1;
    FN[f * 3] = x / l; FN[f * 3 + 1] = y / l; FN[f * 3 + 2] = z / l; FZ[f] = (P[a + 2] + P[b + 2] + P[c + 2]) / 3;
  }
  let zmin = 1e9, zmax = -1e9, cx = 0, cy = 0;
  for (let i = 0; i < n; i++) { zmin = Math.min(zmin, P[i * 3 + 2]); zmax = Math.max(zmax, P[i * 3 + 2]); cx += P[i * 3]; cy += P[i * 3 + 1]; }
  cx /= n; cy /= n;
  // objet rond autour de Z ? (projection cylindrique sans couture)
  let s = 0, s2 = 0, k = 0;
  for (let i = 0; i < n; i++) if (Math.abs(N[i * 3 + 2]) < 0.5) { const r = Math.hypot(P[i * 3] - cx, P[i * 3 + 1] - cy); s += r; s2 += r * r; k++; }
  const rmoy = k ? s / k : 0, rond = k > 50 && Math.sqrt(Math.max(0, s2 / k - rmoy * rmoy)) / Math.max(rmoy, 1e-6) < 0.1;
  return { P, N, I, FN, FZ, n, zmin, zmax, cx, cy, rmoy, rond };
}

export function appliquer(geo, info, q) {
  // q : { motif, profondeur, taille, etirement, rotation, trait, nettete, alea, du, dv, zones, bas, haut, projection, inverser, fondu }
  const M = MOTIFS[q.motif] || MOTIFS.alveoles, { P, N, I, FN, FZ, n, zmin, zmax, cx, cy, rmoy } = info;
  const pos = geo.attributes.position.array;
  const H = zmax - zmin, z0 = zmin + H * q.bas / 100, z1 = zmin + H * q.haut / 100;
  const pp = { trait: q.trait, nettete: q.nettete, alea: q.alea, flou: Math.max(0.01, 0.06 / Math.max(q.nettete, 0.2)) };
  const ang = q.rotation * Math.PI / 180, ca = Math.cos(ang), sa = Math.sin(ang);
  const sx = q.taille * Math.sqrt(q.etirement), sy = q.taille / Math.sqrt(q.etirement);
  const proj = q.projection === 'auto' ? (info.rond ? 'cylindre' : 'triplanaire') : q.projection;
  // tours entiers sur un objet rond : le motif se referme sans couture
  const tour = 2 * Math.PI * rmoy, nRep = Math.max(1, Math.round(tour / sx)), sxc = tour / nRep;
  const motif2 = (a, b, kx) => {           // coordonnées surface (mm) -> hauteur 0..1
    const x = a * ca - b * sa, y = a * sa + b * ca;
    let h = M.f(x / kx + q.du, y / sy + q.dv, pp);
    if (q.inverser) h = 1 - h;
    return h;
  };
  // zone par face
  const okF = new Uint8Array(FN.length / 3);
  for (let f = 0; f < okF.length; f++) {
    const nz = FN[f * 3 + 2];
    let ok = FZ[f] > zmin + 0.25 && FZ[f] >= z0 - 1e-6 && FZ[f] <= z1 + 1e-6;
    if (q.zones === 'cotes') ok = ok && Math.abs(nz) < 0.7;
    else if (q.zones === 'dessus') ok = ok && nz > 0.7;
    else ok = ok && nz > -0.7;
    okF[f] = ok ? 1 : 0;
  }
  const okV = new Uint8Array(n).fill(1);
  for (let f = 0; f < okF.length; f++) if (!okF[f]) { okV[I[f * 3]] = 0; okV[I[f * 3 + 1]] = 0; okV[I[f * 3 + 2]] = 0; }
  const fonduMm = q.fondu;
  for (let i = 0; i < n; i++) {
    const x = P[i * 3], y = P[i * 3 + 1], z = P[i * 3 + 2], nx = N[i * 3], ny = N[i * 3 + 1], nz = N[i * 3 + 2];
    let d = 0;
    if (okV[i]) {
      let h;
      if (proj === 'cylindre' && Math.abs(nz) < 0.7) {
        const a = Math.atan2(y - cy, x - cx) / (2 * Math.PI) * tour;
        h = motif2(a, z, sxc);
      } else if (proj === 'triplanaire' || (proj === 'cylindre')) {
        const wx = nx ** 4, wy = ny ** 4, wz = nz ** 4, ws = wx + wy + wz || 1;
        h = (wx * motif2(y, z, sx) + wy * motif2(x, z, sx) + wz * motif2(x, y, sx)) / ws;
      } else {
        h = proj === 'x' ? motif2(y, z, sx) : proj === 'y' ? motif2(x, z, sx) : motif2(x, y, sx);
      }
      // fondu près des limites de zone en hauteur (pas de marche brutale)
      let w = 1;
      if (fonduMm > 0 && q.zones !== 'dessus') w = Math.min(lisse(z0, z0 + fonduMm, z), 1 - lisse(z1 - fonduMm, z1, z), lisse(zmin, zmin + fonduMm, z));
      d = h * q.profondeur * w;
    }
    pos[i * 3] = x + nx * d; pos[i * 3 + 1] = y + ny * d; pos[i * 3 + 2] = z + nz * d;
  }
  geo.attributes.position.needsUpdate = true;
  geo.computeVertexNormals();
  geo.computeBoundingBox(); geo.computeBoundingSphere();
}
