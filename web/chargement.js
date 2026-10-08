// FENETRE DE CHARGEMENT SHW 3DLAB : pluie "matrix" aux couleurs SHWork, puis message sobre + jauge RAM + progression.
// Usage : const c = window.SHWCharge.debut('Ouverture du projet ServBuddy', { cle: 'servbuddy' }) ... c.fin()
// - n'apparait qu'au-dela de 900 ms (les operations rapides ne la declenchent pas) ;
// - progression ESTIMEE d'apres la duree de la derniere operation de meme cle (memorisee), sinon courbe douce ;
// - jauge RAM reelle (machine + serveur) via /api/systeme.
const CSS = `
#shw-charge{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;background:rgba(6,8,11,.62);backdrop-filter:blur(3px)}
#shw-charge .bx{position:relative;width:min(460px,92vw);border-radius:16px;overflow:hidden;background:#0d0f13;border:1px solid #2a2e37;
  box-shadow:0 20px 60px rgba(0,0,0,.5)}
#shw-charge canvas{display:block;width:100%;height:150px}
#shw-charge .in{padding:16px 20px 18px;font-family:'Segoe UI',system-ui,sans-serif;color:#e9ebef}
#shw-charge .t{font-size:15px;font-weight:600;margin:0 0 2px}
#shw-charge .s{font-size:12px;color:#8b919c;margin:0 0 4px}
#shw-charge .b{font:italic 12.5px Georgia,'Times New Roman',serif;color:#ff6410;margin:0 0 14px}
#shw-charge .e{font-size:11px;color:#c9ced6;margin:10px 0 0;min-height:15px;transition:opacity .3s}
#shw-charge .l{display:flex;justify-content:space-between;font-size:11px;color:#8b919c;margin:8px 0 4px}
#shw-charge .g{height:7px;border-radius:99px;background:#1d2027;overflow:hidden}
#shw-charge .g i{display:block;height:100%;width:0;border-radius:99px;background:#ff6410;transition:width .35s ease}

#shw-charge .logo{position:absolute;left:16px;top:12px;height:20px;opacity:0;transition:opacity .5s}
`;
// etapes classiques des chargements de projet, avec une pointe d'humour de temps a autre
const ETAPES = ['Lecture du projet', 'Génération de la géométrie', 'Vérification des collisions',
  'Rien ne touche la peau ? Vérifié.', 'Assemblage des pièces', 'Ajout de puissance. Pas trop. Juste ce qu\'il faut.',
  'Calcul de la course d\'ouverture', 'Mise en cache pour la prochaine fois', 'Préparation de l\'affichage 3D',
  'Patience. Les grands projets, comme les grandes voitures, ne démarrent pas au quart de tour.'];
const BIERE = ['Le mieux, c\'est de ne rien toucher et de siroter sa bière en paix pendant que ça progresse.',
  'Ne touchez a rien. Prenez une bière. Admirez la puissance.',
  'Asseyez-vous, ouvrez une bière : la machine s\'occupe de tout. Enfin, presque.'];
let el = null, raf = 0, poll = 0, minuteur = 0, t0 = 0, cleCour = '', attendu = 0, actifs = 0;

function matrix(cv) {
  const ctx = cv.getContext('2d'), dpr = devicePixelRatio || 1;
  const W = cv.width = cv.clientWidth * dpr, H = cv.height = cv.clientHeight * dpr;
  const fs = 14 * dpr, cols = Math.ceil(W / fs), y = Array.from({ length: cols }, () => Math.random() * (H / fs) - 4);
  const glyphes = 'SHW3DLAB01アイウエオカキクケコサシスセソ#%&*+<>/\\=';
  const debut = performance.now();
  ctx.fillStyle = '#0d0f13'; ctx.fillRect(0, 0, W, H);
  function pas(t) {
    const age = (t - debut) / 1000;
    ctx.fillStyle = age < 1.4 ? 'rgba(13,15,19,.16)' : 'rgba(13,15,19,.28)';
    ctx.fillRect(0, 0, W, H);
    ctx.font = `${fs}px Consolas,monospace`;
    for (let i = 0; i < cols; i++) {
      const ch = glyphes[Math.floor(Math.random() * glyphes.length)];
      ctx.fillStyle = Math.random() < 0.08 ? '#ffd1b3' : (age < 1.4 ? '#ff6410' : 'rgba(255,100,16,.35)');
      ctx.fillText(ch, i * fs, y[i] * fs);
      if (y[i] * fs > H && Math.random() > 0.96) y[i] = 0;
      y[i] += age < 1.4 ? 1 : 0.45;                    // la pluie ralentit : place au message sobre
    }
    if (age > 1.1) { const lg = el?.querySelector('.logo'); if (lg) lg.style.opacity = 1; }
    raf = requestAnimationFrame(pas);
  }
  raf = requestAnimationFrame(pas);
}

function afficher(titre) {
  if (el) return;
  if (!document.getElementById('shw-charge-css')) {
    const s = document.createElement('style'); s.id = 'shw-charge-css'; s.textContent = CSS; document.head.appendChild(s);
  }
  el = document.createElement('div'); el.id = 'shw-charge';
  el.innerHTML = `<div class="bx"><canvas></canvas><img class="logo" src="logo_shw.png" alt="">
    <div class="in"><p class="t">${titre}</p><p class="s">Vous pouvez rencontrer des ralentissements pendant le chargement.</p>
      <p class="b">${BIERE[Math.floor(Math.random() * BIERE.length)]}</p>
      <div class="l"><span>Progression</span><span data-p>0 %</span></div><div class="g"><i data-gp></i></div>
      <div class="l"><span>Mémoire vive</span><span data-r>-</span></div><div class="g ram"><i data-gr></i></div>
      <p class="e" data-e>${ETAPES[0]}</p></div></div>`;
  document.body.appendChild(el);
  matrix(el.querySelector('canvas'));
  const maj = async () => {
    try {
      const r = await (await fetch('/api/systeme')).json();
      const gr = el.querySelector('[data-gr]'); gr.style.width = r.pct + '%';
      gr.style.background = r.pct < 70 ? '#3ddc97' : r.pct < 88 ? '#f5c542' : '#ff5a4f';
      el.querySelector('[data-r]').textContent = `${r.utilise_go} / ${r.total_go} Go (${r.pct} %) · serveur ${r.processus_mo} Mo`;
    } catch { }
  };
  maj(); poll = setInterval(() => {
    maj();
    const dt = (performance.now() - t0) / 1000;
    const p = attendu > 0 ? Math.min(95, 100 * dt / attendu) : 95 * (1 - Math.exp(-dt / 20));     // estimation honnete : jamais 100 avant la fin
    el.querySelector('[data-gp]').style.width = p.toFixed(0) + '%';
    el.querySelector('[data-p]').textContent = `${p.toFixed(0)} %${attendu ? '' : ' (estimation)'}`;
    const k = Math.floor(dt / 3.2) % ETAPES.length, e = el.querySelector('[data-e]');           // une etape toutes les ~3 s
    if (e.dataset.k != k) { e.dataset.k = k; e.textContent = ETAPES[k]; }
  }, 500);
}

function fermer() {
  clearTimeout(minuteur); clearInterval(poll); cancelAnimationFrame(raf);
  if (el) {
    el.querySelector('[data-gp]').style.width = '100%'; el.querySelector('[data-p]').textContent = '100 %';
    const e = el; el = null; setTimeout(() => e.remove(), 250);
  }
}

window.SHWCharge = {
  debut(titre = 'Chargement', { cle = '', delai = 900 } = {}) {
    actifs++;
    if (actifs === 1) {
      t0 = performance.now(); cleCour = cle;
      try { attendu = +(localStorage.getItem('shw-duree-' + cle) || 0); } catch { attendu = 0; }
      clearTimeout(minuteur); minuteur = setTimeout(() => afficher(titre), delai);
    }
    let fini = false;
    return {
      fin() {
        if (fini) return; fini = true; actifs = Math.max(0, actifs - 1);
        if (actifs) return;
        const d = (performance.now() - t0) / 1000;
        if (cleCour && d > 1) { try { localStorage.setItem('shw-duree-' + cleCour, d.toFixed(1)); } catch { } }
        fermer();
      },
    };
  },
};
