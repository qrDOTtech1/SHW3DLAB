"""Primitives CAO (CadQuery / OpenCASCADE)."""
from __future__ import annotations

import math

import cadquery as cq
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, Point, box as sbox
from shapely.ops import unary_union

# Visserie : (passage, tete, profondeur lamage, insert thermique d, insert L, ecrou plat)
SCREW = {
    "M2": dict(clear=2.4, head=4.0, head_h=2.0, insert=3.2, insert_l=4.0, nut=4.0),
    "M2.5": dict(clear=2.9, head=4.7, head_h=2.5, insert=3.6, insert_l=4.5, nut=5.0),
    "M3": dict(clear=3.4, head=5.8, head_h=3.2, insert=4.1, insert_l=5.7, nut=5.5),
    "M4": dict(clear=4.5, head=7.4, head_h=4.2, insert=5.6, insert_l=8.1, nut=7.0),
    "M5": dict(clear=5.5, head=9.0, head_h=5.2, insert=6.4, insert_l=9.5, nut=8.0),
}


# ---------------------------------------------------------------- 2D -> 3D
def extrude_poly(pts, h: float, z0: float = 0.0) -> cq.Workplane:
    pts = [(float(x), float(y)) for x, y in pts]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    return cq.Workplane("XY").workplane(offset=z0).polyline(pts).close().extrude(h)


def extrude_shapely(geom, h: float, z0: float = 0.0) -> cq.Workplane:
    """Extrude un Polygon/MultiPolygon shapely (trous inclus)."""
    geoms = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    result = None
    for g in geoms:
        if g.is_empty:
            continue
        solid = extrude_poly(list(g.exterior.coords), h, z0)
        holes = [extrude_poly(list(i.coords), h + 2, z0 - 1) for i in g.interiors]
        if holes:
            solid = solid.cut(union_all(holes))
        result = solid if result is None else result.union(solid)
    return result


def cyl(d: float, h: float, z0: float = 0.0, x: float = 0.0, y: float = 0.0) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(d / 2).extrude(h)


def tube(d_out: float, d_in: float, h: float, z0: float = 0.0, x=0.0, y=0.0) -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=z0).center(x, y)
            .circle(d_out / 2).circle(d_in / 2).extrude(h))


def cone(d0: float, d1: float, h: float, z0: float = 0.0, x=0.0, y=0.0) -> cq.Workplane:
    s = cq.Solid.makeCone(d0 / 2, d1 / 2, h, pnt=cq.Vector(x, y, z0), dir=cq.Vector(0, 0, 1))
    return cq.Workplane("XY").add(s)


def box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").add(cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0,
                                                   pnt=cq.Vector(x0, y0, z0)))


def hex_prism(af: float, h: float, z0: float = 0.0) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z0).polygon(6, af / math.cos(math.pi / 6)).extrude(h)


def union_all(parts: list) -> cq.Workplane | None:
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    solids = []
    for p in parts:
        solids.extend(p.vals() if isinstance(p, cq.Workplane) else [p])
    if len(solids) == 1:
        return cq.Workplane("XY").add(solids[0])
    comp = cq.Compound.makeCompound(solids)
    return cq.Workplane("XY").add(comp)


def _solids(items) -> list:
    out = []
    for p in items:
        if p is None:
            continue
        vals = p.vals() if isinstance(p, cq.Workplane) else [p]
        for v in vals:
            if isinstance(v, cq.Compound):
                out.extend(v.Solids())
            else:
                out.append(v)
    return out


def cut_all(base: cq.Workplane, cutters: list) -> cq.Workplane:
    """Soustraction robuste : chaque outil est passe separement a OCC (les outils
    peuvent se chevaucher entre eux sans corrompre le resultat)."""
    tools = _solids(cutters)
    if not tools:
        return base
    b = to_shape(base)
    res = b.cut(*tools).clean()
    return cq.Workplane("XY").add(res)


def fuse_all(parts: list) -> cq.Workplane:
    sol = _solids(parts)
    if len(sol) == 1:
        return cq.Workplane("XY").add(sol[0])
    res = sol[0].fuse(*sol[1:]).clean()
    return cq.Workplane("XY").add(res)


# ---------------------------------------------------------------- transformations
def rot_matrix(axis, angle_deg: float) -> np.ndarray:
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    a = math.radians(angle_deg)
    x, y, z = axis
    c, s, C = math.cos(a), math.sin(a), 1 - math.cos(a)
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def T(R: np.ndarray | None = None, t=(0, 0, 0)) -> np.ndarray:
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    M[:3, 3] = t
    return M


def frame_z_to(axis, x_hint=None, origin=(0, 0, 0)) -> np.ndarray:
    """Repere local dont l'axe z est `axis` (et x le plus proche de x_hint)."""
    z = np.asarray(axis, float)
    z /= np.linalg.norm(z)
    xh = np.asarray(x_hint if x_hint is not None else (1, 0, 0), float)
    if abs(np.dot(xh, z)) > 0.99:
        xh = np.array([0, 1, 0.0]) if abs(z[1]) < 0.9 else np.array([0, 0, 1.0])
    x = xh - np.dot(xh, z) * z
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return T(np.column_stack([x, y, z]), origin)


def _trsf(M: np.ndarray):
    from OCP.gp import gp_Trsf
    t = gp_Trsf()
    R = np.asarray(M, float)[:3, :3]
    # re-orthonormalisation (bruit numerique) avant de passer a OCC
    u, _, vt = np.linalg.svd(R)
    R = u @ vt
    t.SetValues(*[float(v) for v in (R[0, 0], R[0, 1], R[0, 2], M[0][3],
                                     R[1, 0], R[1, 1], R[1, 2], M[1][3],
                                     R[2, 0], R[2, 1], R[2, 2], M[2][3])])
    return t


def _xform(shape: cq.Shape, M) -> cq.Shape:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    return cq.Shape.cast(BRepBuilderAPI_Transform(shape.wrapped, _trsf(M), True).Shape())


def apply_T(shape: cq.Workplane | cq.Shape, M: np.ndarray):
    """Applique une matrice homogene 4x4 (rigide) a une forme."""
    if np.allclose(M, np.eye(4)):
        return shape
    if isinstance(shape, cq.Workplane):
        vals = [_xform(v, M) for v in shape.vals()]
        return cq.Workplane("XY").add(vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals))
    return _xform(shape, M)


def to_shape(w) -> cq.Shape:
    if isinstance(w, cq.Shape):
        return w
    vals = w.vals()
    if len(vals) == 1:
        return vals[0]
    return cq.Compound.makeCompound(vals)


# ---------------------------------------------------------------- features
def bolt_circle(n: int, r: float, start_deg: float = 0.0, skip=None):
    pts = []
    for k in range(n):
        a = math.radians(start_deg + 360 * k / n)
        p = (r * math.cos(a), r * math.sin(a))
        if skip and skip(p):
            continue
        pts.append(p)
    return pts


def holes(points, d: float, z0: float, h: float) -> list:
    return [cyl(d, h, z0, x, y) for x, y in points]


def counterbored(points, screw: str, z_top: float, depth_through: float, cb_depth: float) -> list:
    """Percages de passage + lamages ouverts vers +z (tete en haut)."""
    s = SCREW[screw]
    out = []
    for x, y in points:
        out.append(cyl(s["clear"], depth_through + 2, z_top - depth_through - 1, x, y))
        out.append(cyl(s["head"] + 0.4, cb_depth + 1, z_top - cb_depth, x, y))
    return out


def teardrop_hole_y(d: float, length: float, x: float, z: float, y0: float) -> cq.Workplane:
    """Trou horizontal (axe Y) en goutte d'eau : imprimable sans support (z = haut)."""
    r = d / 2
    pts = []
    for i in range(0, 271, 10):
        a = math.radians(-45 - i)
        pts.append((x + r * math.cos(a + math.pi), z + r * math.sin(a + math.pi)))
    pts.append((x, z + r * math.sqrt(2)))
    wp = cq.Workplane("XZ", origin=(0, y0, 0)).polyline(pts).close().extrude(-length)
    return wp


# ---------------------------------------------------------------- mesures
def volume_cm3(shape) -> float:
    return abs(to_shape(shape).Volume()) / 1000.0


def bbox(shape):
    b = to_shape(shape).BoundingBox()
    return (b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax)


def outline_hull(*geoms, buffer: float = 0.0):
    g = unary_union(list(geoms)).convex_hull
    return g.buffer(buffer, quad_segs=16) if buffer else g


def circle2d(d: float, x=0.0, y=0.0, res=64):
    return Point(x, y).buffer(d / 2, quad_segs=max(8, res // 4))


def rect2d(cx, cy, w, h):
    return sbox(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def hull_solid(shape, tol=0.5, grow=0.0):
    """Enveloppe convexe d'une forme, en solide polyedrique (booleens rapides, degagement
    conservateur). `grow` : jeu supplementaire (mm) par homothetie autour du centre."""
    import trimesh
    sh = to_shape(shape)
    vs, tris = sh.tessellate(tol)
    pts = np.array([[v.x, v.y, v.z] for v in vs])
    hull = trimesh.Trimesh(pts, np.array(tris)).convex_hull
    if grow:
        c = hull.centroid
        ext = np.ptp(hull.vertices, axis=0).max() / 2.0
        hull.vertices = c + (hull.vertices - c) * (1.0 + grow / max(ext, 1e-6))
    faces = []
    for f in hull.faces:
        a, b, c3 = (cq.Vector(*hull.vertices[i]) for i in f)
        faces.append(cq.Face.makeFromWires(cq.Wire.makePolygon([a, b, c3], close=True)))
    solid = cq.Solid.makeSolid(cq.Shell.makeShell(faces))
    return cq.Workplane("XY").add(solid.fix())
