"""Assemblage du porte-serviette : crochets places dans leurs mortaises (controle + rendu)."""
import numpy as np


def poser_crochets(pcs, g, p_b=None):
    p_b = p_b or g["b"]
    """Crochet modelise a plat (x = avancee hors du mur, y = vertical, z = largeur) -> repere plaque
    (X = largeur, Y = vertical, Z = hors du mur). Rotation propre (det = +1) : X' = -z, Y' = y, Z' = x."""
    out = []
    for xc in g["xs"]:
        c = pcs["crochet"]
        T = np.array([[0, 0, -1, xc + p_b / 2], [0, 1, 0, g["y_cr"]], [1, 0, 0, 0], [0, 0, 0, 1]], float)
        out.append(T)
    return out


def interferences(pcs, g, p_b=None):
    p_b = p_b or g["b"]
    import cadquery as cq
    vols = []
    for xc in g["xs"]:
        # meme transformation que poser_crochets : rotation -90 deg autour de Y puis translation
        c = pcs["crochet"].rotate((0, 0, 0), (0, 1, 0), -90).translate((xc + p_b / 2, g["y_cr"], 0)).val()
        vols.append(round(pcs["plaque"].val().intersect(c).Volume(), 2))
    return vols
