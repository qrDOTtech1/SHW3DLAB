"""SHW 3DLAB - lanceur.

Au demarrage :
  1. verifie le depot git (GitHub) : si une mise a jour existe -> fenetre "Telechargement derniere MAJ vX"
     avec le changelog (messages des commits), git pull, reinstalle les dependances si requirements.txt a change ;
  2. demarre le serveur (port 8890) sans fenetre et ouvre le dashboard ;
  3. installe une icone SHW dans la zone de notification : Ouvrir le dashboard / Verifier les mises a jour /
     Arreter SHW 3DLAB.
Si des modifications locales non enregistrees existent (machine de dev), la mise a jour automatique est
sautee (jamais d'ecrasement de travail en cours) et l'icone le signale.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ICI = Path(__file__).resolve().parent
PORT = 8890
URL = f"http://localhost:{PORT}"
NOWIN = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW


def python_serveur() -> str:
    """Interpreteur du serveur : .venv du depot, sinon variable SHW_PYTHON, sinon l'interpreteur courant."""
    for c in (ICI / ".venv" / "Scripts" / "python.exe", Path(os.environ.get("SHW_PYTHON", "")),
              ICI.parent / "DAVINBOT-V2" / ".venv" / "Scripts" / "python.exe"):
        if str(c) and c.is_file():
            return str(c)
    return sys.executable.replace("pythonw.exe", "python.exe")


def git(*args, timeout=60) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=ICI, capture_output=True, text=True, timeout=timeout,
                           creationflags=NOWIN, encoding="utf8", errors="replace")
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:                               # git absent, reseau...
        return 1, str(e)


def version() -> str:
    _, n = git("rev-list", "--count", "HEAD")
    _, h = git("rev-parse", "--short", "HEAD")
    return f"v1.{n.strip() or '0'} ({h.strip() or '?'})"


def etat_maj() -> dict:
    """{'retard': n, 'local': bool, 'changelog': str, 'cible': 'v1.x'} ; ne modifie rien."""
    c, out = git("fetch", "--quiet", timeout=40)
    if c:
        return {"erreur": "hors ligne ou depot inaccessible", "retard": 0}
    _, n = git("rev-list", "--count", "HEAD..@{u}")
    retard = int(n) if n.strip().isdigit() else 0
    _, st = git("status", "--porcelain", "--untracked-files=no", "--", ".", ":!data/projets")   # projets : synchro
    _, log = git("log", "HEAD..@{u}", "--pretty=format:- %s  (%an, %ar)")
    _, tot = git("rev-list", "--count", "@{u}")
    return {"retard": retard, "local": bool(st.strip()), "changelog": log, "cible": f"v1.{tot.strip()}"}


def appliquer_maj(e: dict, fenetre=None) -> bool:
    _, req_avant = git("rev-parse", "HEAD:requirements.txt")
    sys.path.insert(0, str(ICI))
    from atelier.noyau import synchro                      # projets partages : commit + rebase (+ envoi)
    if not synchro.synchroniser().get("ok"):
        c, out = git("pull", "--ff-only", timeout=180)
        if c:
            return False
    _, req_apres = git("rev-parse", "HEAD:requirements.txt")
    if req_avant != req_apres:
        if fenetre:
            fenetre("Installation des nouvelles dependances...")
        subprocess.run([python_serveur(), "-m", "pip", "install", "-r", "requirements.txt", "--quiet"],
                       cwd=ICI, creationflags=NOWIN)
    return True


# ------------------------------------------------------------------ serveur
_proc: subprocess.Popen | None = None


def port_occupe() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def demarrer_serveur():
    global _proc
    if port_occupe():
        return
    log = open(ICI / "serveur.log", "a", encoding="utf8")
    _proc = subprocess.Popen([python_serveur(), "server/run_server.py"], cwd=ICI, stdout=log, stderr=log,
                             creationflags=NOWIN)
    for _ in range(120):
        if port_occupe():
            return
        time.sleep(0.5)


def arreter_serveur():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(8)
        except Exception:
            _proc.kill()
    elif port_occupe() and os.name == "nt":              # serveur lance par une autre instance
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, creationflags=NOWIN).stdout
        for l in out.splitlines():
            if f":{PORT} " in l and "LISTENING" in l:
                subprocess.run(["taskkill", "/PID", l.split()[-1], "/F"], creationflags=NOWIN, capture_output=True)
    _proc = None


# ------------------------------------------------------------------ fenetre de mise a jour (splash)
def splash_maj(e: dict) -> bool:
    import tkinter as tk
    ok = {"v": False}
    root = tk.Tk()
    root.title("SHW 3DLAB")
    root.configure(bg="#16181d")
    root.geometry("520x380")
    root.resizable(False, False)
    try:
        root.iconphoto(True, tk.PhotoImage(file=str(ICI / "web" / "favicon.png")))
        logo = tk.PhotoImage(file=str(ICI / "web" / "logo_shw.png")).subsample(2, 2)
        tk.Label(root, image=logo, bg="#16181d").pack(pady=(18, 4))
    except Exception:
        tk.Label(root, text="SHWork", fg="#ff6410", bg="#16181d", font=("Segoe UI", 22, "bold italic")).pack(pady=(18, 4))
    tk.Label(root, text=f"Telechargement derniere MAJ : {e['cible']}", fg="#ffffff", bg="#16181d",
             font=("Segoe UI", 13, "bold")).pack()
    etat = tk.Label(root, text=f"{e['retard']} nouveaute(s) - version actuelle {version()}", fg="#9aa0aa", bg="#16181d",
                    font=("Segoe UI", 9))
    etat.pack(pady=(2, 8))
    txt = tk.Text(root, height=11, bg="#1f2229", fg="#d8dbe2", bd=0, font=("Segoe UI", 9), wrap="word", padx=10, pady=8)
    txt.insert("1.0", "Changelog\n\n" + (e["changelog"] or "-"))
    txt.configure(state="disabled")
    txt.pack(fill="both", expand=True, padx=18, pady=(0, 14))

    def maj():
        def cb(m):
            root.after(0, lambda: etat.configure(text=m))
        cb("Telechargement...")
        ok["v"] = appliquer_maj(e, cb)
        cb("Mise a jour installee - demarrage" if ok["v"] else "Echec de la mise a jour (on demarre la version actuelle)")
        root.after(900, root.destroy)
    threading.Thread(target=maj, daemon=True).start()
    root.mainloop()
    return ok["v"]


# ------------------------------------------------------------------ icone zone de notification
def icone():
    import pystray
    from PIL import Image

    img = Image.open(ICI / "web" / "favicon.png").convert("RGBA")
    fond = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    img.thumbnail((64, 64))
    fond.paste(img, ((64 - img.width) // 2, (64 - img.height) // 2), img)

    def ouvrir(icon=None, item=None):
        webbrowser.open(URL)

    def verifier(icon, item):
        e = etat_maj()
        if e.get("erreur"):
            icon.notify(e["erreur"], "SHW 3DLAB")
        elif e["retard"] == 0:
            icon.notify(f"Tu es a jour : {version()}", "SHW 3DLAB")
        elif e["local"]:
            icon.notify("Mise a jour disponible, mais des modifications locales sont en cours (git) : "
                        "enregistre-les (commit) puis reessaie.", "SHW 3DLAB")
        else:
            icon.notify(f"Mise a jour {e['cible']} : telechargement...", "SHW 3DLAB")
            if appliquer_maj(e):
                arreter_serveur(); demarrer_serveur()
                icon.title = f"SHW 3DLAB {version()}"
                icon.notify(f"A jour : {version()}\n" + e["changelog"][:200], "SHW 3DLAB")

    def synchro_menu(icon, item):
        sys.path.insert(0, str(ICI))
        from atelier.noyau import synchro
        e = synchro.synchroniser()
        icon.notify(("Projets a jour" + (f" : {e['recus']} recu(s), {e['envoyes']} envoye(s)" if e["recus"] or e["envoyes"] else ""))
                    if e["ok"] else e["message"], "SHW 3DLAB")

    def quitter(icon, item):
        arreter_serveur()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Ouvrir le dashboard", ouvrir, default=True),
        pystray.MenuItem("Verifier les mises a jour", verifier),
        pystray.MenuItem("Synchroniser les projets", synchro_menu),
        pystray.MenuItem(lambda _: f"Version {version()}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Arreter SHW 3DLAB", quitter),
    )
    pystray.Icon("shw3dlab", fond, f"SHW 3DLAB {version()}", menu).run()




# points de controle du lancement : des vrais, et d'autres... moins vrais. Puissance !
CHECKPOINTS = [
    "Vérification des mises à jour",
    "Démarrage du moteur 3D",
    "Ajout de puissance. Beaucoup plus de puissance.",
    "Chargement des bibliothèques de géométrie",
    "Lecture du manuel d'utilisation... non. Personne ne lit le manuel.",
    "Calibrage du rendu MuJoCo",
    "Consultation du pilote d'essai. Il n'a rien dit. C'est bon signe.",
    "Chargement des polices et du logo SHWork",
    "Retrait de tous les boulons. La v2.3 n'en a plus besoin, de toute façon.",
    "Vérification du nid d'abeille. Les abeilles, elles, ne sont pas d'accord.",
    "Préparation du trancheur CuraEngine",
    "Ce qui pouvait mal tourner ? Absolument tout. Et pourtant, nous y voilà.",
]
BIERE = [
    "Le mieux, c'est de ne rien toucher et de siroter sa bière en paix pendant que ça progresse.",
    "Ne touchez a rien. Prenez une bière. Admirez la puissance.",
    "Asseyez-vous, ouvrez une bière : la machine s'occupe de tout. Enfin, presque.",
]


# ------------------------------------------------------------------ fenetre de LANCEMENT (pluie matrix -> message sobre)
def ecran_lancement(travail):
    """Ouvre la fenetre de lancement et execute travail(etape) dans un thread ; etape(texte, fraction) met a
    jour le message et la progression. La fenetre se ferme quand travail() rend la main."""
    import random
    import tkinter as tk
    sys.path.insert(0, str(ICI))
    try:
        from atelier.noyau.systeme import ram
    except Exception:
        ram = lambda: {"pct": 0, "utilise_go": 0, "total_go": 0}
    W, H = 460, 380
    root = tk.Tk()
    root.overrideredirect(True)                          # fenetre sans bordure, centree
    root.attributes("-topmost", True)
    x = (root.winfo_screenwidth() - W) // 2
    y = (root.winfo_screenheight() - H) // 2
    root.geometry(f"{W}x{H}+{x}+{y}")
    root.configure(bg="#0d0f13")
    cv = tk.Canvas(root, width=W, height=150, bg="#0d0f13", highlightthickness=0)
    cv.pack()
    glyphes = "SHW3DLAB01アイウエオカキクケコサシスセソ#%&*+<>/="
    fs = 14
    cols = W // fs
    gouttes = [random.uniform(-4, 11) for _ in range(cols)]
    traces = []
    t0 = time.time()
    try:
        logo = tk.PhotoImage(file=str(ICI / "web" / "logo_shw.png")).subsample(2, 2)
    except Exception:
        logo = None
    etat = {"titre": "Lancement de SHW 3DLAB", "p": 0.0, "fini": False}
    f = tk.Frame(root, bg="#0d0f13")
    f.pack(fill="both", expand=True, padx=20, pady=(10, 16))
    lt = tk.Label(f, text=etat["titre"], fg="#e9ebef", bg="#0d0f13", font=("Segoe UI", 11, "bold"), anchor="w",
                  wraplength=W - 40, justify="left", height=2)
    lt.pack(fill="x")
    tk.Label(f, text="Vous pouvez rencontrer des ralentissements pendant le chargement.", fg="#8b919c", bg="#0d0f13",
             font=("Segoe UI", 9), anchor="w").pack(fill="x")
    tk.Label(f, text=random.choice(BIERE), fg="#ff6410", bg="#0d0f13", font=("Georgia", 9, "italic"), anchor="w",
             wraplength=W - 40, justify="left").pack(fill="x", pady=(2, 10))

    def jauge(nom):
        l = tk.Frame(f, bg="#0d0f13"); l.pack(fill="x")
        tk.Label(l, text=nom, fg="#8b919c", bg="#0d0f13", font=("Segoe UI", 8)).pack(side="left")
        v = tk.Label(l, text="", fg="#8b919c", bg="#0d0f13", font=("Segoe UI", 8)); v.pack(side="right")
        c = tk.Canvas(f, height=7, bg="#1d2027", highlightthickness=0); c.pack(fill="x", pady=(2, 8))
        return v, c
    vp, cp = jauge("Progression")
    vr, cr = jauge("Mémoire vive")

    def barre(c, frac, coul):
        c.delete("all")
        w = max(1, c.winfo_width())
        c.create_rectangle(0, 0, int(w * max(0, min(1, frac))), 7, fill=coul, width=0)

    def anim():
        age = time.time() - t0
        for it in traces:
            cv.delete(it)
        traces.clear()
        cv.create_rectangle(0, 0, W, 150, fill="#0d0f13", width=0)
        vitesse = 1.0 if age < 1.4 else 0.45
        for i in range(cols):
            for k in range(6):                          # queue de la goutte (degrade)
                yy = (gouttes[i] - k) * fs
                if 0 <= yy < 150:
                    coul = "#ffd1b3" if k == 0 else ("#ff6410" if k < 3 else "#7a3410")
                    if age >= 1.4:
                        coul = "#5c2a0e" if k else "#a04a17"
                    cv.create_text(i * fs + 7, yy, text=random.choice(glyphes), fill=coul, font=("Consolas", 10))
            gouttes[i] += vitesse
            if gouttes[i] * fs > 150 + 6 * fs and random.random() > 0.9:
                gouttes[i] = random.uniform(-6, 0)
        if logo is not None and age > 1.1:
            cv.create_image(16, 12, image=logo, anchor="nw")
        if not etat["fini"]:
            root.after(60, anim)

    def maj():
        r = ram()
        vr.configure(text=f"{r['utilise_go']} / {r['total_go']} Go ({r['pct']} %)")
        barre(cr, r["pct"] / 100, "#3ddc97" if r["pct"] < 70 else ("#f5c542" if r["pct"] < 88 else "#ff5a4f"))
        lt.configure(text=etat["titre"])
        vp.configure(text=f"{int(etat['p'] * 100)} %")
        barre(cp, etat["p"], "#ff6410")
        if etat["fini"]:
            root.after(350, root.destroy)
        else:
            root.after(400, maj)

    def etape(titre, frac):
        etat["titre"], etat["p"] = titre, frac

    def tourner():
        try:
            travail(etape)
        finally:
            etat["p"] = 1.0
            etat["fini"] = True
    threading.Thread(target=tourner, daemon=True).start()
    anim(); maj()
    root.mainloop()


def main():
    e = etat_maj()
    if e.get("retard") and not e.get("local"):
        splash_maj(e)

    def travail(etape):
        # 15 s de spectacle : les VRAIES etapes (le serveur demarre pendant ce temps) entrecoupees de points de
        # controle "a la Clarkson". Si le moteur met plus longtemps, on attend honnetement qu'il soit pret.
        deja = port_occupe()
        if not deja:
            threading.Thread(target=demarrer_serveur, daemon=True).start()
        etapes = list(CHECKPOINTS)
        duree = 15.0
        t = time.time()
        for i, txt in enumerate(etapes):
            fin_etape = t + duree * (i + 1) / len(etapes)
            while time.time() < fin_etape:
                frac = min(0.97, (time.time() - t) / duree)
                etape(txt, frac)
                time.sleep(0.1)
        while not port_occupe() and time.time() - t < 120:
            etape("Le moteur prend son temps. Comme une boîte automatique des années 80.", 0.98)
            time.sleep(0.3)
        etape("Ouverture du dashboard. Accrochez-vous.", 1.0)
        time.sleep(0.6)
    ecran_lancement(travail)
    webbrowser.open(URL)
    icone()


if __name__ == "__main__":
    main()
