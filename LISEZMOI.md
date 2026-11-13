# Servo-Skull — le récap de tes parties 40K sur Tabletop Simulator

Un petit programme qui tourne **sur ton PC uniquement**. Il lit la table LCT pendant que tu joues, capture chaque tour (positions, PV, score, phase, cartes, capture d'écran) avec ton intention du moment, puis te génère un **récap de la partie** à revoir à froid.

Ton adversaire ne voit rien : aucune interface, aucun script ni objet n'est ajouté à la table. Le programme interroge TTS à la demande, en lecture seule. Seule **ta** caméra bouge, au moment où tu captures.

---

## Mac / Linux (beta)

Ces deux plateformes sont nouvelles et pas testées sur du vrai matériel — seule la CI confirme
que ça build, pas qu'elles tournent réellement en jeu. En particulier :
- **Lancement :** pas de `lancer.bat` ici. **Linux :** depuis le dossier où tu as extrait le zip,
  lance `./Servo-Skull/Servo-Skull` (si ça ne démarre pas, essaie d'abord `chmod +x Servo-Skull/Servo-Skull` —
  certains gestionnaires d'archives perdent le droit d'exécution). **Mac :** ouvre `Servo-Skull.app`.
- **Pas de raccourcis clavier F8/F9** sur Mac/Linux pour l'instant (ils sont encore affichés sur
  les boutons, ignore la mention) : utilise directement les boutons **Capturer**/**Fin de phase**
  dans l'overlay.
- Si Tabletop Simulator n'est pas détecté précisément, une bannière ambre apparaît dans l'overlay
  pour te prévenir que la capture se fait sur l'écran entier plutôt que juste sur TTS. **Sous Linux
  Wayland**, c'est pire que ça : la détection de fenêtre est impossible *et* le repli "écran entier"
  risque fort de ne rien capturer du tout (image noire). Ouvre une session **X11** (souvent listée
  "Ubuntu sur Xorg" à l'écran de connexion) pour que la capture fonctionne.
- Pas de mise à jour automatique en un clic sur Mac/Linux pour l'instant : télécharger la
  nouvelle version manuellement depuis la page Releases.
- **Mac uniquement** :
  - L'app n'est pas signée (pas de compte développeur Apple). Sur macOS 15 (Sequoia) et plus
    récent, le clic droit → Ouvrir ne suffit plus : va dans **Réglages Système → Confidentialité et
    sécurité**, et en bas de la page, clique **"Ouvrir quand même"** pour Servo-Skull (sur les
    versions plus anciennes, clic droit sur l'app → **Ouvrir** reste suffisant).
  - Pour que la capture d'écran fonctionne du tout, macOS doit t'autoriser explicitement :
    **Réglages Système → Confidentialité et sécurité → Enregistrement de l'écran**, active
    Servo-Skull. Comme l'app n'est pas signée par un vrai certificat, cette autorisation peut
    sauter à chaque mise à jour — si la capture ne montre plus que le fond d'écran, vérifie ce
    réglage en premier.
  - Le build fourni ne tourne que sur **Apple Silicon** (M1/M2/M3/...), pas sur les Mac Intel.
- **Linux uniquement** : le build est fait sur Ubuntu 24.04. Il peut refuser de démarrer sur des
  distributions avec une glibc plus ancienne (Ubuntu 22.04, Debian 12, Mint 21...) avec une erreur
  du type « GLIBC_... not found ». Dis-le sur Discord si c'est ton cas.

Un souci à signaler ? Un message sur le Discord avec ton OS exact (version de macOS/distribution
Linux + compositeur X11/Wayland) aide beaucoup.

---

## Installation et mises à jour

- **Première fois :** double-clique sur **`lancer.bat`**. Il installe ce qu'il faut (Python 3.10+ requis), puis lance l'overlay. Les fois suivantes, il lance directement.
- **Mises à jour :** Claude modifie directement les fichiers de ce dossier. Tu fermes l'overlay et tu relances `lancer.bat`, rien d'autre.
- `build.bat` (facultatif) fabrique un `Servo-Skull.exe` autonome, une fois que tout fonctionne.

## En partie

Ordre : **TTS d'abord, l'exe ensuite** (`build.bat` ne sert qu'à l'installation).

1. Lance TTS, charge la table LCT en **hôte**. Mets TTS en *fenêtré sans bordure* et garde toujours la même taille de fenêtre : les captures d'écran resteront comparables.
2. Lance `lancer.bat` (ou l'exe) et choisis ta couleur.
3. **Première fois uniquement : bouton 🎥 Vue.** Chaque curseur (hauteur, inclinaison, rotation, décalages) bouge ta caméra TTS en direct. Cadre la table comme tu veux la revoir, puis **Enregistrer**. Chaque capture reprendra ensuite exactement ce cadrage, sur les deux couleurs (la vue est donnée du point de vue de ton camp).
4. Pendant la partie :
   - **F8** ou **Capturer** : ta caméra se place sur la vue enregistrée, puis capture d'écran + données + ton intention/ta note.
   - **Capture auto** à la fin de chaque Mouvement (les deux joueurs) et au lancement de la partie. Données seules : ta caméra ne bouge pas.
   - **Alerte** si un tour passe sans capture manuelle : bouton *Rattraper maintenant*.
5. **Terminer** : le récap s'ouvre dans ton navigateur.

Tout est rangé dans le sous-dossier `parties\<date>_<Rouge>-vs-<Bleu>\` :
`recap.html`, `game.json`, `captures\` (données + photos), `units\` (de quoi recréer les figurines).

## Le récap

- **Plan** : vue du dessus identique d'un tour à l'autre, ta zone en bas. Il montre les flèches de mouvement depuis la capture précédente, des croix pour les figurines retirées, un contour orange pour les unités blessées, les objectifs avec leur rayon de 3".
- **Capture d'écran** : la photo prise au même moment (captures manuelles).
- Panneau de droite : ton intention, ta note, les pertes depuis la capture précédente, le score par round (survole pour le détail primaire/secondaire), les PC, les cartes et les réserves.
- Clavier : `←` `→` pour naviguer, `Espace` pour la lecture, `M` pour les flèches, `S` pour basculer plan/photo.
- Si les couleurs des figurines sont inversées : bouton **Inverser camps**.

## Restaurer un tour dans TTS (replay 3D)

Bouton **Restaurer…**, puis choisis la partie et la capture. Les figurines sont remises en place avec leurs PV. Les figurines mortes depuis sont recréées, celles qui n'existaient pas encore sont rangées hors table.
⚠️ Ça déplace les figurines de la table ouverte. Fais-le sur une partie chargée exprès pour l'analyse, jamais en plein match.

## Mode invité (quand tu n'héberges pas)

TTS n'exécute les scripts que chez l'hôte. Le programme le détecte et bascule en mode invité : capture d'écran et note seulement. Pas de positions, pas de round/score, pas de détection de tour, pas de restauration.

## Réglages (`config.json`, à côté de l'exe)

| Clé | Rôle | Défaut |
|---|---|---|
| `camera_distance`, `camera_pitch`, `camera_yaw_offset`, `camera_target_x/z` | La vue fixe : à régler avec le bouton 🎥 Vue plutôt qu'à la main | 70 / 90 / 0 / 0 |
| `camera_settle_s` | Délai entre le mouvement de caméra et la photo | 0.9 |
| `fixed_camera` | `false` = photo de ta vue telle quelle, sans bouger la caméra | true |
| `hotkey` | Raccourci de capture (`f8`, `ctrl+shift+c`…) | f8 |
| `auto_capture_after_movement` | Capture auto en fin de Mouvement | true |
| `alert_scope` | `all` = alerte sur tous les tours, `mine` = seulement les tiens | all |
| `stale_minutes` | Délai sans aucun mouvement ni jet de dés avant l'alerte « partie en pause » | 7 |
| `replays_dir` | Dossier des parties | `parties` à côté du programme |
| `red_positive_z` | Côté Rouge de la table (à inverser seulement si le plan est à l'envers) | true |

## Limites connues

- **Testé contre un simulateur de TTS** qui rejoue ta vraie sauvegarde LCT, pas encore dans TTS lui-même. Prévois une première partie de rodage.
- Après une capture manuelle, **ta caméra reste en vue du dessus** : TTS ne permet pas de lire la position de caméra pour la restaurer.
- La capture auto dépend du **bouton de phase** du mod. Si vous sautez directement au tour suivant, il n'y a pas de capture « fin de Mouvement » pour ce tour.
- Le port 39998 ne peut servir qu'à un seul outil : ferme l'extension TTS de VSCode/Atom si elle est ouverte.
- Les camps des figurines sont déduits de la règle d'armée (ex. *Oath of Moment* / *Prioritised Efficiency*) et des positions. En partie miroir (même armée), seules les positions servent : vérifie le 1er plan.
