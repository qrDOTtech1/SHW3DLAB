"""Demonstration a UN bras : vitesse (DSDM), precision, force - mesurees dans la physique.

Epreuves :
  1. VITESSE   : grand deplacement repos -> toile ; DSDM en mode Vitesse quand la gravite le permet.
  2. PRECISION : la pointe de l'outil trace un cercle (r = 40 mm) a 2 mm au-dessus de la toile ;
                 erreur de suivi mesuree en continu (RMS / max, mm).
  3. FORCE     : l'outil appuie sur la toile posee sur les 4 RFP602 ; regulation d'effort
                 (admittance) jusqu'a la consigne, maintien, puis TRIANGULATION : le point d'appui
                 est recalcule a partir des 4 capteurs et compare a la position reelle de l'outil.
Commande identique au firmware : consignes articulaires limitees en vitesse (DSDM compris),
asservissement MKS (boucle fermee + anticipation de gravite), couples bornes au couple
disponible calcule par le generateur.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import mujoco
import numpy as np

from .mjcf import build_scene

DT_CTRL = 0.02


class ArmDemo:
    def __init__(self, build_dir: Path, force_target: float = 10.0, progress=lambda m: None):
        sim = build_dir / "sim"
        xml, inf = sim / "demo1.xml", sim / "demo1_info.json"
        man_t = (build_dir / "manifest.json").stat().st_mtime
        if not xml.exists() or xml.stat().st_mtime < man_t:
            progress("Generation de la scene 1 bras (maillages, inerties, couples reels)...")
            build_scene(build_dir, progress=progress, arms=("A",), scene_name="demo1")
        self.info = json.loads(inf.read_text(encoding="utf8"))
        self.m = mujoco.MjModel.from_xml_path(str(xml))
        self.d = mujoco.MjData(self.m)
        self.kd = mujoco.MjData(self.m)
        m = self.m
        jn = [j["name"] for j in self.info["joints"]]
        self.qa = np.array([m.jnt_qposadr[m.joint(f"A_{n}").id] for n in jn])
        self.da = np.array([m.jnt_dofadr[m.joint(f"A_{n}").id] for n in jn])
        self.act = np.array([m.actuator(f"A_{n}").id for n in jn])
        self.kp = np.array([m.actuator_gainprm[a, 0] for a in self.act])
        self.tip = m.site("A_tip").id
        self.b6 = m.body("A_b6").id
        J = self.info["joints"]
        self.tmax = np.array([j["tmax"] for j in J])
        self.t_fast = np.array([j["t_fast"] for j in J])
        self.vmax = np.array([j["vmax"] for j in J])
        self.vfast = np.array([j["vmax_fast"] for j in J])
        self.lim = np.array([j["limit"] for j in J])
        self.dsdm = np.array([j["dsdm"] for j in J])
        self.frame_skip = int(round(DT_CTRL / m.opt.timestep))
        self.force_target = force_target
        self.trace_steps = 8
        self.sensors = [m.sensor(f"rfp{i}").id for i in range(1, 5)]
        self.sens_xy = np.array([m.site_xpos[m.site(f"rfp{i}").id][:2] for i in range(1, 5)]) if False else None
        c = np.array(self.info["canvas_center"])
        self.canvas = c
        # zone de travail : cote exterieur de la toile (pres du socle, J3 bute a 140 deg)
        self.center = c + np.array([0.04, 0.0])
        self.surface = self.info["surface_z"]
        self.home = np.radians(self.info["home_deg"])
        self.results = {}
        self.stats = {}
        self.fast_time = 0.0
        self.t = 0.0

    # ------------------------------------------------------------------ IK cinematique
    def ik(self, goal, q0, starts=20):
        q = self._ik(goal, q0, starts)
        if q is None and starts < 8:
            q = self._ik(goal, q0, 12)
        return q

    def _ik(self, goal, q0, starts=20):
        m, kd = self.m, self.kd
        rng = np.random.default_rng(0)
        best = None
        for k, s0 in enumerate([q0] + [rng.uniform(-self.lim, self.lim) for _ in range(starts)]):
            kd.qpos[:] = self.d.qpos
            kd.qpos[self.qa] = s0
            for _ in range(200):
                mujoco.mj_kinematics(m, kd)
                mujoco.mj_comPos(m, kd)
                p = kd.site_xpos[self.tip]
                ax = kd.xmat[self.b6].reshape(3, 3)[:, 2]
                jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
                mujoco.mj_jacSite(m, kd, jp, jr, self.tip)
                Jm = np.vstack([jp[:, self.da], 0.3 * jr[:, self.da]])
                err = np.r_[goal - p, 0.3 * np.cross(ax, [0, 0, -1.0])]
                if np.linalg.norm(err) < 2e-5:
                    break
                dq = Jm.T @ np.linalg.solve(Jm @ Jm.T + 0.02 ** 2 * np.eye(6), err)
                kd.qpos[self.qa] = np.clip(kd.qpos[self.qa] + np.clip(dq, -0.1, 0.1), -self.lim + 0.02, self.lim - 0.02)
            mujoco.mj_forward(m, kd)
            if np.linalg.norm(goal - kd.site_xpos[self.tip]) > 0.0015:
                continue
            tq = float(np.max(np.abs(kd.qfrc_bias[self.da]) / self.tmax))
            cost = tq + 0.3 * np.linalg.norm(kd.qpos[self.qa] - q0)
            if best is None or cost < best[0]:
                best = (cost, kd.qpos[self.qa].copy())
            if k == 0 and tq < 0.9:
                break
        return None if best is None else best[1]

    # ------------------------------------------------------------------ commande (firmware)
    def speed_limits(self):
        bias = np.abs(self.d.qfrc_bias[self.da])
        fast = self.dsdm & (bias < 0.8 * self.t_fast)
        return np.where(fast, self.vfast, self.vmax), fast

    def step_to(self, qref):
        """Asservissement MKS SERVO42C : PD (actionneur) + anticipation de gravite + integrale."""
        d = self.d
        e = qref - d.qpos[self.qa]
        self.integ = np.clip(self.integ + e * DT_CTRL, -0.01, 0.01)
        ff = d.qfrc_bias[self.da] / self.kp
        d.ctrl[self.act] = np.clip(qref + ff + 3.0 * self.integ, -self.lim, self.lim)
        mujoco.mj_step(self.m, d, self.frame_skip)
        self.t += DT_CTRL

    def move_joint(self, qgoal, cb, tol=0.004, tmax=6.0):
        """Ralliement articulaire synchronise a vitesse maxi (profil trapeze simplifie)."""
        qref = self.d.qpos[self.qa].copy()
        t0 = self.t
        while self.t - t0 < tmax:
            vl, fast = self.speed_limits()
            dq = qgoal - qref
            tmin = np.max(np.abs(dq) / vl)
            if tmin < DT_CTRL:
                qref = qgoal.copy()
            else:
                qref = qref + dq * DT_CTRL / tmin
            if np.any(fast):
                self.fast_time += DT_CTRL
            self.step_to(qref)
            cb()
            if np.max(np.abs(self.d.qpos[self.qa] - qgoal)) < tol:
                break
        return self.t - t0

    def forces(self):
        return np.array([self.d.sensordata[self.m.sensor_adr[s]] for s in self.sensors])

    # ------------------------------------------------------------------ scenario
    def run(self, cb):
        m, d = self.m, self.d
        mujoco.mj_resetData(m, d)
        self.integ = np.zeros(6)
        # demo 1 bras : breadboard et composant ranges hors de la toile
        m.body_pos[m.body("breadboard").id] = [-0.4, 0.4, 0.005]
        d.qpos[self.qa] = self.home
        mujoco.mj_forward(m, d)
        self.t = 0.0
        # parc la composante hors toile du composant (inutile ici) : on le met de cote
        cq = m.jnt_qposadr[m.joint("composant").id]
        d.qpos[cq:cq + 3] = [-0.3, -0.3, 0.01]
        mujoco.mj_forward(m, d)
        above = np.r_[self.center, self.surface + 0.06]

        # 1. VITESSE ---------------------------------------------------------------
        self.stats["epreuve"] = "1/3 VITESSE : grand deplacement (DSDM)"
        cb()
        q_up = np.radians([60, 0, 0, 0, 0, 0])
        dur1 = self.move_joint(q_up, cb)
        qa = self.ik(above, d.qpos[self.qa])
        t_move = self.move_joint(qa, cb)
        self.results["vitesse"] = {"duree_s": round(dur1 + t_move, 2),
                                   "temps_en_mode_vitesse_DSDM_s": round(self.fast_time, 2)}

        # 2. PRECISION : deux passes (rapide puis fine) -> compromis vitesse / precision mesure
        self.results["precision"] = {}
        for label, r, steps in (("rapide", 0.040, 8), ("fine", 0.025, 20)):
            self.stats["epreuve"] = f"2/3 PRECISION ({label}) : cercle r={r * 1000:.0f} mm a 2 mm de la toile"
            n = 120
            z = self.surface + 0.002
            path = [np.r_[self.center + r * np.array([math.cos(a), math.sin(a)]), z]
                    for a in np.linspace(0, 2 * math.pi, n + 1)]
            q = self.ik(path[0], d.qpos[self.qa])
            self.move_joint(q, cb)
            errs = []
            for p in path[1:]:
                qn = self.ik(p, q, starts=0)
                if qn is None:
                    continue
                q = qn
                for _ in range(steps):
                    vl, _ = self.speed_limits()
                    qref = d.qpos[self.qa] + np.clip(q - d.qpos[self.qa], -vl * DT_CTRL, vl * DT_CTRL)
                    self.step_to(qref)
                tip = d.site_xpos[self.tip]
                e = math.hypot(np.linalg.norm(tip[:2] - self.center) - r, tip[2] - z)
                errs.append(e)
                self.stats["erreur_mm"] = round(e * 1000, 2)
                cb()
            errs = np.array(errs)
            self.results["precision"][label] = {
                "rms_mm": round(float(np.sqrt(np.mean(errs ** 2))) * 1000, 2),
                "max_mm": round(float(errs.max()) * 1000, 2),
                "duree_cercle_s": round(len(errs) * steps * DT_CTRL, 1),
                "vitesse_mm_s": round(2 * math.pi * r * 1000 / (len(errs) * steps * DT_CTRL), 1)}
        self.results["precision"] = {f"{k}_{kk}": vv for k, v in self.results["precision"].items()
                                     for kk, vv in v.items()}

        # 3. FORCE -----------------------------------------------------------------
        self.stats["epreuve"] = f"3/3 FORCE : appui regule {self.force_target:g} N sur les 4 RFP602"
        press_xy = self.center + np.array([0.02, 0.025])
        q = self.ik(np.r_[press_xy, self.surface + 0.01], d.qpos[self.qa])
        self.move_joint(q, cb)
        zc = self.surface + 0.002
        tare = self.forces().copy()             # poids propre de la toile
        hist = []
        for k in range(300):
            F = (self.forces() - tare).sum()
            zc -= 0.00002 * (self.force_target - F)          # admittance : ~0.02 mm / N / pas
            zc = min(zc, self.surface + 0.01)
            qn = self.ik(np.r_[press_xy, zc], d.qpos[self.qa], starts=0)
            if qn is not None:
                q = qn
            self.step_to(q)
            f4 = np.maximum(self.forces() - tare, 0)
            F = f4.sum()
            hist.append(F)
            xy = (f4[:, None] * self.sens_centers()).sum(0) / F if F > 0.5 else None
            self.stats["force_N"] = round(float(F), 2)
            self.stats["rfp602_N"] = [round(float(v), 2) for v in f4]
            if xy is not None:
                self.stats["appui_triangule_mm"] = (np.array(xy) * 1000).round(1).tolist()
            cb()
        f4 = np.maximum(self.forces() - tare, 0)
        F = f4.sum()
        xy = (f4[:, None] * self.sens_centers()).sum(0) / max(F, 1e-6)
        tip = d.site_xpos[self.tip][:2]
        steady = np.array(hist[-80:])
        self.results["force"] = {
            "consigne_N": self.force_target, "force_moyenne_N": round(float(steady.mean()), 2),
            "ecart_type_N": round(float(steady.std()), 2),
            "capteurs_N": [round(float(v), 2) for v in f4],
            "appui_triangule_mm": (xy * 1000).round(1).tolist(),
            "position_outil_mm": (tip * 1000).round(1).tolist(),
            "erreur_triangulation_mm": round(float(np.linalg.norm(xy - tip)) * 1000, 1),
            "couple_J2_Nm": round(float(d.actuator_force[self.act[1]]), 2),
            "couple_J2_max_Nm": round(float(self.tmax[1]), 2),
        }
        # remontee
        self.stats["epreuve"] = "Termine"
        self.move_joint(self.ik(above, d.qpos[self.qa]), cb)
        return self.results

    def sens_centers(self):
        """Position (monde, m) des 4 capteurs RFP602 : coins de la matrice carree."""
        sp = 0.075
        c = self.canvas
        return np.array([[c[0] - sp, c[1] - sp], [c[0] - sp, c[1] + sp],
                         [c[0] + sp, c[1] - sp], [c[0] + sp, c[1] + sp]])
