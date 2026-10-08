# atelier/ — le moteur de SHW 3DLAB

```
atelier/
├── meca.py              CATALOGUE : point d'entrée de toutes les pièces et projets (schéma d'interface + générateur)
├── noyau/               le LAB : utilisé par tout le monde — y toucher fait évoluer tous les projets
│   ├── c3d.py               géométrie (booléens, formes, vase, intégrer, effets…)
│   ├── c3d_worker.py        outils lourds en sous-processus
│   ├── rendu.py             rendus MuJoCo (vérifications visuelles)
│   ├── slicer.py            tranchage CuraEngine (K2 SE)
│   ├── logo.py              logo SHWork vectorisé (gravure, relief, icônes)
│   ├── image2d.py · objets.py · motifs.py · emballage.py · lignes.py · retouches.py · poncage.py · assemblage_ps.py
├── produits/            le catalogue « boutique » : porte-clés, jetons, keycaps, porte-serviette
└── projets/             un dossier par projet, ses versions côte à côte
    ├── servbuddy/           v1.py (archive) · v2_2.py (carénages vissés) · v2_3.py (sans visserie, actuelle)
    ├── shwork190/           carrosserie.py (découpe 190 E) · chassis.py (tubulaire + suspension active)
    ├── compresseur/         wankel.py · sim_wankel.py
    └── vibedeck/            vibedeck.py
```

## Règles de rangement

- **Nouveau projet** → `projets/<nom>/` + une entrée dans `meca.py` (`CATALOGUE[...]`, cat `"Projets"`) et dans `_FAMILLES`
  (famille, version, archive, icône) : il apparaît tout seul dans l'onglet Projets, rangé dans sa famille.
- **Nouvelle version** d'un projet → nouveau fichier `vX_Y.py` à côté de l'ancien (on ne casse jamais une version
  publiée) ; l'ancienne passe `archive=True` dans `_FAMILLES`.
- **Outil utile à plusieurs projets** → `noyau/` (et non dans le projet).
- Imports **absolus** (`from atelier.noyau.c3d import ...`), chemins vers la racine du dépôt via
  `Path(__file__).resolve().parents[N]`.
- Les calculs longs d'un projet passent par `_cache_projet` (meca.py) : résultat gardé dans `sortie/cache_projets`.
