"""FIGURINE PHOTO : une photo -> un buste imprimable, reconstruit par IA 3D sur la carte graphique du poste.

Moteur : TripoSG (licence MIT), detourage RMBG-1.4 (licence BRIA, non commerciale : a revoir avant toute vente).
Tout s'installe seul a la premiere utilisation, dans un environnement a part (plusieurs Go) : dossier SHW_IA, sinon
D:/SHW-IA si le disque existe, sinon sortie/ia. Il faut une carte NVIDIA avec 6 Go de memoire graphique libres.
Le maillage brut (gros et lent a calculer) est garde en cache par photo et variante : changer le format est instantane.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh

ICI = Path(__file__).resolve().parents[2]
NOWIN = 0x08000000 if sys.platform == "win32" else 0
DEPOT = "https://github.com/VAST-AI-Research/TripoSG.git"
PAQUETS = ["diffusers", "transformers", "einops", "huggingface_hub", "opencv-python", "trimesh", "omegaconf", "scikit-image", "scipy",
           "numpy<2", "peft", "jaxtyping", "typeguard", "pymeshlab", "accelerate", "kornia", "timm", "pillow"]


def _dossier() -> Path:
    if os.environ.get("SHW_IA"):
        return Path(os.environ["SHW_IA"])
    return Path("D:/SHW-IA") if Path("D:/").exists() else ICI / "sortie" / "ia"


# diso ne s'installe pas sous Windows : la surface est extraite avec scikit-image
_SURFACE = '''from skimage import measure as _sk


def surface_lisse(vol, sigma=1.0):
    from scipy import ndimage as nd
    trou = np.isnan(vol)
    idx = nd.distance_transform_edt(trou, return_distances=False, return_indices=True).astype(np.int32)
    vol = vol[tuple(idx)]
    del idx
    bande = np.percentile(np.abs(vol[~trou]), 50)
    vol = nd.gaussian_filter(np.clip(vol, -bande, bande) / bande, sigma)
    return _sk.marching_cubes(vol, 0.0)[:2]
'''


def _adapter_code(racine: Path):
    f = racine / "TripoSG" / "triposg" / "inference_utils.py"
    s = f.read_text(encoding="utf8")
    if "surface_lisse" in s:
        return
    s = s.replace("from diso import DiffDMC\n", _SURFACE)
    a, b = s.index("        dmc = DiffDMC("), s.index("        vertices = vertices / (2 ** octree_depth)")
    s = s[:a] + "        vertices, faces = surface_lisse(grid_logits.to(torch.float32).cpu().numpy())\n" + s[b:]
    f.write_text(s, encoding="utf8")


def _installer() -> tuple[Path, Path]:
    racine = _dossier()
    racine.mkdir(parents=True, exist_ok=True)
    exe = racine / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not (racine / "TripoSG").exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", DEPOT, str(racine / "TripoSG")], check=True, creationflags=NOWIN)
    if not exe.exists():
        subprocess.run([sys.executable, "-m", "venv", str(racine / "venv")], check=True, creationflags=NOWIN)
    if subprocess.run([str(exe), "-c", "import torch,diffusers,skimage,pymeshlab"], capture_output=True, creationflags=NOWIN).returncode:
        subprocess.run([str(exe), "-m", "pip", "install", "-q", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu124"], check=True, creationflags=NOWIN)
        subprocess.run([str(exe), "-m", "pip", "install", "-q", *PAQUETS], check=True, creationflags=NOWIN)
    _adapter_code(racine)
    return racine, exe


SCRIPT = r'''
import sys, os, numpy as np, torch, trimesh, pymeshlab
racine, photo, sortie, graine, pas = sys.argv[1:6]
os.chdir(os.path.join(racine, "TripoSG")); sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "scripts")]
if not torch.cuda.is_available():
    raise SystemExit("carte NVIDIA introuvable")
from huggingface_hub import snapshot_download
import triposg.models.autoencoders.autoencoder_kl_triposg, triposg.models.transformers.triposg_transformer, triposg.schedulers.scheduling_rectified_flow
from triposg.pipelines.pipeline_triposg import TripoSGPipeline
from image_process import prepare_image
from briarmbg import BriaRMBG
P = os.path.join(racine, "poids")
snapshot_download("VAST-AI/TripoSG", local_dir=P + "/TripoSG"); snapshot_download("briaai/RMBG-1.4", local_dir=P + "/RMBG")
r = BriaRMBG.from_pretrained(P + "/RMBG").to("cuda").eval()
img = prepare_image(photo, bg_color=np.array([1., 1., 1.]), rmbg_net=r); del r; torch.cuda.empty_cache()
pipe = TripoSGPipeline.from_pretrained(P + "/TripoSG").to("cuda", torch.float16)
o = pipe(image=img, generator=torch.Generator("cuda").manual_seed(int(graine)), num_inference_steps=int(pas), guidance_scale=7.0).samples[0]
ms = pymeshlab.MeshSet(); ms.add_mesh(pymeshlab.Mesh(o[0].astype(np.float64), np.asarray(o[1])))
ms.meshing_merge_close_vertices(); ms.meshing_decimation_quadric_edge_collapse(targetfacenum=500000, preservenormal=True)
m = ms.current_mesh(); trimesh.Trimesh(m.vertex_matrix(), m.face_matrix()).export(sortie)
'''


def maillage_ia(image: Path, graine: int, pas: int) -> Path:
    cle = hashlib.sha1(Path(image).read_bytes() + f"|{graine}|{pas}|v1".encode()).hexdigest()[:16]
    cache = ICI / "sortie" / "figurines"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{cle}.stl"
    if not f.exists():
        racine, exe = _installer()
        png = cache / f"{cle}.png"
        from PIL import Image
        Image.open(image).convert("RGB").save(png)
        r = subprocess.run([str(exe), "-c", SCRIPT, str(racine), str(png), str(f), str(graine), str(pas)],
                           capture_output=True, text=True, encoding="utf8", errors="replace", creationflags=NOWIN)
        if not f.exists():
            raise ValueError("Reconstruction IA impossible : " + (r.stderr or r.stdout)[-400:])
    return f


def figurine(image: Path, p: dict):
    import manifold3d as mf
    from atelier.noyau.c3d import vers_manifold, vers_trimesh, section
    g = lambda k, d: float(p.get(k, d)) if p.get(k) not in (None, "") else d
    m = trimesh.load(maillage_ia(image, int(g("variante", 42)), int(g("pas_ia", 50))), force="mesh")
    m.invert()
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))   # debout, regarde vers -Y
    parts = m.split(only_watertight=False)
    if len(parts) > 1:
        m = max(parts, key=lambda x: abs(x.volume))
    H, socle_h = g("hauteur", 110.0), g("socle", 6.0)
    m.apply_scale((H - socle_h) / m.extents[2])
    c = m.bounding_box.centroid
    m.apply_translation([-c[0], -c[1], socle_h - 0.5 - m.bounds[0][2]])
    corps = vers_manifold(m)
    Rx, Ry = m.extents[0] * 0.56 + 2, m.extents[1] * 0.60 + 2
    socle = mf.Manifold.cylinder(socle_h, 1.0, 0.985, 160).scale((Rx, Ry, 1))
    final = corps + socle
    nom = str(p.get("nom_socle") or "").strip()
    if nom:
        from atelier.produits.porte_cles import Style, glyphes
        from shapely.ops import unary_union
        from shapely import affinity
        t_ = unary_union(glyphes(nom, Style(police="gabriola", hauteur=10.0)))
        b = t_.bounds
        k_ = min((socle_h - 2) / (b[3] - b[1]), Rx * 1.1 / (b[2] - b[0]))
        t_ = affinity.scale(affinity.translate(t_, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2), -k_, k_, origin=(0, 0))
        pr = mf.Manifold.extrude(section(t_), 3.0).transform(np.array([[-1, 0, 0, 0], [0, 0, 1, -Ry - 1.0 + 0.5], [0, 1, 0, socle_h / 2]], float))
        final = final - pr
    res = vers_trimesh(final)
    return [res], {"noms": ["figurine"], "hauteur_mm": round(float(res.extents[2]), 1), "etanche": bool(res.is_watertight),
                   "volume_cm3": round(float(res.volume) / 1000, 1), "moteur": "TripoSG"}
