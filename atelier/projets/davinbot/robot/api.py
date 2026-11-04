"""API robot commune : les MODES (changement d'outil, prise, peinture...) ne parlent qu'a cette
interface. Le backend de simulation (MuJoCo) l'implemente aujourd'hui ; un backend materiel
(ESP32 + MKS SERVO42C + servo de verrou + bus pogo) l'implementera a l'identique.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class RobotAPI(ABC):
    log: list

    # --- mouvement (TCP = point de travail de l'outil monte, ou face de la tete si aucun)
    @abstractmethod
    def move_to(self, pos, z_axis, x_axis=None, speed: float = 1.0) -> bool:
        """Deplacement articulaire rapide vers une pose de l'outil (IK sous butees)."""

    @abstractmethod
    def move_linear(self, pos, z_axis, x_axis=None, dist_step: float = 0.004) -> bool:
        """Deplacement rectiligne du TCP (approches, plongees, glissements)."""

    @abstractmethod
    def tcp(self) -> np.ndarray: ...

    @abstractmethod
    def transit(self, q, speed: float = 1.0) -> bool:
        """Deplacement articulaire planifie sans collision (points de passage si besoin)."""

    @abstractmethod
    def move_to_chain(self, pts, z_axis, x_axis=None, speed: float = 1.0) -> bool:
        """Va au premier point dans une configuration qui permet de suivre tout le trajet lineaire."""

    @abstractmethod
    def move_path(self, q, speed: float = 1.0) -> bool:
        """Deplacement articulaire court verifie sans collision."""

    @abstractmethod
    def path_free(self, qa, qb) -> bool: ...

    # --- changeur d'outil
    @abstractmethod
    def lock(self) -> dict:
        """Verrouille la bague (servo 90 deg) ; renvoie {'ok', 'erreur_mm', 'angle_deg'}."""

    @abstractmethod
    def unlock(self) -> None: ...

    @abstractmethod
    def read_tool_id(self) -> dict | None:
        """Lit l'EEPROM I2C de l'outil via les pogo pins (None si aucun outil)."""

    @abstractmethod
    def dock(self, slot: str) -> None:
        """Remise en prise de l'outil dans la fourche du rack."""

    @abstractmethod
    def undock(self, slot: str) -> None: ...

    # --- main
    @abstractmethod
    def grip(self, targets: dict, duration: float = 0.8) -> None:
        """Consignes de la main : {'index': 0..1, ..., 'pouce': 0..1, 'opp': 0..1, 'ecart': -1..1}."""

    @abstractmethod
    def object_pos(self, name: str) -> np.ndarray: ...

    @abstractmethod
    def touching(self, obj: str) -> set:
        """Parties de la main en contact avec l'objet (capteurs de pulpe / courant moteur)."""

    @abstractmethod
    def wait(self, seconds: float) -> None: ...

    def allow_touch(self, *names):
        """Objets que le bras a le droit de toucher (sinon : obstacles pour la planification)."""

    def say(self, msg: str):
        self.log.append(msg)
