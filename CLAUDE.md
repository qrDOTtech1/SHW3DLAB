# SHW 3DLAB : regles pour les sessions Claude

Steven et Hugo travaillent en meme temps, chacun avec sa session Claude, sur le meme depot.

- Lancer l'app : `Lancer SHW 3DLAB.bat` (dashboard http://127.0.0.1:8890). Structure : `atelier/README.md`.
- Avant de commencer : `git pull --no-rebase`. Ne jamais utiliser `git stash`, `--autostash`, `reset --hard`, `push --force`.
- La synchro de l'app tourne toutes les 2 min : elle commit `data/projets`, `data/images`, `data/bases` et pousse aussi tes commits.
  Ne committe pas ces dossiers a la main, sauf si l'utilisateur le demande.
- Petits commits frequents, poussés aussitot (`git pull --no-rebase`, puis `git push`), un sujet par commit. Annonce les fichiers que tu vas modifier.
- Avant de modifier un fichier partage (`atelier/meca.py`, `server/app.py`, `web/index.html`), fais un pull et garde la modification courte.
- Modifier un projet : editer `data/projets/<id>.json`, champ `donnees`. L'app ouverte l'applique toute seule en 2 s.
- Modifier le generateur d'un projet : creer une nouvelle version (`vX_Y.py`), garder l'ancienne en archive dans le catalogue.
- Code modifie : le bandeau "Nouveau code recu" de la fenetre Equipe recharge l'app.
- Imprimante : ne jamais envoyer de commande a la K2 SE (192.168.1.81). L'impression reste le bouton de l'utilisateur.
