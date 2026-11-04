"""Backend MuJoCo de l'API robot (scene atelier)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import mujoco
import numpy as np

from .api import RobotAPI

DT = 0.02


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _qconj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


class SimRobot(RobotAPI):
    def __init__(self, build_dir: Path, frame_cb=lambda r: None, progress=lambda m: None):
        from ..sim.atelier import build_atelier
        sim = build_dir / "sim"
        xml = sim / "atelier.xml"
        man_t = (build_dir / "manifest.json").stat().st_mtime
        src = max((Path(__file__).parent.parent / "sim" / f).stat().st_mtime for f in ("atelier.py", "mjcf.py"))
        if not xml.exists() or xml.stat().st_mtime < max(man_t, src):     # scene perimee : regeneree
            build_atelier(build_dir, progress)
        self.info = json.loads((sim / "atelier_info.json").read_text(encoding="utf8"))
        man = json.loads((build_dir / "manifest.json").read_text(encoding="utf8"))
        self.m = mujoco.MjModel.from_xml_path(str(xml))
        self.d = mujoco.MjData(self.m)
        self.kd = mujoco.MjData(self.m)
        m = self.m
        J = self.info["joints"]
        jn = [j["name"] for j in J]
        self.qa = np.array([m.jnt_qposadr[m.joint(f"A_{n}").id] for n in jn])
        self.da = np.array([m.jnt_dofadr[m.joint(f"A_{n}").id] for n in jn])
        self.act = np.array([m.actuator(f"A_{n}").id for n in jn])
        self.kp = np.array([m.actuator_gainprm[a, 0] for a in self.act])
        self.tmax = np.array([j["tmax"] for j in J])
        self.t_fast = np.array([j["t_fast"] for j in J])
        self.vmax = np.array([j["vmax"] for j in J])
        self.vfast = np.array([j["vmax_fast"] for j in J])
        self.lim = np.array([j["limit"] for j in J])
        self.dsdm = np.array([j["dsdm"] for j in J])
        self.b6 = m.body("A_b6").id
        self.face = m.site("A_face").id
        T6 = np.array(man["joints"][5]["T"])
        self.R6 = T6[:3, :3]                     # axes du repere tete/outil en pose zero
        self.frame_skip = int(round(DT / m.opt.timestep))
        self.mounted = None
        self.lock_state = 0.0
        self.t = 0.0
        self.log = []
        self.frame_cb = frame_cb
        self.integ = np.zeros(6)
        self.eq = {n: m.equality(n).id for n in ("verrou_P", "verrou_H")}
        self.tools = self.info["outils"]
        self.touch_ok = set()                                # corps que le bras a le droit de toucher
        self.clearance = 0.015                               # degagement exige des objets mobiles
        self.clear_world = False
        self.hand_ctrl = {k: [(m.actuator(j).id, mx) for j, mx in v] for k, v in self.tools["H"].get("ctrl", {}).items()}
        self.grip_now = {}
        mujoco.mj_resetData(m, self.d)
        self.d.qpos[self.qa] = 0.0                    # atelier : depart bras droit
        # les outils sont maintenus dans leur fourche (contrainte = prise de la gorge)
        self.rack_eq = {}
        mujoco.mj_forward(m, self.d)
        for tid in ("P", "H"):
            self._add_rack_hold(tid)
        self.qref = self.d.qpos[self.qa].copy()

    # ================================================================ geometrie
    def _tool_R(self, d=None):
        d = d or self.d
        return d.xmat[self.b6].reshape(3, 3) @ self.R6

    def _tcp_local(self):
        if self.mounted is None:
            return np.zeros(3)
        return np.array(self.tools[self.mounted]["tcp"])

    def q(self):
        return self.d.qpos[self.qa].copy()

    def face_pos(self):
        return self.d.site_xpos[self.face].copy()

    def tcp_offset(self, z_axis, x_axis):
        """Position du TCP de l'outil monte par rapport a la face, pour une orientation donnee."""
        z = np.asarray(z_axis, float) / np.linalg.norm(z_axis)
        x = np.asarray(x_axis, float) - np.dot(x_axis, z) * z
        x /= np.linalg.norm(x)
        R = np.column_stack([x, np.cross(z, x), z])
        return R @ self._tcp_local()

    def tcp(self, d=None):
        d = d or self.d
        return d.site_xpos[self.face] + self._tool_R(d) @ self._tcp_local()

    def object_pos(self, name):
        return self.d.xpos[self.m.body(name).id].copy()

    # ================================================================ IK
    def _ik_solve(self, s0, pos, z, x, tcp_l, iters=220):
        """Moindres carres amortis depuis s0 (kd.qpos modifie en place). Boucle optimisee : produits
        vectoriels en ligne, matrices pre-allouees, abandon precoce des graines qui stagnent."""
        m, kd, qa, da = self.m, self.kd, self.qa, self.da
        if not hasattr(self, "_J"):
            self._jp, self._jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
            self._J = np.zeros((6, 6))
            self._lam = 0.02 ** 2 * np.eye(6)
            self._lo, self._hi = -self.lim + 0.02, self.lim - 0.02
        jp, jr, J, lam, lo, hi = self._jp, self._jr, self._J, self._lam, self._lo, self._hi
        q = np.array(s0, float)
        err = np.empty(6)
        z0, z1, z2 = z
        for it in range(iters):
            kd.qpos[qa] = q
            mujoco.mj_kinematics(m, kd)
            mujoco.mj_comPos(m, kd)
            R = kd.xmat[self.b6].reshape(3, 3) @ self.R6
            p = kd.site_xpos[self.face] + R @ tcp_l
            a0, a1, a2 = R[0, 2], R[1, 2], R[2, 2]
            e0, e1, e2 = a1 * z2 - a2 * z1, a2 * z0 - a0 * z2, a0 * z1 - a1 * z0
            if x is not None:
                b0, b1, b2 = R[0, 0], R[1, 0], R[2, 0]
                e0 += b1 * x[2] - b2 * x[1]
                e1 += b2 * x[0] - b0 * x[2]
                e2 += b0 * x[1] - b1 * x[0]
            err[:3] = pos - p
            err[3], err[4], err[5] = 0.4 * e0, 0.4 * e1, 0.4 * e2
            en = math.sqrt(err @ err)
            if en < 2e-5:
                break
            if (it == 90 and en > 0.08) or (it == 160 and en > 0.01):
                return False                                 # graine sans espoir : abandon
            mujoco.mj_jac(m, kd, jp, jr, p, self.b6)
            J[:3] = jp[:, da]
            J[3:] = 0.4 * jr[:, da]
            dq = J.T @ np.linalg.solve(J @ J.T + lam, err)
            np.clip(dq, -0.1, 0.1, out=dq)
            q += dq
            np.clip(q, lo, hi, out=q)
        kd.qpos[qa] = q
        return True

    def ik(self, pos, z_axis, x_axis=None, q0=None, starts=40, check=True):
        m, kd = self.m, self.kd
        pos, z_axis = np.asarray(pos, float), np.asarray(z_axis, float) / np.linalg.norm(z_axis)
        x_axis = None if x_axis is None else np.asarray(x_axis, float) / np.linalg.norm(x_axis)
        q0 = self.d.qpos[self.qa].copy() if q0 is None else q0
        rng = np.random.default_rng(1)
        home = np.radians(self.info.get("home_deg", [0, 0, 0, 0, 0, 0]))
        best = None
        tcp_l = self._tcp_local()
        seeds = [q0] if starts == 0 else [q0, home] + [rng.uniform(-self.lim, self.lim) for _ in range(starts)]
        for k, s0 in enumerate(seeds):          # starts=0 : suivi local uniquement (pas de saut de branche)
            kd.qpos[:] = self.d.qpos
            if not self._ik_solve(s0, pos, z_axis, x_axis, tcp_l):
                continue
            mujoco.mj_forward(m, kd)
            R = self._tool_R(kd)
            p = kd.site_xpos[self.face] + R @ tcp_l
            ok = np.linalg.norm(pos - p) < 0.0015 and np.dot(R[:, 2], z_axis) > 0.998 and \
                (x_axis is None or np.dot(R[:, 0], x_axis) > 0.995)
            if not ok:
                continue
            tq = float(np.max(np.abs(kd.qfrc_bias[self.da]) / self.tmax))
            qs = kd.qpos[self.qa].copy()
            if check and self._collides(qs, 0.0):            # configuration dans le decor : rejetee
                continue
            marge = self.lim - np.abs(qs)                  # distance aux butees (rad)
            cost = tq + 0.25 * np.linalg.norm(qs - q0) + 4.0 * float(np.sum(np.clip(0.35 - marge, 0, None)))
            if best is None or cost < best[0]:
                best = (cost, qs)
            if k == 0 and tq < 0.85 and np.min(self.lim - np.abs(qs)) > 0.35:
                break                                     # graine courante bonne et loin des butees
        return None if best is None else best[1]

    # ================================================================ commande (firmware)
    def _speed_limits(self):
        bias = np.abs(self.d.qfrc_bias[self.da])
        fast = self.dsdm & (bias < 0.8 * self.t_fast)
        return np.where(fast, self.vfast, self.vmax)

    def _step(self, n=1):
        d = self.d
        for _ in range(n):
            e = self.qref - d.qpos[self.qa]
            self.integ = np.clip(self.integ + e * DT, -0.01, 0.01)
            ff = d.qfrc_bias[self.da] / self.kp
            d.ctrl[self.act] = np.clip(self.qref + ff + 3.0 * self.integ, -self.lim, self.lim)
            mujoco.mj_step(self.m, d, self.frame_skip)
            self.t += DT
            self.frame_cb(self)

    def move_joints(self, qgoal, speed=1.0, tol=0.004, tmax=8.0):
        t0 = self.t
        while self.t - t0 < tmax:
            vl = self._speed_limits() * speed
            dq = qgoal - self.qref
            tmin = np.max(np.abs(dq) / vl)
            self.qref = qgoal.copy() if tmin < DT else self.qref + dq * DT / tmin
            self._step()
            if np.max(np.abs(self.d.qpos[self.qa] - qgoal)) < tol and tmin < DT:
                break
        return True

    def ik_chain(self, pts, z_axis, x_axis=None, starts=40, step=0.004):
        """Configuration de depart telle que TOUT le trajet lineaire pts[0]->pts[1]->... se suit
        localement sans saut de branche (plongee, insertion). Renvoie q du premier point."""
        rng = np.random.default_rng(7)
        seeds = [self.q(), np.radians(self.info.get("home_deg", [0, 0, 0, 0, 0, 0]))] +             [rng.uniform(-self.lim, self.lim) for _ in range(starts)]
        for s0 in seeds:
            q = self.ik(pts[0], z_axis, x_axis, q0=s0, starts=0)
            if q is None:
                continue
            q_first, ok, p0 = q.copy(), True, np.asarray(pts[0], float)
            for p1 in pts[1:]:
                p1 = np.asarray(p1, float)
                n = max(1, int(np.linalg.norm(p1 - p0) / step))
                for i in range(1, n + 1):
                    qn = self.ik(p0 + (p1 - p0) * i / n, z_axis, x_axis, q0=q, starts=0, check=False)
                    if qn is None or np.max(np.abs(qn - q)) > math.radians(15) or                             self._collides(qn, 0.001, self_only=True):     # jamais d'auto-collision
                        ok = False
                        break
                    q = qn
                if not ok:
                    break
                p0 = p1
            if ok:
                return q_first
        return None

    def move_to_chain(self, pts, z_axis, x_axis=None, speed=1.0):
        q = self.ik_chain(pts, z_axis, x_axis)
        if q is None:
            self.say(f"  ! aucune configuration ne permet le trajet complet depuis {np.round(np.asarray(pts[0]) * 1000).tolist()} mm")
            return False
        return self.transit(q, speed)

    def move_to(self, pos, z_axis, x_axis=None, speed=1.0):
        q = self.ik(pos, z_axis, x_axis)
        if q is None:
            self.say(f"  ! pose inatteignable {np.round(np.asarray(pos) * 1000).tolist()} mm")
            return False
        return self.transit(q, speed)

    # ================================================================ planification
    def _arm_bodies(self):
        if not hasattr(self, "_armb"):
            m = self.m
            self._armb = {m.body(f"A_b{k}").id for k in range(1, 7)}
            self._toolb = {}
            for tid in ("P", "H"):
                root = m.body(f"outil_{tid}").id
                self._toolb[tid] = {b for b in range(m.nbody) if self._root_of(b) == root}
        return self._armb

    def _tool_roots(self):
        return {self.m.body(f"outil_{t}").id for t in ("P", "H") if t != self.mounted}

    def _root_of(self, b):
        m = self.m
        while m.body_parentid[b] != 0:
            b = m.body_parentid[b]
        return b

    def _collides(self, q, tol=0.0, self_only=False):
        """Le bras (et l'outil monte) en configuration q touche-t-il le decor ou un autre outil ?"""
        m, kd = self.m, self.kd
        kd.qpos[:] = self.d.qpos
        kd.qpos[self.qa] = q
        if self.mounted:                                     # l'outil suit la tete (soudure)
            d = self.d
            tb = m.body(f"outil_{self.mounted}").id
            R6, p6 = d.xmat[self.b6].reshape(3, 3), d.xpos[self.b6]
            Rt, pt = d.xmat[tb].reshape(3, 3), d.xpos[tb]
            Rrel, prel = R6.T @ Rt, R6.T @ (pt - p6)
            mujoco.mj_kinematics(m, kd)
            R6k, p6k = kd.xmat[self.b6].reshape(3, 3), kd.xpos[self.b6]
            jid = m.joint(f"outil_{self.mounted}_libre").id
            adr = m.jnt_qposadr[jid]
            quat = np.zeros(4)
            mujoco.mju_mat2Quat(quat, (R6k @ Rrel).flatten())
            kd.qpos[adr:adr + 3] = p6k + R6k @ prel
            kd.qpos[adr + 3:adr + 7] = quat
        # marge de detection : les contacts sont generes jusqu'a CLEAR mm d'ecart, pour exiger
        # un degagement reel vis-a-vis des obstacles (le suivi reel devie un peu du plan)
        saved = m.geom_margin.copy()
        m.geom_margin[:] = saved + (self.clearance if self.clearance > 0 else 0.0)
        try:
            mujoco.mj_forward(m, kd)
        finally:
            m.geom_margin[:] = saved
        arm = self._arm_bodies() | (self._toolb[self.mounted] if self.mounted else set())
        for c in kd.contact[:kd.ncon]:
            b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
            if b1 in arm and b2 in arm:                      # auto-collision bras/bras ou main/bras
                tb = self._toolb[self.mounted] if self.mounted else set()
                if (b1 in tb and b2 in tb) or ({b1, b2} & {self.b6} and {b1, b2} & tb):
                    continue                                 # interne a la main / main sur sa tete
                if c.dist < -tol:
                    return True
                continue
            if (b1 in arm) == (b2 in arm) or self_only:
                continue
            other = b2 if b1 in arm else b1
            if other != 0 and self._root_of(other) in self.touch_ok:
                continue                                     # objet en cours de saisie : contact voulu
            if other == 0 and not self.clear_world:
                lim = -tol                                   # decor fixe : contact exact
            else:
                lim = self.clearance - tol if other != 0 else -tol
            if c.dist < lim:
                return True
        return False

    def path_free(self, qa, qb, n=24):
        return self._path_free(qa, qb, n, tol=0.0005)         # planification : marge stricte

    def move_path(self, q, speed=1.0):
        """Deplacement articulaire court, verifie sans collision avant execution."""
        if not self._path_free(self.d.qpos[self.qa].copy(), q, tol=0.003):   # execution
            self.say("  ! trajet en collision, refuse")
            return False
        self.move_joints(q, speed)
        return self._reached(q, math.radians(4.0))

    def _path_free(self, qa, qb, n=24, tol=0.001):
        # echantillonnage dense : 1 point tous les 1.5 deg sur l'articulation qui bouge le plus
        # (a 250 mm de rayon, un bout de doigt parcourt ~6.5 mm entre deux points)
        n = max(n, int(np.max(np.abs(qb - qa)) / math.radians(1.5)) + 1)
        return not any(self._collides(qa + (qb - qa) * i / n, tol) for i in range(1, n + 1))

    def transit(self, q, speed=1.0):
        """Transit sans collision : trajet direct s'il est libre, sinon passage par des points
        de passage (bras redresse, puis au-dessus de la cible) verifies un par un."""
        cur = self.d.qpos[self.qa].copy()
        if self._path_free(cur, q):
            self.move_joints(q, speed)
            return self._reached_or_say(q)
        tcp_goal = None
        cands = []
        up_c = np.array([cur[0], 0.0, 0.0, 0.0, 0.0, cur[5]])
        up_g = np.array([q[0], 0.0, 0.0, 0.0, 0.0, q[5]])
        # au-dessus de la cible (meme orientation), de plus en plus haut
        R = self._fk_R(q)
        p_goal = self._fk_tcp(q)
        above = []
        for h in (0.08, 0.15, 0.25):
            qa = self.ik(p_goal + [0, 0, h], R[:, 2], R[:, 0], q0=q, starts=6)
            if qa is not None:
                above.append(qa)
        for qa in above:
            cands.append([up_c, up_g, qa])
            cands.append([qa])
        cands.append([up_c, up_g])
        # degagement vertical de l'outil depuis la pose courante (sortir d'un rack, d'une table)
        Rc, pc = self._fk_R(cur), self._fk_tcp(cur)
        lifts = []
        for h in (0.10, 0.20):
            ql = self.ik(pc + [0, 0, h], Rc[:, 2], Rc[:, 0], q0=cur, starts=0, check=True)
            if ql is not None:
                lifts.append(ql)
        for ql in lifts:
            cands.append([ql, up_c, up_g] + above[:1])
            cands.append([ql, up_g])
            cands.append([ql] + above[:1])
        for wps in cands:
            seq, prev, ok = wps + [q], cur, True
            for w in seq:
                if not self._path_free(prev, w):
                    ok = False
                    break
                prev = w
            if ok:
                for w in seq:
                    self.move_joints(w, speed)
                return self._reached_or_say(q)
        # dernier recours : planification aleatoire (RRT-connect simplifie a 1-2 relais)
        path = self._random_relay(cur, q)
        if path:
            for w in path:
                self.move_joints(w, speed)
            return self._reached_or_say(q)
        self.say("  ! aucun trajet sans collision trouve")
        return False

    def _random_relay(self, qa, qb, n=400):
        rng = np.random.default_rng(11)
        pool = []
        for _ in range(n):
            w = rng.uniform(-self.lim * 0.9, self.lim * 0.9)
            w[5] = qb[5]
            if self._collides(w, 0.0005):
                continue
            if self._path_free(qa, w) and self._path_free(w, qb):
                return [w, qb]
            pool.append(w)
        for w1 in pool:                                      # deux relais
            if not self._path_free(qa, w1):
                continue
            for w2 in pool:
                if self._path_free(w1, w2) and self._path_free(w2, qb):
                    return [w1, w2, qb]
        return None

    def _reached_or_say(self, q):
        if self._reached(q):
            return True
        e = np.degrees(self.q() - q)
        sat = np.abs(self.d.actuator_force[self.act]) >= 0.98 * self.tmax
        self.say(f"  ! consigne non atteinte (ecart deg {np.round(e, 1).tolist()}"
                 f"{', couple sature : ' + str([f'J{i + 1}' for i in np.nonzero(sat)[0]]) if sat.any() else ''})")
        return False

    def _reached(self, q, tol=math.radians(2.0)):
        return bool(np.max(np.abs(self.d.qpos[self.qa] - q)) < tol)

    def _fk_tcp(self, q):
        kd = self.kd
        kd.qpos[:] = self.d.qpos
        kd.qpos[self.qa] = q
        mujoco.mj_kinematics(self.m, kd)
        return self.tcp(kd)

    def _fk_R(self, q):
        kd = self.kd
        kd.qpos[:] = self.d.qpos
        kd.qpos[self.qa] = q
        mujoco.mj_kinematics(self.m, kd)
        return self._tool_R(kd)

    def move_linear(self, pos, z_axis, x_axis=None, dist_step=0.004, check=False):
        p0 = self.tcp()
        pos = np.asarray(pos, float)
        n = max(1, int(np.linalg.norm(pos - p0) / dist_step))
        q = self.d.qpos[self.qa].copy()
        for i in range(1, n + 1):
            pi = p0 + (pos - p0) * i / n
            qp = q
            q = self.ik(pi, z_axis, x_axis, q0=q, starts=0, check=False)   # mouvement de contact voulu (plongee, insertion)
            if q is not None and np.max(np.abs(q - qp)) > math.radians(15):
                q = None                                                   # saut de configuration : refuse
            if q is not None and self._collides(q, 0.001, self_only=not check):
                self.say("  ! trajectoire lineaire : collision prevue")
                q = None
            if q is None:
                self.say(f"  ! trajectoire lineaire interrompue a {i}/{n}")
                return False
            self.move_joints(q, speed=0.5, tol=0.01, tmax=1.0)
        self.move_joints(q, speed=0.5, tmax=1.5)
        err = float(np.linalg.norm(self.tcp() - pos))
        if err > 0.005:                                   # bloque (contact, couple) : on le dit
            self.say(f"  ! cible lineaire manquee de {err * 1000:.1f} mm")
            return False
        return True

    def wait(self, seconds):
        self._step(max(1, int(seconds / DT)))

    # ================================================================ contraintes (verrou / rack)
    def _weld_to(self, eq_id, b1, b2):
        m, d = self.m, self.d
        if b2 == 0:          # monde
            p2, q2 = np.zeros(3), np.array([1.0, 0, 0, 0])
        else:
            p2, q2 = d.xpos[b2], d.xquat[b2]
        p1, q1 = d.xpos[b1], d.xquat[b1]
        R1 = d.xmat[b1].reshape(3, 3)
        m.eq_data[eq_id, 3:6] = R1.T @ (p2 - p1)
        m.eq_data[eq_id, 6:10] = _qmul(_qconj(q1), q2)
        d.eq_active[eq_id] = 1

    def _add_rack_hold(self, tid):
        # contrainte de maintien outil <-> monde : reutilise l'egalite du verrou, corps1 = outil
        m = self.m
        b = m.body(f"outil_{tid}").id
        # pas d'egalite "rack" dediee dans le modele : on fige l'outil en controlant sa pose libre
        self.rack_eq[tid] = {"body": b, "held": True, "pose": (self.d.xpos[b].copy(), self.d.xquat[b].copy())}

    def _hold_tools(self):
        m, d = self.m, self.d
        for tid, h in self.rack_eq.items():
            if not h["held"]:
                continue
            jid = m.joint(f"outil_{tid}_libre").id
            qa, da = m.jnt_qposadr[jid], m.jnt_dofadr[jid]
            d.qpos[qa:qa + 3], d.qpos[qa + 3:qa + 7] = h["pose"]
            d.qvel[da:da + 6] = 0

    def lock(self):
        """Verrouillage : l'outil doit etre centre (cones) et la face au contact."""
        d = self.d
        best = None
        for tid in ("P", "H"):
            b = self.m.body(f"outil_{tid}").id
            e = np.linalg.norm(d.site_xpos[self.face] - d.xpos[b]) * 1000
            R_t = d.xmat[b].reshape(3, 3)
            ang = math.degrees(math.acos(np.clip(np.dot(R_t[:, 2], self._tool_R()[:, 2]), -1, 1)))
            if best is None or e < best[1]:
                best = (tid, e, ang)
        tid, e, ang = best
        for k in range(15):                     # rotation de la bague (servo 90 deg en 0.3 s)
            self.lock_state = (k + 1) / 15
            self._step()
        if e > 5.0 or ang > 6.0:
            self.lock_state = 0.0
            return {"ok": False, "erreur_mm": round(e, 2), "angle_deg": round(ang, 2)}
        self.rack_eq[tid]["held"] = False
        self._weld_to(self.eq[f"verrou_{tid}"], self.b6, self.m.body(f"outil_{tid}").id)
        self.mounted = tid
        return {"ok": True, "outil": tid, "erreur_mm": round(e, 2), "angle_deg": round(ang, 2)}

    def unlock(self):
        if self.mounted is None:
            return
        self.d.eq_active[self.eq[f"verrou_{self.mounted}"]] = 0
        for k in range(15):
            self.lock_state = 1 - (k + 1) / 15
            self._step()
        self.mounted = None

    def dock(self, slot):
        tid = self.mounted
        b = self.m.body(f"outil_{tid}").id
        self.rack_eq[tid] = {"body": b, "held": True, "pose": (self.d.xpos[b].copy(), self.d.xquat[b].copy())}

    def undock(self, slot):
        pass

    def read_tool_id(self):
        if self.mounted is None:
            return None
        return self.info["eeprom"].get(self.mounted)

    # ================================================================ main
    def grasp_center(self, prise):
        """Centre reel de la prise (repere outil H) : barycentre des phalanges des doigts et du
        pouce dans la configuration fermee `prise` (cinematique pure, main hors contact)."""
        m, kd = self.m, self.kd
        kd.qpos[:] = self.d.qpos
        tb = m.body("outil_H").id
        bodies = []
        for k, v in prise.items():
            if k in ("opp", "ecart"):
                pass
            for aid, mx in self.hand_ctrl.get(k, []):
                jid = m.actuator_trnid[aid, 0]
                lo, hi = m.jnt_range[jid]
                kd.qpos[m.jnt_qposadr[jid]] = float(np.clip(v * mx, lo, hi))
                if k not in ("opp", "ecart"):
                    bodies.append(m.jnt_bodyid[jid])
        mujoco.mj_kinematics(m, kd)
        R, p = kd.xmat[tb].reshape(3, 3), kd.xpos[tb]
        pts = np.array([R.T @ (kd.xipos[b] - p) for b in bodies])
        return pts.mean(0)

    def allow_touch(self, *names):
        self.touch_ok = {self.m.body(n).id for n in names}

    def touching(self, obj):
        """Quelles parties de la main touchent l'objet (equivalent des capteurs de pulpe)."""
        m, d = self.m, self.d
        ob = m.body(obj).id
        names = {}
        for tid_ctrl, lst in self.hand_ctrl.items():
            if tid_ctrl in ("opp", "ecart"):
                continue
            for aid, _ in lst:
                b = m.jnt_bodyid[m.actuator_trnid[aid, 0]]
                for bb in range(m.nbody):                    # le corps et ses descendants
                    x = bb
                    while x not in (0, b):
                        x = m.body_parentid[x]
                    if x == b:
                        names[bb] = tid_ctrl
        root = m.body("outil_H").id
        out = set()
        for c in d.contact[:d.ncon]:
            b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
            if ob not in (b1, b2):
                continue
            o = b2 if b1 == ob else b1
            if o in names:
                out.add(names[o])
            elif o == root:
                out.add("paume")
        return out

    def set_tcp(self, tid, local):
        self.tools[tid]["tcp"] = list(map(float, local))

    def grip(self, targets, duration=0.8):
        if self.mounted != "H":
            return
        full = {"index": 0, "majeur": 0, "annulaire": 0, "auriculaire": 0, "pouce": 0, "opp": 0, "ecart": 0}
        full.update(self.grip_now)
        start = dict(full)
        full.update(targets)
        n = max(1, int(duration / DT))
        for i in range(1, n + 1):
            for k, v in full.items():
                cur = start.get(k, 0) + (v - start.get(k, 0)) * i / n
                for aid, mx in self.hand_ctrl.get(k, []):
                    lo, hi = self.m.actuator_ctrlrange[aid]
                    self.d.ctrl[aid] = float(np.clip(cur * mx, lo, hi))
            self._step()
        self.grip_now = full

    # ================================================================ pas de simulation (outils figes au rack)
    def _step_hook(self):
        self._hold_tools()


# le maintien des outils au rack est applique a chaque pas
_orig_step = SimRobot._step


def _step_with_hold(self, n=1):
    for _ in range(n):
        self._hold_tools()
        _orig_step(self, 1)


SimRobot._step = _step_with_hold
