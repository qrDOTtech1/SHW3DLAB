"""Entrainement du DaVinBot Base en simulation : MuJoCo avec les vraies masses, le vrai couple et les 3 capteurs a ultrasons.

Tache : amener le bout du bras sur une cible, en lisant positions, vitesses et distances ultrason (comme le vrai bras).
  python -m atelier.projets.davinbot_sim entrainer 300000
  python -m atelier.projets.davinbot_sim evaluer
Le modele reste une simulation : jeux mecaniques et frottements reels devront etre mesures sur le bras.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import gymnasium as gym
import mujoco
import numpy as np

ICI = Path(__file__).resolve().parents[2]
PACK = ICI / "data" / "bases" / "davinbot_base_2a7112407d.zip"
GARDE = {"BASE", "J1", "TOURELLE", "J2", "BRAS", "J3", "COUDE"}
LIMITES = {"J1": 170, "J2": 110, "J3": 140}
SORTIE = Path("D:/SHW-IA/davinbot") if Path("D:/").exists() else ICI / "sortie" / "ia"
# capteur : corps porteur, position (m, repere monde pose zero), direction de mesure
ULTRASONS = [(0, (0.106, 0, 0.044)), (1, (0.046, 0, 0.230)), (3, (0.052, -0.013, 0.520))]
TIP = (0, -0.00265, 0.5701)


def scene() -> str:
    m = json.loads(zipfile.ZipFile(PACK).read("manifest.json"))
    parts = [q for q in m["parts"] if q["group"] in GARDE and q["kind"] != "keepout" and "capot" not in q["id"]]
    J = {j["name"]: j for j in m["joints"]}
    org = {1: np.array(J["J1"]["origin"]) / 1000, 2: np.array(J["J2"]["origin"]) / 1000, 3: np.array(J["J3"]["origin"]) / 1000}
    ax = {1: J["J1"]["axis"], 2: J["J2"]["axis"], 3: J["J3"]["axis"]}
    cpl = {i: m["torque"][f"J{i}"]["couple_dispo_Nm"] for i in (1, 2, 3)}

    def inertie(b, o):
        P = [q for q in parts if q["body"] == b]
        ma = sum(q["masse_g"] for q in P) / 1000
        c = sum(np.array(q["com"]) * q["masse_g"] for q in P) / 1000 / max(ma, 1e-6) / 1000
        return ma, c - o

    def corps(b, parent_o):
        o = org[b]
        ma, c = inertie(b, o)
        rel = o - parent_o
        cap = (c[2] if abs(c[2]) > 0.03 else 0.05)
        cap_g = f'<geom type="capsule" fromto="0 0 0 {c[0] * 2:.3f} {c[1] * 2:.3f} {cap * 2:.3f}" size="0.03" mass="0" contype="0" conaffinity="0" rgba=".85 .87 .9 1"/>'
        cap_c = "".join(f'<site name="us{i}" pos="{p[0] - o[0]:.4f} {p[1] - o[1]:.4f} {p[2] - o[2]:.4f}" size="0.008" rgba="1 .4 0 1"/>' for i, (bb, p) in enumerate(ULTRASONS) if bb == b)
        fin = f'<site name="tip" pos="{TIP[0] - o[0]:.4f} {TIP[1] - o[1]:.4f} {TIP[2] - o[2]:.4f}" size="0.012" rgba="0 1 0 1"/>' if b == 3 else corps(b + 1, o)
        lim = LIMITES[f"J{b}"]
        return f'''<body name="b{b}" pos="{rel[0]:.4f} {rel[1]:.4f} {rel[2]:.4f}">
          <joint name="j{b}" axis="{ax[b][0]} {ax[b][1]} {ax[b][2]}" range="{-lim} {lim}" damping="1.5" frictionloss="0.15" armature="{8.2e-6 * m['torque'][f'J{b}'].get('rapport', 30) ** 2:.5f}"/>
          <inertial pos="{c[0]:.4f} {c[1]:.4f} {c[2]:.4f}" mass="{max(ma, 0.02):.3f}" diaginertia="{max(ma, 0.02) * 0.01:.5f} {max(ma, 0.02) * 0.01:.5f} {max(ma, 0.02) * 0.004:.5f}"/>
          {cap_g}{cap_c}{fin}</body>'''
    actionneurs = "".join(f'<position name="a{i}" joint="j{i}" kp="{cpl[i] * 25:.1f}" forcerange="{-cpl[i]} {cpl[i]}"/>' for i in (1, 2, 3))
    us0 = "".join(f'<site name="us{i}" pos="{p[0]} {p[1]} {p[2]}" size="0.008" rgba="1 .4 0 1"/>' for i, (bb, p) in enumerate(ULTRASONS) if bb == 0)
    return f'''<mujoco model="davinbot_base"><compiler angle="degree"/><option timestep="0.002"/>
      <worldbody><light pos="0 -1 2"/><geom name="sol" type="plane" size="2 2 .1" rgba=".3 .32 .36 1"/>
        <geom name="socle" type="cylinder" pos="0 0 .044" size=".1 .044" rgba=".7 .72 .76 1"/>{us0}
        <body name="obstacle" mocap="true" pos=".35 0 .1"><geom name="obst" type="box" size=".05 .05 .1" rgba=".9 .5 .2 1" contype="0" conaffinity="0"/></body>
        <body name="cible" mocap="true" pos=".3 0 .3"><geom type="sphere" size=".015" rgba="0 1 .4 .8" contype="0" conaffinity="0"/></body>
        {corps(1, np.zeros(3))}</worldbody><actuator>{actionneurs}</actuator></mujoco>'''


class Atteindre(gym.Env):
    PAS = 25                # 20 Hz
    VITESSE = np.radians([100, 100, 150])

    def __init__(self, duree=100):
        self.m = mujoco.MjModel.from_xml_string(scene()); self.d = mujoco.MjData(self.m)
        self.duree = duree
        self.lim = self.m.jnt_range.copy()
        self.tip = self.m.site("tip").id
        self.us = [self.m.site(f"us{i}").id for i in range(3)]
        self.cible = self.m.body("cible").mocapid[0]; self.obst = self.m.body("obstacle").mocapid[0]
        self.action_space = gym.spaces.Box(-1, 1, (3,), np.float32)
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (18,), np.float32)

    def _ultrasons(self):
        out = []
        gid = np.array([-1], dtype=np.int32)
        for s in self.us:
            p = self.d.site_xpos[s]; n = self.d.site_xmat[s].reshape(3, 3)[:, 0]
            r = mujoco.mj_ray(self.m, self.d, p, n, None, 1, -1, gid)
            r = 4.0 if r < 0 or r > 4.0 else r      # HC-SR04 : portee 4 m
            out.append(r)
        return np.array(out)

    def _obs(self):
        t = self.d.site_xpos[self.tip]; c = self.d.mocap_pos[self.cible]
        return np.r_[self.d.qpos / np.pi, self.d.qvel / 3, self.ctrl / np.pi, c, (c - t) * 5, self._ultrasons() / 4].astype(np.float32)   # consigne incluse : sans elle l'etat est incomplet

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        mujoco.mj_resetData(self.m, self.d)
        r = self.np_random
        q = r.uniform(np.radians([-120, -60, -90]), np.radians([120, 60, 90]))   # cible atteignable : tiree dans l'espace du bras
        self.q_cible = q.copy(); self.d.qpos[:] = q; mujoco.mj_forward(self.m, self.d)
        self.d.mocap_pos[self.cible] = self.d.site_xpos[self.tip].copy()
        self.d.qpos[:] = r.uniform(-0.3, 0.3, 3); self.d.qvel[:] = 0
        self.d.mocap_pos[self.obst] = [r.uniform(.25, .6) * r.choice([-1, 1]), r.uniform(-.4, .4), .1]
        self.ctrl = self.d.qpos.copy(); self.d.ctrl[:] = self.ctrl
        mujoco.mj_forward(self.m, self.d)
        self.n = 0; self.av = np.linalg.norm(self.d.site_xpos[self.tip] - self.d.mocap_pos[self.cible])
        return self._obs(), {}

    def step(self, a):
        a = np.clip(a, -1, 1)
        self.ctrl = np.clip(self.ctrl + a * self.VITESSE * self.PAS * self.m.opt.timestep, np.radians(self.lim[:, 0]) if self.lim.max() > 7 else self.lim[:, 0], np.radians(self.lim[:, 1]) if self.lim.max() > 7 else self.lim[:, 1])
        self.d.ctrl[:] = self.ctrl
        mujoco.mj_step(self.m, self.d, self.PAS)
        e = np.linalg.norm(self.d.site_xpos[self.tip] - self.d.mocap_pos[self.cible])
        rec = -e * 3 + (self.av - e) * 10 + (1.0 if e < 0.01 else 0.3 if e < 0.03 else 0) - 0.002 * np.square(a).sum() - 0.002 * np.square(self.d.qvel).sum()
        self.av = e; self.n += 1
        return self._obs(), float(rec), False, self.n >= self.duree, {"erreur_mm": e * 1000}


def evaluer(chemin=None, n=100):
    from stable_baselines3 import SAC
    pol = SAC.load(chemin or SORTIE / "politique_base", device="cpu") if chemin != "hasard" else None
    env = Atteindre(); E = []
    for k in range(n):
        o, _ = env.reset(seed=1000 + k)
        for _ in range(env.duree):
            a = env.action_space.sample() if pol is None else pol.predict(o, deterministic=True)[0]
            o, _, _, t, i = env.step(a)
        E.append(i["erreur_mm"])
    return {"erreur_mediane_mm": round(float(np.median(E)), 1), "p90_mm": round(float(np.percentile(E, 90)), 1), "sous_10mm_pct": round(float(np.mean(np.array(E) < 10) * 100))}


def entrainer(pas=300000):
    from stable_baselines3 import SAC
    SORTIE.mkdir(parents=True, exist_ok=True)
    pol = SAC("MlpPolicy", Atteindre(), device="cpu", batch_size=512, learning_starts=3000, gamma=0.98, buffer_size=300000, policy_kwargs={"net_arch": [256, 256]}, verbose=0)
    tranche = 40000; fait = 0
    while fait < pas:
        pol.learn(tranche, reset_num_timesteps=False); fait += tranche
        pol.save(SORTIE / "politique_base")
        print(fait, evaluer(n=30), flush=True)
    print("FINI", evaluer(), flush=True)


def physique(n=50):
    """Limite physique : consigne parfaite directement sur l'angle cible (sans IA)."""
    env = Atteindre(); E = []
    for k in range(n):
        env.reset(seed=2000 + k); env.ctrl = env.q_cible.copy(); env.d.ctrl[:] = env.ctrl
        for _ in range(env.duree): mujoco.mj_step(env.m, env.d, env.PAS)
        E.append(np.linalg.norm(env.d.site_xpos[env.tip] - env.d.mocap_pos[env.cible]) * 1000)
    return {"mediane_mm": round(float(np.median(E)), 1), "max_mm": round(float(np.max(E)), 1)}


if __name__ == "__main__":
    if sys.argv[1] == "physique":
        print(physique())
    elif sys.argv[1] == "entrainer":
        print("hasard", evaluer("hasard", 30), flush=True)
        entrainer(int(sys.argv[2]) if len(sys.argv) > 2 else 300000)
    else:
        print(evaluer())
