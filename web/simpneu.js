// SIMULATION PNEUMATIQUE : compresseur -> reservoir -> fuites / consommation, avec REGULATION
// (aucune, tout-ou-rien avec hysteresis, PID sur la vitesse du moteur) et soupape de securite.
// Modele isotherme : p_abs * V = quantite d'air ; debits en litres d'air libre (NL).

export function simuler(c) {
  // c : { cyl_cm3, taux_geo, etanche_bar, n_max, mode, consigne, hyst, kp, ki, v_res_L, fuite_Lmin_1bar,
  //       verin_d, verin_course, verin_cpm, soupape, duree, dt }
  const dt = c.dt || 0.05, N = Math.round(c.duree / dt);
  const pmaxAbs = Math.min(c.taux_geo, (c.etanche_bar || 4) + 1);      // pression abs que les joints imprimes tiennent
  let p = 0, integ = 0, marche = 1, ntot = 0, tCons = null, pmax = 0, t_on = 0;
  const out = { t: [], p: [], n: [], qin: [], qout: [] };
  const A_verin = Math.PI * (c.verin_d / 2) ** 2 / 100;                  // cm2
  const v_cycle_L = 2 * A_verin * c.verin_course / 10 / 1000;           // double effet : sortie + rentree (L a p)
  for (let i = 0; i <= N; i++) {
    const t = i * dt;
    // ---------------- regulation
    let n = c.n_max;
    if (c.mode === 'tor') {
      if (p >= c.consigne + c.hyst / 2) marche = 0;
      if (p <= c.consigne - c.hyst / 2) marche = 1;
      n = marche ? c.n_max : 0;
    } else if (c.mode === 'pid') {
      const e = c.consigne - p;
      integ = Math.max(-50, Math.min(50, integ + e * dt));
      n = Math.max(0, Math.min(c.n_max, c.n_max * (c.kp * e + c.ki * integ)));
    }
    // ---------------- debits (litres d'air libre par seconde)
    const pr = (p + 1) / 1;
    const eta = Math.max(0, 0.85 * (1 - (pr - 1) / Math.max(pmaxAbs - 1, 0.01)));
    let qin = c.cyl_cm3 / 1000 * n / 60 * eta;                            // repli : formule (1 compression / tour d'arbre)
    if (c.courbe?.length) {                                                // courbe du CYCLE REEL simule, a l'echelle du regime
      const cb = c.courbe; let q = 0;
      if (p <= cb[0].p_reservoir_bar) q = cb[0].debit_libre_L_min;
      else if (p >= cb.at(-1).p_reservoir_bar) q = cb.at(-1).debit_libre_L_min;
      else for (let k = 1; k < cb.length; k++) if (p <= cb[k].p_reservoir_bar) { const a = cb[k - 1], b = cb[k], t = (p - a.p_reservoir_bar) / (b.p_reservoir_bar - a.p_reservoir_bar); q = a.debit_libre_L_min + t * (b.debit_libre_L_min - a.debit_libre_L_min); break; }
      qin = Math.max(0, q) / 60 * (n / (c.rpm_ref || c.n_max));
    }
    const qfuite = c.fuite_Lmin_1bar / 60 * Math.sqrt(Math.max(p, 0));
    const qcons = p > 0.3 ? v_cycle_L * (p + 1) * c.verin_cpm / 60 : 0;
    const qsoup = p > c.soupape ? (p - c.soupape) * 5 : 0;               // la soupape evacue fort au-dela du tarage
    p = Math.max(0, p + (qin - qfuite - qcons - qsoup) / c.v_res_L * dt);
    if (n > 0) t_on += dt;
    ntot += n / 60 * dt; pmax = Math.max(pmax, p);
    if (tCons === null && p >= c.consigne * 0.98) tCons = t;
    if (i % Math.max(1, Math.round(0.2 / dt)) === 0) { out.t.push(t); out.p.push(p); out.n.push(n); out.qin.push(qin * 60); out.qout.push((qfuite + qcons) * 60); }
  }
  // force du verin a la pression finale
  const F = A_verin / 100 * p * 1e5 / 10000 * 100;
  return { ...out, pmax, tConsigne: tCons, marche_pct: 100 * t_on / c.duree, tours: ntot, p_fin: p,
           force_verin_N: Math.PI * (c.verin_d / 2) ** 2 * p * 0.1, pmaxAbs };
}

export function tracer(canvas, r, c) {
  const ctx = canvas.getContext('2d'), W = canvas.width, H = canvas.height, m = 28;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#10141b'; ctx.fillRect(0, 0, W, H);
  const pm = Math.max(c.soupape * 1.1, r.pmax * 1.15, c.consigne * 1.3, 0.5), T = r.t.at(-1) || 1;
  const X = t => m + (W - m - 8) * t / T, Yp = p => H - 18 - (H - 30) * p / pm, Yn = n => H - 18 - (H - 30) * n / (c.n_max || 1);
  // grille
  ctx.strokeStyle = '#232934'; ctx.lineWidth = 1; ctx.font = '10px Inter, sans-serif'; ctx.fillStyle = '#8a93a3';
  for (let k = 0; k <= 4; k++) { const p = pm * k / 4, y = Yp(p); ctx.beginPath(); ctx.moveTo(m, y); ctx.lineTo(W - 8, y); ctx.stroke(); ctx.fillText(p.toFixed(1), 2, y + 3); }
  ctx.fillText(`${T.toFixed(0)} s`, W - 34, H - 4); ctx.fillText('bar', 2, 10);
  // consigne et soupape
  const ligne = (y, col, dash) => { ctx.strokeStyle = col; ctx.setLineDash(dash); ctx.beginPath(); ctx.moveTo(m, y); ctx.lineTo(W - 8, y); ctx.stroke(); ctx.setLineDash([]); };
  if (c.mode !== 'aucune') ligne(Yp(c.consigne), '#3ddc97', [4, 4]);
  ligne(Yp(c.soupape), '#ff4d6d', [2, 3]);
  // regime moteur (zone)
  ctx.fillStyle = 'rgba(255,179,107,.18)'; ctx.beginPath(); ctx.moveTo(X(0), Yn(0));
  r.t.forEach((t, i) => ctx.lineTo(X(t), Yn(r.n[i]))); ctx.lineTo(X(T), Yn(0)); ctx.fill();
  // pression
  ctx.strokeStyle = '#ff7a2f'; ctx.lineWidth = 2; ctx.beginPath();
  r.t.forEach((t, i) => i ? ctx.lineTo(X(t), Yp(r.p[i])) : ctx.moveTo(X(t), Yp(r.p[i]))); ctx.stroke();
}
