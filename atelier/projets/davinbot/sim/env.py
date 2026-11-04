"""Environnement de coordination bimanuelle DaVinBot V2 (MuJoCo).

Tache (3 phases, recompense d'equipe + termes individuels) :
  0. PRISE      : le bras A amene sa pointe d'outil sur le composant (ESP32) et le saisit
                  (prise abstraite par contrainte de soudure : a remplacer par la DaVinHand).
  1. PRESENTATION / INSPECTION : A presente le composant au point d'inspection ; B oriente sa
                  camera de poignet (axe optique -> composant, distance de mise au point) et
                  tient la vue N pas (validation "OpenCV").
  2. INSERTION  : A pose le composant sur la cible de la breadboard, sans collision.
Contraintes physiques reelles : couples bornes au couple disponible du generateur, DSDM en
mode Vitesse seulement si le couple gravitaire de l'axe est sous la limite de M2
(sinon vitesse limitee au mode Force), inertie reflechie et frottement des reducteurs.

API :
  * DaVinBimanualEnv : pettingzoo.ParallelEnv (agents "bras_A", "bras_B")
  * CentralizedEnv   : gymnasium.Env (les deux bras pilotes par une politique unique)
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

OBS_DIM = 36
FRAME_SKIP = 10                 # 10 x 2 ms = 50 Hz de commande
PRESENT_HOLD = 20               # pas de vue stable exigee pour valider l'inspection
CAM_FOCUS = 0.07                # distance de mise au point de l'endoscope (m)


def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _quat_conj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


class DaVinBimanualEnv(ParallelEnv):
    metadata = {"name": "davinbot_bimanuel_v0", "render_modes": ["rgb_array"]}

    def __init__(self, scene_dir: str | Path, max_steps: int = 400, seed: int | None = None,
                 render_mode: str | None = None):
        self.dir = Path(scene_dir)
        self.info = json.loads((self.dir / "scene_info.json").read_text(encoding="utf8"))
        self.model = mujoco.MjModel.from_xml_path(str(self.dir / "scene.xml"))
        self.data = mujoco.MjData(self.model)
        self.max_steps = max_steps
        self.render_mode = render_mode
        self.rng = np.random.default_rng(seed)
        self.possible_agents = ["bras_A", "bras_B"]
        m = self.model
        jn = [j["name"] for j in self.info["joints"]]
        self.qadr = {a: np.array([m.jnt_qposadr[m.joint(f"{a}_{n}").id] for n in jn]) for a in "AB"}
        self.dadr = {a: np.array([m.jnt_dofadr[m.joint(f"{a}_{n}").id] for n in jn]) for a in "AB"}
        self.act = {a: np.array([m.actuator(f"{a}_{n}").id for n in jn]) for a in "AB"}
        self.tip = {a: m.site(f"{a}_tip").id for a in "AB"}
        self.cam_site = m.site("B_cam_site").id
        self.cam = m.camera("B_cam").id
        self.comp_body = m.body("composant").id
        self.comp_site = m.site("composant_c").id
        self.weld = m.equality("prise_A").id
        self.b6 = m.body("A_b6").id
        self.comp_qadr = m.jnt_qposadr[m.joint("composant").id]
        self.tmax = np.array([j["tmax"] for j in self.info["joints"]])
        self.t_fast = np.array([j["t_fast"] for j in self.info["joints"]])
        self.vmax = np.array([j["vmax"] for j in self.info["joints"]])
        self.vmax_fast = np.array([j["vmax_fast"] for j in self.info["joints"]])
        self.lim = np.array([j["limit"] for j in self.info["joints"]])
        self.dsdm = np.array([j["dsdm"] for j in self.info["joints"]])
        self.dt = m.opt.timestep * FRAME_SKIP
        self.kp = np.array([m.actuator_gainprm[m.actuator(f"A_{n}").id, 0] for n in jn])
        self.target = np.array(self.info["target"])
        self.present = np.array(self.info["present"])
        arm_geoms = {a: set() for a in "AB"}
        for g in range(m.ngeom):
            name = m.body(m.geom_bodyid[g]).name
            if name[:2] in ("A_", "B_") and m.geom_contype[g]:
                arm_geoms[name[0]].add(g)
        self.arm_geoms = arm_geoms
        self.table = m.geom("table").id
        self._renderer = None

    # ------------------------------------------------------------ espaces
    @functools.lru_cache(maxsize=None)
    def observation_space(self, agent):
        return spaces.Box(-np.inf, np.inf, (OBS_DIM,), np.float32)

    @functools.lru_cache(maxsize=None)
    def action_space(self, agent):
        return spaces.Box(-1.0, 1.0, (7 if agent == "bras_A" else 6,), np.float32)

    # ------------------------------------------------------------ cycle
    def reset(self, seed=None, options=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        m, d = self.model, self.data
        mujoco.mj_resetData(m, d)
        self.qref = {}
        m.eq_active0[self.weld] = 0
        d.eq_active[self.weld] = 0
        homes = {"A": np.radians(self.info.get("home_deg", [0, 20, 60, 0, 60, 0])),
                 "B": np.radians(self.info.get("home_deg_B", self.info.get("home_deg", [0, 20, 60, 0, 60, 0])))}
        for a in "AB":
            q = homes[a] + self.rng.normal(0, 0.03, 6)
            d.qpos[self.qadr[a]] = q
            d.ctrl[self.act[a]] = q
            self.qref[a] = q.copy()
        c0 = np.array(self.info["comp0"]) + np.r_[self.rng.uniform(-0.02, 0.02, 2), 0]
        d.qpos[self.comp_qadr:self.comp_qadr + 3] = c0
        d.qpos[self.comp_qadr + 3:self.comp_qadr + 7] = [1, 0, 0, 0]
        mujoco.mj_forward(m, d)
        self.agents = list(self.possible_agents)
        self.steps, self.phase, self.hold, self.grasped = 0, 0, 0, False
        self.prev = self._potential()
        obs = {ag: self._obs(ag) for ag in self.agents}
        return obs, {ag: {"phase": 0} for ag in self.agents}

    def _speed_limits(self, a):
        """DSDM : vitesse du mode Vitesse autorisee seulement si |gravite| < couple de M2."""
        bias = np.abs(self.data.qfrc_bias[self.dadr[a]])
        fast = self.dsdm & (bias < 0.8 * self.t_fast)
        return np.where(fast, self.vmax_fast, self.vmax)

    def step(self, actions):
        m, d = self.model, self.data
        for a, ag in (("A", "bras_A"), ("B", "bras_B")):
            u = np.clip(np.asarray(actions.get(ag, np.zeros(7)), float), -1, 1)
            vl = self._speed_limits(a)
            tgt = self.qref[a] + u[:6] * vl * self.dt
            # anti-windup : la consigne ne s'eloigne pas de plus de 4 deg de la position reelle
            q = d.qpos[self.qadr[a]]
            self.qref[a] = np.clip(np.clip(tgt, q - 0.07, q + 0.07), -self.lim, self.lim)
            # boucle fermee MKS (action integrale) : anticipation du couple de gravite
            ff = d.qfrc_bias[self.dadr[a]] / self.kp
            d.ctrl[self.act[a]] = np.clip(self.qref[a] + ff, -self.lim, self.lim)
        grip = float(np.asarray(actions.get("bras_A", np.zeros(7)))[6])
        self._grip_logic(grip)
        mujoco.mj_step(m, d, FRAME_SKIP)
        self.steps += 1
        r_team, r_ind, info = self._reward(grip)
        done = self.phase == 3
        trunc = self.steps >= self.max_steps
        obs = {ag: self._obs(ag) for ag in self.agents}
        rew = {"bras_A": r_team + r_ind["A"], "bras_B": r_team + r_ind["B"]}
        term = {ag: done for ag in self.agents}
        tru = {ag: trunc for ag in self.agents}
        infos = {ag: dict(info) for ag in self.agents}
        if done or trunc:
            self.agents = []
        return obs, rew, term, tru, infos

    # ------------------------------------------------------------ prise (contrainte de soudure)
    def _grip_logic(self, grip):
        m, d = self.model, self.data
        tipA = d.site_xpos[self.tip["A"]]
        comp = d.xpos[self.comp_body]
        if not self.grasped and grip > 0 and np.linalg.norm(tipA - comp) < 0.015 and self.phase == 0:
            # pose relative courante composant / corps 6 -> contrainte active sans saut
            p6, q6 = d.xpos[self.b6], d.xquat[self.b6]
            pc, qc = d.xpos[self.comp_body], d.xquat[self.comp_body]
            R6 = d.xmat[self.b6].reshape(3, 3)
            m.eq_data[self.weld, 3:6] = R6.T @ (pc - p6)
            m.eq_data[self.weld, 6:10] = _quat_mul(_quat_conj(q6), qc)
            d.eq_active[self.weld] = 1
            self.grasped = True
        elif self.grasped and grip < -0.5 and self.phase == 2:
            d.eq_active[self.weld] = 0
            self.grasped = False

    # ------------------------------------------------------------ recompenses
    def _cam_metrics(self):
        d = self.data
        cam_p = d.cam_xpos[self.cam]
        cam_R = d.cam_xmat[self.cam].reshape(3, 3)
        look = -cam_R[:, 2]
        v = d.xpos[self.comp_body] - cam_p
        dist = np.linalg.norm(v)
        cosang = float(np.dot(look, v / max(dist, 1e-6)))
        return cosang, dist

    def _potential(self):
        d = self.data
        comp = d.xpos[self.comp_body]
        tipA = d.site_xpos[self.tip["A"]]
        if self.phase == 0:
            return -np.linalg.norm(tipA - comp)
        if self.phase == 1:
            cos, dist = self._cam_metrics()
            return -np.linalg.norm(comp - self.present) + 0.1 * cos - 0.5 * abs(dist - CAM_FOCUS)
        return -np.linalg.norm(comp - self.target)

    def _collisions(self):
        d = self.data
        inter, table = 0, 0
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = c.geom1, c.geom2
            a1 = "A" if g1 in self.arm_geoms["A"] else "B" if g1 in self.arm_geoms["B"] else None
            a2 = "A" if g2 in self.arm_geoms["A"] else "B" if g2 in self.arm_geoms["B"] else None
            if a1 and a2 and a1 != a2:
                inter += 1
            elif (a1 or a2) and self.table in (g1, g2):
                table += 1
        return inter, table

    def _reward(self, grip):
        d = self.data
        pot = self._potential()
        r = 10.0 * (pot - self.prev)                 # mise en forme par potentiel
        info = {"phase": self.phase}
        comp = d.xpos[self.comp_body]
        if self.phase == 0 and self.grasped:
            r += 2.0
            self.phase = 1
        elif self.phase == 1:
            cos, dist = self._cam_metrics()
            ok = np.linalg.norm(comp - self.present) < 0.04 and cos > 0.95 and abs(dist - CAM_FOCUS) < 0.03
            self.hold = self.hold + 1 if ok else 0
            info.update(cam_cos=cos, cam_dist=dist)
            if self.hold >= PRESENT_HOLD:
                r += 5.0
                self.phase = 2
        elif self.phase == 2:
            err = np.linalg.norm(comp - self.target)
            if err < 0.004 and not self.grasped:
                r += 20.0
                self.phase = 3
        if self.phase != info["phase"]:
            pot = self._potential()
        self.prev = pot
        inter, table = self._collisions()
        r -= 1.0 * inter + 0.3 * table
        sat = {a: float(np.mean(np.abs(d.actuator_force[self.act[a]]) > 0.98 * self.tmax)) for a in "AB"}
        info.update(collisions=inter, table=table, saturation_A=sat["A"], saturation_B=sat["B"])
        ind = {"A": -0.05 * sat["A"], "B": -0.05 * sat["B"]}
        if self.phase == 1:
            cos, _ = self._cam_metrics()
            ind["B"] += 0.02 * cos
        return r - 0.002, ind, info

    # ------------------------------------------------------------ observations
    def _obs(self, ag):
        d = self.data
        a = ag[-1]
        o = a == "A" and "B" or "A"
        comp = d.xpos[self.comp_body]
        tip = d.site_xpos[self.tip[a]]
        cos, dist = self._cam_metrics()
        ph = np.zeros(4)
        ph[min(self.phase, 3)] = 1
        v = np.concatenate([
            d.qpos[self.qadr[a]], 0.1 * d.qvel[self.dadr[a]], tip, comp, comp - tip,
            self.target - comp, d.site_xpos[self.tip[o]], ph, [float(self.grasped)], [cos, dist],
        ])
        out = np.zeros(OBS_DIM, np.float32)
        out[:len(v)] = v[:OBS_DIM]
        return out

    def state_snapshot(self):
        d = self.data
        return {"A": np.degrees(d.qpos[self.qadr["A"]]).round(2).tolist(),
                "B": np.degrees(d.qpos[self.qadr["B"]]).round(2).tolist(),
                "comp": (d.xpos[self.comp_body] * 1000).round(1).tolist(), "phase": self.phase}

    def render(self):
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, 360, 480)
        self._renderer.update_scene(self.data, camera=self.cam)
        return self._renderer.render()

    def close(self):
        if self._renderer is not None:
            self._renderer.close()


class CentralizedEnv(gym.Env):
    """Les deux bras sous une politique unique (coordination centralisee)."""

    metadata = {"render_modes": ["rgb_array"]}

    def __init__(self, scene_dir, max_steps=400, seed=None):
        self.pz = DaVinBimanualEnv(scene_dir, max_steps, seed)
        self.observation_space = spaces.Box(-np.inf, np.inf, (2 * OBS_DIM,), np.float32)
        self.action_space = spaces.Box(-1.0, 1.0, (13,), np.float32)

    def reset(self, seed=None, options=None):
        obs, info = self.pz.reset(seed=seed)
        return np.concatenate([obs["bras_A"], obs["bras_B"]]), info["bras_A"]

    def step(self, action):
        acts = {"bras_A": action[:7], "bras_B": action[7:]}
        obs, rew, term, trunc, info = self.pz.step(acts)
        o = np.concatenate([obs["bras_A"], obs["bras_B"]])
        r = 0.5 * (rew["bras_A"] + rew["bras_B"])
        return o, float(r), bool(term["bras_A"]), bool(trunc["bras_A"]), info["bras_A"]
