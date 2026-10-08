# SHW 3DLAB — by SHWork (Super High Work)

Atelier 3D local pour la Creality K2 SE : création 3D façon Tinkercad (en mieux), keycaps, pièces mécaniques
paramétriques, projets (ServBuddy, SHWork 190 SE, compresseur Wankel…), tranchage CuraEngine et impression.

## Installer (une seule fois)

1. Télécharge **`setup/SHW3DLAB_Setup.exe`** et lance-le.
2. Il installe tout seul : Git et Python 3.12 (via winget si absents), le code, les dépendances, UltiMaker Cura
   (tranchage), puis crée le raccourci **SHW 3DLAB** sur le bureau et dans le menu Démarrer.

Installation dans `%LOCALAPPDATA%\SHW3DLAB\app`. Relancer le setup = réparer / mettre à jour l'installation.

## Utiliser

Lance **SHW 3DLAB** : au démarrage, s'il y a une mise à jour sur GitHub, une fenêtre affiche
« Téléchargement dernière MAJ vX » + le changelog, puis l'app s'ouvre sur <http://localhost:8890>.
Une icône **SHW** reste dans la zone de notification : *Ouvrir le dashboard*, *Vérifier les mises à jour*,
*Arrêter SHW 3DLAB*.

## Contribuer (Steven + Hugo)

Chaque `git push` sur `main` = mise à jour pour tout le monde au prochain lancement.

- Écris des messages de commit clairs : **ce sont eux qui s'affichent dans le changelog**.
- Modifs en cours non commitées : la mise à jour auto est sautée (jamais d'écrasement de ton travail).
- `requirements.txt` modifié → les dépendances sont réinstallées automatiquement chez tout le monde.
- `setup/installer.py` modifié → le setup de tout le monde évolue aussi (l'exe le télécharge à chaque lancement).
- Ne versionne jamais `sortie/` ni `data/projets/` (données de chaque machine, déjà dans `.gitignore`).

Version affichée : `v1.<nombre de commits>`.

## Sécurité imprimante

Aucune commande n'est envoyée à l'imprimante sans un clic explicite + confirmation dans l'interface.
