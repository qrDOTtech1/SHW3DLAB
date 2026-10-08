"""Execute UN outil lourd de Creation 3D dans un processus separe (le serveur reste reactif ; un calcul trop
long est tue par le delai du parent). Usage : python -m atelier.c3d_worker entree.ply sortie.ply outil params_json"""
import json
import sys

import trimesh

from atelier import c3d


def main():
    entree, sortie, outil, params = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
    m = trimesh.load(entree, force="mesh", process=False)
    fn = {"arrondir": lambda: c3d.arrondir(m, float(params.get("r", 1.5))),
          "epaissir": lambda: c3d.epaissir(m, float(params.get("e", 1))),
          "coque": lambda: c3d.coque(m, float(params.get("paroi", 2)), bool(params.get("ouverture", False))),
          "lisser": lambda: c3d.lisser(m)}[outil]
    try:
        fn().export(sortie)
    except ValueError as e:
        print("ERREUR:" + str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
