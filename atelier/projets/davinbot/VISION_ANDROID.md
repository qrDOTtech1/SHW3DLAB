# DaVinBot → Android : fil rouge d'architecture

Le bras actuel est la **première brique** d'un androïde : 2 bras (modèles différents : un
« force » DSDM et un « précision/artiste »), 2 jambes, une tête bardée de capteurs, des gadgets
(drone, RC) et des add-ons pour les bras. Tout ce qu'on code maintenant doit s'y brancher sans
réécriture.

## 1. Règle d'or : chaque membre est un module autonome
- Un membre = un **ESP32-S3 local** (boucle temps réel 1 kHz : MKS SERVO42C, verrou, main, capteurs
  de contact) + une **API unique** (`davinbot/robot/api.py`). Le membre sait se protéger seul
  (butées, couple, chute de tension, perte de liaison → pose sûre).
- Le **cerveau** (PC / Jetson dans le torse) ne donne que des intentions : « prends l'outil H »,
  « saisis le gobelet ». Les modes (`modes.py`) tournent déjà contre cette API → aujourd'hui
  sur MuJoCo, demain sur le vrai bras, après-demain dans l'androïde.
- Bus : **CAN-FD** entre membres (robuste, déjà maîtrisé sur FRANCO/AutoBrain), Ethernet/WiFi
  pour la vidéo. Alimentation 24 V distribuée, 5 V local.

## 2. Couches logicielles
| Couche | Rôle | État |
|---|---|---|
| Firmware membre | asservissement, sécurité, EEPROM outils via pogo | à écrire (ESP32) |
| RobotAPI | move_to / move_linear / lock / grip / read_tool_id | **fait** (sim) |
| Modes | prendre/déposer outil, saisir, poser, peindre, mission | **faits**, en validation sim |
| Perception | tête : caméras stéréo, lidar, IR, temp, gaz, micros, HP | à venir |
| Cerveau | planif de tâches (LLM local Ollama) → suite de modes | à venir |
| Apprentissage | RL MuJoCo (env PettingZoo déjà là) pour affiner les modes | amorcé |

## 3. Tête capteurs (brouillon)
Stéréo 2× caméras global-shutter + 1 caméra IR/thermique (MLX90640), lidar 2D/3D (LD19 ou
Unitree L1), capteurs temp/humidité, gaz (SGP41 / MQ-x), réseau de 4 micros (localisation de
source) + HP, IMU. Cou 2 axes. Le calcul vision tourne sur le cerveau, la tête ne fait que capter.

## 4. Jambes
Même philosophie de réducteurs imprimés (cycloïdaux) mais moteurs brushless + FOC (le couple
d'un NEMA17 ne suffit pas à porter un corps). À étudier : quasi-direct-drive façon MIT Cheetah.

## 5. Add-ons de bras (via le changeur d'outils existant)
Le changeur (baïonnette + 6 pogo + EEPROM) est **déjà** le port d'extension : tout add-on
s'identifie tout seul. Idées : lanceur/dock de micro-drone, pince à ventouse, fer à souder,
scanner/caméra macro, lampe, stylo/pinceau (fait), perceuse légère, préhenseur souple.
Drone et RC : le bras peut les **lancer et les récupérer** (dock magnétique + pogo de recharge).
