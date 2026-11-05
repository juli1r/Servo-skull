# Servo-Skull

Le « récap » de tes parties de Warhammer 40K (11e) sur **Tabletop Simulator** : capture automatique de chaque phase (positions, PV, score, cartes), puis un récap HTML à revoir à froid et un GIF de la partie à partager.

Il tourne **sur ton PC uniquement** : rien n'est ajouté à la table, ton adversaire ne voit rien.

> **Version bêta.** Testé jusqu'ici sur une seule configuration (table LCT, 11e édition, Windows, joueur hôte). Des bugs sont probables : voir « Si ça ne marche pas ».

## Ce qu'il faut
- **Windows**
- **Tabletop Simulator** avec la table **LCT** (11e édition)
- **Être l'hôte** de la partie : TTS n'exécute les scripts que chez l'hôte. En invité, il ne reste que les captures d'écran et la saisie manuelle.
- Si l'extension TTS de VSCode/Atom est ouverte, ferme-la : le port 39998 ne peut servir qu'à un seul outil.

## Installer
1. Décompresse le zip **dans un dossier à toi** (Documents, Bureau…), pas dans « Programmes ».
2. Ouvre le dossier `Servo-Skull` et lance **`Servo-Skull.exe`**.
3. Windows peut afficher « Windows a protégé votre PC » (le programme n'est pas signé) : *Informations complémentaires* puis *Exécuter quand même*. Certains antivirus peuvent aussi le signaler à tort : il lit une touche de raccourci, capture l'écran et parle à TTS en local.

## Utiliser
Lance **TTS d'abord**, charge la table, puis Servo-Skull. Le guide détaillé (vue caméra, raccourci F8, mode invité, restauration d'un tour…) est dans [`LISEZMOI.md`](LISEZMOI.md).

Les parties sont rangées dans le dossier `parties` à côté du programme, avec un `recap.html` et un GIF par partie.

## Si ça ne marche pas
Envoie à celui qui t'a donné le logiciel le fichier **`servo-skull.log`** (à côté du programme) et dis ce que tu faisais. Il contient les noms des joueurs et des unités de ta partie, rien d'autre de personnel.

## Données de jeu
Les contours des layouts viennent du **Event Companion** de Games Workshop. Ce logiciel est un outil de fans, sans lien avec Games Workshop. Ne republie pas les documents officiels.

## Développement
- Lancer depuis les sources : `lancer.bat` (Python 3.10+).
- Construire le paquet à partager : `empaqueter.bat` (génère `release\Servo-Skull-<version>-windows.zip`).
- Tests : `python tests/sim_phases.py`.
