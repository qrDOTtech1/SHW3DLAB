# DaVinBot V2 : phase 3 NEMA

Moteurs : J1 (30,6:1), J2 M1 (90:1), J3 M1 (90:1). Vitesses maxi : 118, 40 et 40 deg/s.

## Ordre de fabrication
1. Socle + J1 + tourelle (groupes BASE, J1, TOURELLE, environ 950 g) : banc d'essai du 1er moteur.
2. J2 sans `J2_pignon_M2`, puis bras et ressort.
3. J3 sans `J3_pignon_M2`, puis coude.
4. Avant-bras, poignet, J4 a J6 avec leurs bloqueurs.

## Piece retiree -> remplacement
- `Jx_nema17` + `Jx_pignon_moteur` (J4, J5, J6) -> `Jx_bloqueur`, 4 vis M3 x 8 dans les trous du NEMA.
  Reorienter : devisser, tourner l'axe, revisser.
- `J2/J3_nema17_M2` + `pignon_M2` : le cliquet d'origine tient la roue M2 (servo a 0 deg).

## A valider au banc avant de charger le bras
- Le cliquet tient bien la roue M2 sans glisser, dans les deux sens de charge.
- Ressort J2 : regle pour le bras complet, plus lourd de 2,1 kg. Estimation a la main : il surcompense d'environ 5 N.m
  a vide (le bras tend a monter), couple dispo 21,8 N.m. A verifier a la mise en service, le detendre si besoin.
- Couples du tableau calcules avec le bras complet : marge reelle au moins egale sur J3, a confirmer par pesee.
