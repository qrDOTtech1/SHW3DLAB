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
    _, st = git("status", "--porcelain", "--untracked-files=no")
    _, log = git("log", "HEAD..@{u}", "--pretty=format:- %s  (%an, %ar)")
    _, tot = git("rev-list", "--count", "@{u}")
    return {"retard": retard, "local": bool(st.strip()), "changelog": log, "cible": f"v1.{tot.strip()}"}


def appliquer_maj(e: dict, fenetre=None) -> bool:
    _, req_avant = git("rev-parse", "HEAD:requirements.txt")
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

    def quitter(icon, item):
        arreter_serveur()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Ouvrir le dashboard", ouvrir, default=True),
        pystray.MenuItem("Verifier les mises a jour", verifier),
        pystray.MenuItem(lambda _: f"Version {version()}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Arreter SHW 3DLAB", quitter),
    )
    pystray.Icon("shw3dlab", fond, f"SHW 3DLAB {version()}", menu).run()


def main():
    e = etat_maj()
    if e.get("retard") and not e.get("local"):
        splash_maj(e)
    demarrer_serveur()
    webbrowser.open(URL)
    icone()


if __name__ == "__main__":
    main()
