"""Outils de simulation : test de tenue statique, expert scripte (IK), entrainement PPO,
evaluation + enregistrement de trajectoires rejouables dans l'interface web.

Usage CLI :
  python -m davinbot.sim.train <build_dir> statique
  python -m davinbot.sim.train <build_dir> expert
  python -m davinbot.sim.train <build_dir> ppo 200000
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

from .env import DaVinBimanualEnv, CentralizedEnv, CAM_FOCUS
from .mjcf import build_scene


def ensure_scene(build_dir: Path, progress=lambda m: None) -> Path:
    sim = build_dir / "sim"
    man_t = (build_dir / "manifest.json").stat().st_mtime
    if not (sim / "scene.xml").exists() or (sim / "scene.xml").stat().st_mtime < man_t:
        progress("Generation de la scene MuJoCo (maillages, inerties, actionneurs)...")
        build_scene(build_dir, progress=progress)
    return sim


# ------------------------------------------------------------------ tenue statique
def static_test(build_dir: Path, payload: float, progress=lambda m: None) -> dict:
    """Bras A tendu a l'horizontale avec la charge au bout de l'outil : le couple borne des
    actionneurs suffit-il ? (validation physique du bilan de couple)."""
    sim = ensure_scene(build_dir, progress)
    env = DaVinBimanualEnv(sim, seed=0)
    m, d = env.model, env.data
    res = {}
    poses = {"verticale": [0, 0, 0, 0, 0, 0], "peinture (45/60/60)": [0, 45, 60, 0, 60, 0],
             "horizontale (pire cas)": [0, 90, 0, 0, 0, 0]}
    for name, pose in poses.items():
        env.reset(seed=0)
        q = np.radians(pose)
        d.qpos[env.qadr["A"]] = q
        d.ctrl[env.act["A"]] = q
        mujoco.mj_forward(m, d)
        # charge utile : force externe -m.g appliquee a la pointe de l'outil (corps 6)
        b6 = m.body("A_b6").id
        tip = d.site_xpos[env.tip["A"]].copy()
        F = np.array([0, 0, -payload * 9.81])
        d.xfrc_applied[b6, :3] = F
        d.xfrc_applied[b6, 3:] = np.cross(tip - d.xipos[b6], F)
        for _ in range(1500):
            d.xfrc_applied[b6, 3:] = np.cross(d.site_xpos[env.tip["A"]] - d.xipos[b6], F)
            mujoco.mj_step(m, d)
        d.xfrc_applied[:] = 0
        err = np.degrees(d.qpos[env.qadr["A"]] - q)
        force = d.actuator_force[env.act["A"]]
        sat = np.abs(force) >= 0.98 * env.tmax
        res[name] = {"erreur_deg": err.round(2).tolist(), "couple_Nm": force.round(2).tolist(),
                     "couple_max_Nm": env.tmax.round(2).tolist(), "sature": sat.tolist(),
                     "tient": bool(np.all(np.abs(err) < 3.0) and not np.any(sat))}
        progress(f"Tenue {name} : {'OK' if res[name]['tient'] else 'ECHEC'} (erreur max {np.abs(err).max():.1f} deg)")
    return {"charge_kg": payload, "poses": res}


# ------------------------------------------------------------------ expert scripte (IK)
class Expert:
    """Expert planificateur : pour chaque point de passage, IK cinematique multi-departs
    (sous butees, outil vertical ou axe camera impose) choisissant la solution de COUPLE
    GRAVITAIRE minimal, puis ralliement dans l'espace articulaire sous les limites de vitesse
    du firmware (DSDM compris). Sert de reference et de demonstrateur de faisabilite."""

    def __init__(self, env: DaVinBimanualEnv, seed=0):
        self.e = env
        m = env.model
        self.kd = mujoco.MjData(m)
        self.rng = np.random.default_rng(seed)
        self.dofs = {a: np.array([m.jnt_dofadr[m.joint(f"{a}_{j['name']}").id] for j in env.info["joints"]])
                     for a in "AB"}
        self.b6A = m.body("A_b6").id
        self.plan = {"A": (None, None), "B": (None, None)}
        self.last_fail = {}

    # --------------------------------------------------------------- IK cinematique
    def _solve(self, arm, site, goal, axis_fn, want_axis, q0, starts=40):
        m, kd, e = self.e.model, self.kd, self.e
        qa, dofs, lim = e.qadr[arm], self.dofs[arm], e.lim
        best = None
        seeds = [q0] + [self.rng.uniform(-lim, lim) for _ in range(starts)]
        for s0 in seeds:
            kd.qpos[:] = e.data.qpos
            kd.qpos[qa] = s0
            for _ in range(220):
                mujoco.mj_kinematics(m, kd)
                mujoco.mj_comPos(m, kd)
                p = kd.site_xpos[site] if site >= 0 else kd.cam_xpos[e.cam]
                ax = axis_fn(kd)
                jp = np.zeros((3, m.nv))
                jr = np.zeros((3, m.nv))
                if site >= 0:
                    mujoco.mj_jacSite(m, kd, jp, jr, site)
                else:
                    mujoco.mj_jacSite(m, kd, jp, jr, e.cam_site)
                J = np.vstack([jp[:, dofs], 0.3 * jr[:, dofs]])
                err = np.r_[goal - p, 0.3 * np.cross(ax, want_axis)]
                dq = J.T @ np.linalg.solve(J @ J.T + 0.03 ** 2 * np.eye(6), err)
                kd.qpos[qa] = np.clip(kd.qpos[qa] + np.clip(dq, -0.1, 0.1), -lim + 0.02, lim - 0.02)
                if np.linalg.norm(err) < 1e-4:
                    break
            mujoco.mj_forward(m, kd)
            p = kd.site_xpos[site] if site >= 0 else kd.cam_xpos[e.cam]
            perr = np.linalg.norm(goal - p)
            aerr = 1 - float(np.dot(axis_fn(kd), want_axis))
            if perr > 0.004 or aerr > 0.02:
                continue
            tq = float(np.max(np.abs(kd.qfrc_bias[dofs]) / e.tmax))
            cost = tq + 0.05 * np.linalg.norm(kd.qpos[qa] - e.data.qpos[qa])
            nvalid = locals().get("nvalid", 0) + 1
            if best is None or cost < best[0]:
                best = (cost, kd.qpos[qa].copy())
            if nvalid >= 3:
                break
        return None if best is None else best[1]

    def _goto(self, arm, key, goal, site, axis_fn, want_axis):
        e = self.e
        q = e.data.qpos[e.qadr[arm]]
        k0, sol = self.plan[arm]
        self.tick = getattr(self, "tick", 0) + 1
        retry = sol is None and self.tick - self.last_fail.get(arm, -99) >= 25
        if (k0 is None or np.linalg.norm(np.r_[k0] - np.r_[key]) > 0.005) and                 (sol is not None or k0 is None or retry):
            sol = self._solve(arm, site, goal, axis_fn, want_axis, q)
            self.plan[arm] = (key, sol)
            self.nsolve = getattr(self, "nsolve", 0) + 1
            if sol is None:
                self.last_fail[arm] = self.tick
        if sol is None:
            return np.zeros(6)
        vl = e._speed_limits(arm) * e.dt
        return np.clip(0.5 * (sol - q) / np.maximum(vl, 1e-6), -1, 1)

    def act(self):
        e, d = self.e, self.e.data
        comp = d.xpos[e.comp_body].copy()
        tipA = d.site_xpos[e.tip["A"]].copy()
        down = np.array([0, 0, -1.0])
        axisA = lambda kd: kd.xmat[self.b6A].reshape(3, 3) @ np.array([0, 0, 1.0])  # noqa: E731
        grip = 1.0
        if e.phase == 0:
            above = comp + np.array([0, 0, 0.05])
            reach = np.linalg.norm(tipA - above) < 0.01 or self.plan["A"][0] is not None and                 np.linalg.norm(np.r_[self.plan["A"][0]] - comp) < 0.004
            goal = comp if reach else above
            aA = self._goto("A", goal.round(3), goal, e.tip["A"], axisA, down)
        elif e.phase == 1:
            goal = e.present + (tipA - comp)
            aA = self._goto("A", e.present.round(3), goal, e.tip["A"], axisA, down)
        else:
            above = e.target + np.array([0, 0, 0.04])
            at_above = np.linalg.norm(comp - above) < 0.008
            if self.plan["A"][0] is not None and np.linalg.norm(np.r_[self.plan["A"][0]] - e.target) < 1e-6:
                at_above = True
            tgt = e.target if at_above else above
            goal = tgt + (tipA - comp)
            aA = self._goto("A", tgt.round(3), goal, e.tip["A"], axisA, down)
            if np.linalg.norm(comp - e.target) < 0.004:
                grip = -1.0
        # B : camera a la distance de mise au point, axe optique vers le composant
        if e.phase >= 1:
            look_from = comp + np.array([0.05, 0.0, 0.05]) / np.sqrt(2) * CAM_FOCUS / 0.05
            want = (comp - look_from) / np.linalg.norm(comp - look_from)
            camax = lambda kd: -kd.cam_xmat[e.cam].reshape(3, 3)[:, 2]  # noqa: E731
            aB = self._goto("B", comp.round(2), look_from, -1, camax, want)
        else:
            aB = np.zeros(6)
        return {"bras_A": np.r_[aA, grip], "bras_B": aB}


def run_episode(env: DaVinBimanualEnv, policy, seed=0, record=True) -> dict:
    obs, _ = env.reset(seed=seed)
    traj, R, info = [], 0.0, {}
    for t in range(env.max_steps):
        acts = policy(obs)
        obs, rew, term, trunc, infos = env.step(acts)
        R += rew["bras_A"] + rew["bras_B"]
        info = infos["bras_A"]
        if record and t % 2 == 0:
            traj.append(env.state_snapshot())
        if term["bras_A"] or trunc["bras_A"]:
            break
    traj.append(env.state_snapshot())
    return {"return": round(R, 2), "steps": t + 1, "phase_finale": env.phase, "succes": env.phase == 3,
            "info": {k: (round(float(v), 3) if isinstance(v, (float, np.floating)) else v) for k, v in info.items()},
            "traj": traj, "dt": env.dt * 2}


def expert_run(build_dir: Path, progress=lambda m: None) -> dict:
    sim = ensure_scene(build_dir, progress)
    env = DaVinBimanualEnv(sim, max_steps=900, seed=0)
    ex = Expert(env)
    res = run_episode(env, lambda o: ex.act(), seed=0)
    (sim / "traj_expert.json").write_text(json.dumps(res), encoding="utf8")
    progress(f"Expert IK : phase finale {res['phase_finale']} / 3, succes={res['succes']}, {res['steps']} pas")
    return {k: v for k, v in res.items() if k != "traj"}


# ------------------------------------------------------------------ PPO
def train_ppo(build_dir: Path, steps: int, progress=lambda m, f=None: None) -> dict:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import DummyVecEnv, VecMonitor

    sim = ensure_scene(build_dir, lambda m: progress(m))
    curve = []

    class CB(BaseCallback):
        def _on_step(self):
            for inf in self.locals.get("infos", []):
                if "episode" in inf:
                    curve.append({"t": int(self.num_timesteps), "r": round(float(inf["episode"]["r"]), 2),
                                  "phase": int(inf.get("phase", 0))})
            if self.n_calls % 2000 == 0:
                last = curve[-20:]
                mr = np.mean([c["r"] for c in last]) if last else 0
                mp = np.mean([c["phase"] for c in last]) if last else 0
                progress(f"PPO {self.num_timesteps}/{steps} pas - recompense {mr:.1f} - phase moy. {mp:.2f}",
                         self.num_timesteps / steps)
                (sim / "ppo_curve.json").write_text(json.dumps(curve), encoding="utf8")
            return True

    venv = VecMonitor(DummyVecEnv([lambda i=i: CentralizedEnv(sim, 400, seed=i) for i in range(4)]))
    path = sim / "ppo_bimanuel.zip"
    if path.exists():
        model = PPO.load(path, env=venv, device="cpu")
        progress("Reprise du modele existant.")
    else:
        model = PPO("MlpPolicy", venv, n_steps=512, batch_size=512, learning_rate=3e-4, gamma=0.99,
                    gae_lambda=0.95, ent_coef=0.0, policy_kwargs={"net_arch": [256, 256]}, verbose=0,
                    device="cpu")
    t0 = time.time()
    model.learn(total_timesteps=steps, callback=CB(), reset_num_timesteps=False)
    model.save(path)
    (sim / "ppo_curve.json").write_text(json.dumps(curve), encoding="utf8")
    env = DaVinBimanualEnv(sim, 400, seed=123)

    def pol(o):
        x = np.concatenate([o["bras_A"], o["bras_B"]]) if o else np.zeros(72)
        a, _ = model.predict(x, deterministic=True)
        return {"bras_A": a[:7], "bras_B": a[7:]}
    res = run_episode(env, pol, seed=123)
    (sim / "traj_ppo.json").write_text(json.dumps(res), encoding="utf8")
    out = {k: v for k, v in res.items() if k != "traj"}
    out.update(pas_total=int(model.num_timesteps), duree_s=round(time.time() - t0, 1))
    progress(f"PPO termine : phase finale {res['phase_finale']}/3, retour {res['return']}", 1.0)
    return out


if __name__ == "__main__":
    bd = Path(sys.argv[1])
    cmd = sys.argv[2]
    pr = lambda m, f=None: print(m, flush=True)  # noqa: E731
    if cmd == "statique":
        print(json.dumps(static_test(bd, 1.5, pr), indent=1))
    elif cmd == "expert":
        print(expert_run(bd, pr))
    elif cmd == "ppo":
        print(train_ppo(bd, int(sys.argv[3]), pr))
