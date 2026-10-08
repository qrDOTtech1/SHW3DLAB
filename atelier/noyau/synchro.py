"""SYNCHRONISATION DES PROJETS entre postes (Steven, Hugo...) via le depot GitHub.

data/projets/ est versionne (data/images reste local : le depot est public). A chaque enregistrement (et toutes les 2 min), le poste :
  1. commit ses projets modifies ("projets : <poste>") ;
  2. recupere ceux des autres (pull --rebase) ;
  3. pousse les siens.
Conflit (le meme projet modifie sur deux postes entre deux synchros) : on garde la version la plus RECENTE (champ
"date" du projet) ; l'autre n'est pas perdue, elle reste dans l'historique git. Un conflit hors data/ (code) n'est
jamais resolu automatiquement : on annule et on le signale.
Pour pousser, le compte GitHub du poste doit avoir le droit d'ecriture sur le depot (collaborateur).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

ICI = Path(__file__).resolve().parents[2]
DOSSIERS = ["data/projets"]          # data/images reste LOCAL (photos personnelles : jamais sur le depot public)
NOWIN = 0x08000000 if os.name == "nt" else 0
_verrou = threading.Lock()
_minuteur: threading.Timer | None = None
etat = {"derniere": None, "message": "jamais synchronise", "ok": None, "recus": 0, "envoyes": 0}


def git(*args, timeout=90, env=None):
    try:
        r = subprocess.run(["git", *args], cwd=ICI, capture_output=True, text=True, timeout=timeout, encoding="utf8",
                           errors="replace", creationflags=NOWIN, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def _poste() -> str:
    c, nom = git("config", "user.name")
    return nom if c == 0 and nom else f"SHW 3DLAB {socket.gethostname()}"


def _ident() -> list[str]:
    """Identite de commit : celle du poste, sinon une identite locale (sinon git refuse de committer)."""
    c, _ = git("config", "user.email")
    return [] if c == 0 else ["-c", f"user.name={_poste()}", "-c", f"user.email=shw3dlab@{socket.gethostname()}.local"]


def _date(txt: str) -> float:
    try:
        return float(json.loads(txt).get("date", 0))
    except Exception:
        return 0.0


def _resoudre_conflits() -> bool:
    """Pendant un rebase : chaque fichier en conflit sous data/ -> version la plus recente. False si conflit de code."""
    _, lst = git("diff", "--name-only", "--diff-filter=U")
    for f in [l for l in lst.splitlines() if l.strip()]:
        if not any(f.startswith(d + "/") for d in DOSSIERS):
            return False
        c2, amont = git("show", f":2:{f}")            # en rebase : 2 = version deja sur GitHub, 3 = la notre
        c3, local = git("show", f":3:{f}")
        a_amont, a_local = c2 == 0, c3 == 0
        if not a_amont and not a_local:                 # supprime des deux cotes
            git("rm", "--quiet", f)
            continue
        if a_amont and a_local:
            local_gagne = _date(local) >= _date(amont)   # le plus recent gagne (egalite : le notre)
        else:
            local_gagne = a_local                       # une seule version existe : on la garde
        git("checkout", "--theirs" if local_gagne else "--ours", "--", f)   # en rebase, theirs = notre commit
        git("add", f)
    return True


def synchroniser(pousser=True) -> dict:
    """Commit local des projets + recuperation + envoi. Ne touche jamais au code local modifie (autostash)."""
    with _verrou:
        avant = git("rev-parse", "HEAD")[1]
        git("add", "-A", *DOSSIERS)
        c, diff = git("diff", "--cached", "--name-only")
        envoyes = len([l for l in diff.splitlines() if l.strip()])
        if envoyes:
            git(*_ident(), "commit", "--quiet", "-m", f"projets : {_poste()} ({envoyes} fichier(s))")
        c, out = git("fetch", "--quiet", timeout=60)
        if c:
            return _fin(False, "hors ligne : synchro reportee", 0, 0)
        env = dict(os.environ, GIT_EDITOR="true")
        c, out = git(*_ident(), "rebase", "--autostash", "@{u}", env=env, timeout=120)
        tours = 0
        while c and tours < 50 and ("CONFLICT" in out or "conflit" in out.lower() or "could not apply" in out.lower()):
            if not _resoudre_conflits():
                git("rebase", "--abort")
                return _fin(False, "conflit dans le CODE (pas les projets) : a regler a la main", 0, 0)
            c, out = git(*_ident(), "rebase", "--continue", env=env, timeout=120)
            tours += 1
        if c:
            git("rebase", "--abort")
            return _fin(False, "synchro impossible : " + out[-200:], 0, 0)
        _, n = git("rev-list", "--count", f"{avant}..HEAD", "--", *DOSSIERS)
        recus = max(0, int(n) - (1 if envoyes else 0)) if n.strip().isdigit() else 0
        if pousser:
            _, a_pousser = git("rev-list", "--count", "@{u}..HEAD")
            if a_pousser.strip() not in ("", "0"):
                c, out = git("push", "--quiet", timeout=120)
                if c:
                    msg = ("pas le droit d'ecrire sur le depot GitHub (demander l'acces collaborateur)"
                           if "403" in out or "denied" in out.lower() or "permission" in out.lower()
                           else "envoi impossible : " + out[-160:])
                    return _fin(False, msg, recus, 0)
        return _fin(True, "a jour", recus, envoyes)


def _fin(ok, msg, recus, envoyes):
    etat.update(ok=ok, message=msg, derniere=time.time(), recus=recus, envoyes=envoyes)
    return dict(etat)


def planifier(delai=15.0):
    """Appele a chaque enregistrement : synchro groupee quelques secondes plus tard (pas un push par clic)."""
    global _minuteur
    if _minuteur is not None:
        _minuteur.cancel()
    _minuteur = threading.Timer(delai, synchroniser)
    _minuteur.daemon = True
    _minuteur.start()


def boucle(periode=120.0):
    """Recupere regulierement les projets des autres postes (le serveur l'appelle une fois, au demarrage)."""
    def tourner():
        while True:
            try:
                synchroniser()
            except Exception as e:
                _fin(False, f"erreur synchro : {e}", 0, 0)
            time.sleep(periode)
    threading.Thread(target=tourner, daemon=True, name="synchro-projets").start()
