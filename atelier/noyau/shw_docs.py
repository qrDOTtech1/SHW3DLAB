"""SHW Docs : generateur de notices et fiches (montage, cablage) en HTML propre.

Reutilisable pour tous les projets SHW (turbine, boitier, plus tard la doc complete du bras).
Logo SHW, ton direct facon Jeremy Clarkson (sans references automobiles), imprimable.

    from atelier.noyau.shw_docs import Doc
    d = Doc("Titre", "Sous-titre", logo="web/logo_shw.png", code="DA-LAB")
    d.intro("Un paragraphe qui met l'ambiance.")
    d.pieces([("x3", "NEMA 17"), ("x1", "ESP32-S3")])
    d.cablage("Moteurs", [("STEP M1", "GPIO 4"), ...], note="...")
    d.etapes("Montage", ["Etape 1.", "Etape 2."])
    d.avert("A ne pas oublier.")
    d.ecrire("sortie.html")
"""
from __future__ import annotations

import base64
import html
from pathlib import Path


def _esc(x):
    return html.escape(str(x))


class Doc:
    def __init__(self, titre, sous_titre="", logo=None, code="", soustexte=""):
        self.titre, self.sous_titre, self.code = titre, sous_titre, code
        self.soustexte = soustexte
        self.logo64 = ""
        if logo and Path(logo).exists():
            self.logo64 = base64.b64encode(Path(logo).read_bytes()).decode()
        self.corps = []

    # --- blocs ---
    def intro(self, texte):
        self.corps.append(f'<p class="lead">{_esc(texte)}</p>')

    def h(self, titre):
        self.corps.append(f'<h2>{_esc(titre)}</h2>')

    def para(self, texte):
        self.corps.append(f'<p>{_esc(texte)}</p>')

    def pieces(self, lignes, titre="Pièces"):
        r = "".join(f'<tr><td class="q">{_esc(q)}</td><td>{_esc(n)}</td></tr>' for q, n in lignes)
        self.corps.append(f'<h2>{_esc(titre)}</h2><table class="t"><tbody>{r}</tbody></table>')

    def cablage(self, titre, lignes, note=""):
        r = "".join(f'<tr><td><b>{_esc(a)}</b></td><td class="pin">{_esc(b)}</td>'
                    + (f'<td class="c">{_esc(c)}</td>' if len(x) > 2 else '<td></td>')
                    + '</tr>' for x in lignes for a, b, c in [(x[0], x[1], x[2] if len(x) > 2 else "")])
        n = f'<p class="note">{_esc(note)}</p>' if note else ""
        self.corps.append(f'<h2>{_esc(titre)}</h2><table class="t cab"><thead><tr><th>Signal</th><th>Broche</th><th>Remarque</th></tr></thead><tbody>{r}</tbody></table>{n}')

    def etapes(self, titre, liste):
        li = "".join(f'<li>{_esc(e)}</li>' for e in liste)
        self.corps.append(f'<h2>{_esc(titre)}</h2><ol class="et">{li}</ol>')

    def cmd(self, titre, lignes):
        r = "".join(f'<tr><td class="pin">{_esc(a)}</td><td>{_esc(b)}</td></tr>' for a, b in lignes)
        self.corps.append(f'<h2>{_esc(titre)}</h2><table class="t cmd"><tbody>{r}</tbody></table>')

    def avert(self, texte):
        self.corps.append(f'<div class="warn"><b>⚠ Sécurité.</b> {_esc(texte)}</div>')

    def svg(self, titre, svg_markup):
        self.corps.append(f'<h2>{_esc(titre)}</h2><div class="fig">{svg_markup}</div>')

    # --- rendu ---
    def html(self):
        logo = f'<img class="logo" src="data:image/png;base64,{self.logo64}" alt="SHWork">' if self.logo64 else '<b class="logo-txt">SHWork</b>'
        code = f'<span class="code">{_esc(self.code)}</span>' if self.code else ""
        soustexte = f'<p class="st">{_esc(self.soustexte)}</p>' if self.soustexte else ""
        return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(self.titre)}</title>
<style>
:root{{--bg:#0d0f13;--p:#171b22;--l:#262c36;--t:#e8eaee;--m:#98a1b0;--a:#ff6410;--a2:#ffb36b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--t);font:15.5px/1.5 "Segoe UI",system-ui,sans-serif}}
.w{{max-width:940px;margin:auto;padding:0 20px 60px}}
header{{border-bottom:3px solid var(--a);padding:22px 0 30px;margin-bottom:8px}}
.top{{display:flex;align-items:center;gap:14px;margin-bottom:26px}}.logo{{height:34px}}.logo-txt{{font-size:22px;color:var(--a)}}
.code{{margin-left:auto;font:600 12px Consolas,monospace;border:1px solid var(--a);color:var(--a2);padding:3px 9px;border-radius:5px}}
h1{{font-size:clamp(28px,5vw,44px);margin:0 0 6px;letter-spacing:-.01em}}
.st{{color:var(--m);margin:0;font-size:18px}}
.lead{{font-size:17px;color:#c9cfd9;font-style:italic;border-left:3px solid var(--a);padding-left:14px;margin:22px 0}}
h2{{font-size:21px;margin:30px 0 10px;border-bottom:1px solid var(--l);padding-bottom:5px}}
.t{{width:100%;border-collapse:collapse;background:var(--p);border:1px solid var(--l);border-radius:8px;overflow:hidden}}
.t td,.t th{{padding:8px 12px;border-bottom:1px solid var(--l);text-align:left}}.t tr:last-child td{{border-bottom:0}}
.t th{{color:var(--m);font-size:12px;letter-spacing:.08em;text-transform:uppercase}}
td.q,.pin{{font-family:Consolas,monospace;color:var(--a2);white-space:nowrap}}td.c{{color:var(--m);font-size:14px}}
ol.et{{counter-reset:e;list-style:none;padding:0}}ol.et li{{counter-increment:e;position:relative;padding:10px 0 10px 44px;border-bottom:1px solid var(--l)}}
ol.et li:before{{content:counter(e);position:absolute;left:0;top:8px;width:28px;height:28px;background:var(--a);color:#160800;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700}}
.note{{color:var(--m);font-size:14px;margin:8px 2px}}
.warn{{background:#2a1d08;border-left:4px solid var(--a);border-radius:6px;padding:12px 16px;margin:16px 0}}.warn b{{color:var(--a2)}}
.fig{{background:var(--p);border:1px solid var(--l);border-radius:8px;padding:14px;overflow:auto}}
footer{{margin-top:40px;border-top:1px solid var(--l);padding-top:16px;color:var(--m);font-size:13px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}}
@media print{{body{{background:#fff;color:#111}}.t,.fig{{background:#fff;border-color:#ccc}}.lead,.st,td.c,.note,.t th,footer{{color:#555}}.warn{{background:#f6efe2}}h2{{break-after:avoid}}.t,ol.et li,.warn{{break-inside:avoid}}}}
</style></head><body><div class="w">
<header><div class="top">{logo}{code}</div><h1>{_esc(self.titre)}</h1>{soustexte}</header>
{"".join(self.corps)}
<footer><span>Davinarm by SHW — SPEC-A Hardware Lab</span><span>Document de travail</span></footer>
</div></body></html>'''

    def ecrire(self, chemin):
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        Path(chemin).write_text(self.html(), encoding="utf8")
        return chemin
