"""SHW 3DLAB - INSTALLATION AUTOMATIQUE (script telecharge et execute par SHW3DLAB_Setup.exe).

Ce fichier vit dans le depot : le modifier = modifier le setup de tout le monde (l'exe telecharge toujours la
derniere version avant de l'executer). Ne depend que de la bibliotheque standard (tkinter, urllib, subprocess).

Etapes : Git -> Python 3.12 -> code (clone / mise a jour) -> environnement + dependances -> raccourcis -> lancement.
Git et Python manquants sont installes par winget (silencieux). Rejouable a volonte (repare une installation).
"""
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

DEPOT = "https://github.com/qrDOTtech1/SHW3DLAB.git"
DEST = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SHW3DLAB"
APP = DEST / "app"
NOWIN = 0x08000000
VERSION_SETUP = "1.0"


def trouver_git():
    for c in (shutil.which("git"), r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if c and Path(c).exists():
            return c
    return None


def trouver_python():
    cands = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe",
             Path(r"C:\Program Files\Python312\python.exe")]
    py = shutil.which("py")
    if py:
        try:
            out = subprocess.run([py, "-3.12", "-c", "import sys;print(sys.executable)"], capture_output=True,
                                 text=True, creationflags=NOWIN, timeout=30).stdout.strip()
            if out:
                cands.insert(0, Path(out))
        except Exception:
            pass
    for c in cands:
        if c.exists():
            return str(c)
    return None


def winget(ident, log):
    log(f"Installation de {ident} (winget, quelques minutes)...")
    r = subprocess.run(["winget", "install", "--id", ident, "-e", "--silent", "--accept-package-agreements",
                        "--accept-source-agreements", "--scope", "user"], capture_output=True, text=True,
                       creationflags=NOWIN, encoding="utf8", errors="replace")
    if r.returncode not in (0, -1978335189):                 # deja installe = ok
        r = subprocess.run(["winget", "install", "--id", ident, "-e", "--silent", "--accept-package-agreements",
                            "--accept-source-agreements"], capture_output=True, text=True, creationflags=NOWIN,
                           encoding="utf8", errors="replace")
    return r.returncode


def lancer(cmd, log, cwd=None):
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         creationflags=NOWIN, encoding="utf8", errors="replace")
    for ligne in p.stdout:
        ligne = ligne.strip()
        if ligne:
            log("   " + ligne[:110], detail=True)
    return p.wait()


def raccourci(chemin_lnk, cible, args, icone, dossier):
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{chemin_lnk}');"
          f"$s.TargetPath='{cible}';$s.Arguments='\"{args}\"';$s.WorkingDirectory='{dossier}';"
          f"$s.IconLocation='{icone}';$s.Description='SHW 3DLAB';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NOWIN, capture_output=True)


def installer(log, fin):
    try:
        # 1. Git
        git = trouver_git()
        if not git:
            winget("Git.Git", log)
            git = trouver_git()
        if not git:
            return fin(False, "Git introuvable : installe-le depuis git-scm.com puis relance le setup.")
        log("Git : ok")
        # 2. Python 3.12
        py = trouver_python()
        if not py:
            winget("Python.Python.3.12", log)
            py = trouver_python()
        if not py:
            return fin(False, "Python 3.12 introuvable : installe-le depuis python.org puis relance le setup.")
        log("Python 3.12 : ok")
        # 3. Code
        DEST.mkdir(parents=True, exist_ok=True)
        if (APP / ".git").exists():
            log("Mise a jour du code...")
            lancer([git, "pull", "--ff-only"], log, cwd=APP)
        else:
            log("Telechargement du code SHW 3DLAB...")
            if lancer([git, "clone", DEPOT, str(APP)], log):
                return fin(False, "Echec du telechargement du depot (connexion ?).")
        # 4. Environnement Python + dependances
        venv_py = APP / ".venv" / "Scripts" / "python.exe"
        if not venv_py.exists():
            log("Creation de l'environnement Python...")
            lancer([py, "-m", "venv", str(APP / ".venv")], log)
        log("Installation des dependances (long la 1re fois : 5 a 15 min)...")
        lancer([str(venv_py), "-m", "pip", "install", "--upgrade", "pip"], log)
        if lancer([str(venv_py), "-m", "pip", "install", "-r", str(APP / "requirements.txt")], log):
            return fin(False, "Echec de l'installation des dependances (voir le detail).")
        # 5. Raccourcis (bureau + menu Demarrer)
        pyw = APP / ".venv" / "Scripts" / "pythonw.exe"
        ico = APP / "web" / "shw3dlab.ico"
        bureau = Path(os.environ["USERPROFILE"]) / "Desktop"
        try:
            import ctypes.wintypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)
            bureau = Path(buf.value)
        except Exception:
            pass
        menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        for d in (bureau, menu):
            raccourci(str(d / "SHW 3DLAB.lnk"), str(pyw), str(APP / "shw3dlab.pyw"), str(ico), str(APP))
        log("Raccourcis 'SHW 3DLAB' : bureau + menu Demarrer")
        # 6. Cura (tranchage) : facultatif
        if not list(Path(r"C:\Program Files").glob("UltiMaker Cura*")):
            log("Info : UltiMaker Cura n'est pas installe (necessaire pour trancher). Installation...")
            winget("Ultimaker.Cura", log)
        fin(True, "SHW 3DLAB est installe.")
    except Exception as e:
        fin(False, f"Erreur : {e}")


def main():
    import tkinter as tk
    root = tk.Tk()
    root.title("SHW 3DLAB - Installation")
    root.configure(bg="#16181d")
    root.geometry("560x420")
    root.resizable(False, False)
    tk.Label(root, text="SHWork", fg="#ff6410", bg="#16181d", font=("Segoe UI", 26, "bold italic")).pack(pady=(18, 0))
    tk.Label(root, text="3DLAB  -  installation", fg="#ffffff", bg="#16181d", font=("Segoe UI", 11, "bold")).pack()
    etat = tk.Label(root, text="Preparation...", fg="#ffb07a", bg="#16181d", font=("Segoe UI", 10))
    etat.pack(pady=(10, 6))
    txt = tk.Text(root, height=14, bg="#1f2229", fg="#c9ccd3", bd=0, font=("Consolas", 8), wrap="none", padx=8, pady=6)
    txt.pack(fill="both", expand=True, padx=16)
    bouton = tk.Button(root, text="Patiente...", state="disabled", bg="#ff6410", fg="white", bd=0,
                       font=("Segoe UI", 10, "bold"), padx=16, pady=6)
    bouton.pack(pady=12)

    def log(m, detail=False):
        def f():
            if not detail:
                etat.configure(text=m)
            txt.insert("end", m + "\n"); txt.see("end")
        root.after(0, f)

    def fin(ok, m):
        def f():
            etat.configure(text=m, fg="#7bd88f" if ok else "#ff6b6b")
            if ok:
                bouton.configure(text="Lancer SHW 3DLAB", state="normal", command=lambda: (
                    subprocess.Popen([str(APP / ".venv" / "Scripts" / "pythonw.exe"), str(APP / "shw3dlab.pyw")], cwd=APP),
                    root.destroy()))
            else:
                bouton.configure(text="Fermer", state="normal", command=root.destroy)
        root.after(0, f)
    log(f"Setup v{VERSION_SETUP} - dossier : {DEST}")
    threading.Thread(target=installer, args=(log, fin), daemon=True).start()
    root.mainloop()


main()
