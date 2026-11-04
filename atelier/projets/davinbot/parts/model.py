"""Modele de piece commun a tout le generateur."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# couleurs d'affichage par categorie
COLORS = {
    "structure": "#d9dde3", "housing": "#8fa3b8", "gear": "#e8a33d", "disc": "#d9573b",
    "shaft": "#b07ad9", "output": "#4fb286", "cap": "#6f86a0", "tool": "#e5c04a",
    "sensor": "#43a6c6", "motor": "#3a3d42", "bearing": "#a8adb3", "pin": "#c9ccd1",
    "keepout": "#ff3b6b", "electronics": "#2f7d4a", "screw": "#7d8288",
}


@dataclass
class Part:
    id: str
    name: str
    group: str                 # sous-ensemble (J1, J2, base, outil...)
    body: int                  # corps cinematique : 0 = socle ... 6 = bride outil
    shape: object              # cq.Workplane / cq.Shape dans le repere local
    kind: str = "print"        # print | vitamin | keepout
    category: str = "structure"
    qty: int = 1
    T: np.ndarray = field(default_factory=lambda: np.eye(4))   # local -> monde (pose zero)
    notes: str = ""
    anim: dict | None = None   # animation interne du reducteur (repere local)
    material: str = "PETG"
    infill: str = ""
    print_up: tuple | None = None   # axe local a orienter vers +Z pour l'impression
    meta: dict = field(default_factory=dict)

    @property
    def color(self) -> str:
        return COLORS.get(self.category, "#cccccc")


@dataclass
class Vitamin:
    """Element du commerce (nomenclature)."""
    ref: str
    desc: str
    qty: int
    group: str
