"""SHW3DLAB_Setup.exe (amorce) : telecharge la DERNIERE version du script d'installation depuis GitHub et
l'execute. Le setup evolue donc avec le depot, sans recompiler l'exe. Hors ligne : copie integree."""
import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/qrDOTtech1/SHW3DLAB/main/setup/installer.py"


def code():
    try:
        with urllib.request.urlopen(URL, timeout=15) as r:
            return r.read().decode("utf8")
    except Exception:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        return (base / "installer.py").read_text(encoding="utf8")


exec(compile(code(), "installer.py", "exec"), {"__name__": "__main__"})
