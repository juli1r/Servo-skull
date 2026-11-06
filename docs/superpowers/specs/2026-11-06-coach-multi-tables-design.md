# Suivi multi-tables pour coach — Design

*2026-11-06*

## Contexte

Lors d'un brainstorm précédent sur l'évolution de l'overlay Servo-Skull, une idée écartée ("mode
arbitre" intégré à l'overlay d'un joueur pour suivre plusieurs tables) a été recadrée en un besoin
distinct : un **coach d'équipe** qui veut suivre plusieurs tables à la fois pendant une session de
scrim d'équipe, depuis un poste séparé — pas depuis l'overlay d'un joueur.

Ce document spécifie un **produit web séparé**, indépendant de Servo-Skull dans son infrastructure
(projet Firebase propre), mais dont le design s'inspire fortement de l'architecture et du design
system de [Cogitator](../../../../Cogitator) (`C:\Users\Megaport\Documents\Claude\Projects\Cogitator`)
— un outil existant pour équipes compétitives Warhammer qui a déjà, dans son modèle de domaine, un
rôle `coach` en lecture étendue et un module `Vox` de suivi live par table (actuellement saisi
manuellement par le capitaine, pas automatique). Ce document ne fusionne pas les deux produits —
cette question est explicitement reportée.

**Dès ce document, le produit cible les deux contextes de scrim à égalité : virtuel (TTS, avec un
outil de capture comme Servo-Skull) et présentiel/IRL (sans outil de capture).** Ce n'est pas une
extension ajoutée après-coup au cas virtuel : la saisie manuelle (§2) est un canal de première
classe, pas un repli dégradé.

## Périmètre

**Dans le périmètre :** un coach d'équipe suivant, en lecture seule et en direct, les tables de
*sa propre équipe* pendant une session de scrim interne qu'il contrôle lui-même (ouverture/fermeture)
— que les parties soient jouées en virtuel (TTS) ou en présentiel.

**Hors périmètre (explicite) :**
- Mode tournoi / organisateur suivant des tables tenues par des inconnus.
- Fusion technique avec l'infrastructure Cogitator (Firestore, Vox, modèle de domaine) — piste à
  évaluer séparément, plus tard.
- Mode arbitre intégré à l'overlay d'un joueur (idée explicitement écartée en amont de ce document).

## 1. Comptes, équipes, sessions

- **Coach** : compte utilisateur. Dispose d'un lien d'invitation d'équipe permanent et stable.
- **Joueur** : crée un compte via ce lien d'invitation. Ce rattachement à l'équipe du coach est
  **permanent** — fait une seule fois, jamais à refaire pour une session future.
- **Session** : objet explicitement créé et clos par le coach (ex. "Scrim mardi 10/11"). Pendant
  la fenêtre où une session est ouverte, toute partie démarrée par un membre de l'équipe du coach
  s'y rattache automatiquement — aucune action du joueur pour "rejoindre" la session.
- **Table** : une partie en cours d'un joueur de l'équipe, rattachée à la session active. Identité
  d'une table = les deux joueurs (ou le joueur de l'équipe + son adversaire), pas un numéro de
  table physique saisi à la main.

## 2. Capture et remontée de l'état — virtuel (auto) et IRL (manuel)

Deux sources possibles pour l'état d'une table, également supportées et au choix selon le contexte
(TTS avec outil de capture, ou scrim en présentiel sans outil de capture) :

**Automatique** : côté joueur, l'outil qui suit sa partie (round, phase, score) pousse l'état
automatiquement dès que deux conditions sont réunies : le joueur est membre d'une équipe, et cette
équipe a une session ouverte. Aucun geste de partage explicite pendant la partie — contrairement au
mode spectateur actuel de Servo-Skull (`app/live_share.py`) qui nécessite un clic "Partager en
live" par partie.

**Manuelle (scrim IRL)** : en l'absence d'outil de capture (parties en présentiel), l'état d'une
table est saisi à la main, par l'un ou l'autre de ces deux canaux — aucun des deux n'est requis à
l'exclusion de l'autre, et les deux peuvent se relayer sur une même table au fil de la session :
- **Le joueur, depuis son téléphone** : mini-formulaire mobile (score, round/phase) qu'il met à
  jour à chaque changement — démarre lui-même sa table dans la session active.
- **Le coach, directement sur le tableau de bord** : édition rapide d'une carte en passant dans les
  allées, y compris pour créer une table que personne n'a encore démarrée côté joueur.

Dans les deux cas (auto ou manuel), chaque table transmet/reçoit à chaque mise à jour :
- Score des deux côtés.
- Round et phase en cours.
- Durée écoulée sur le round en cours (pour calculer le signal de retard, cf. §4) — en saisie
  manuelle, calculée depuis l'heure de la dernière mise à jour plutôt que remontée par l'outil.

Pas de transmission/saisie du détail du plan de table (positions d'unités) dans le flux "léger" du
tableau de bord — uniquement à la demande, lors du zoom sur une table (cf. §4), et uniquement
disponible en source automatique (rien à afficher en saisie manuelle).

## 3. Modèle de données (inspiré du Domain Model Cogitator)

Vocabulaire aligné avec `Cogitator/docs/DOMAIN_MODEL.md` pour faciliter un rapprochement futur,
sans réutiliser son infrastructure :

| Entité | Notes |
|---|---|
| `User` | Coach ou joueur, compte Firebase Auth. |
| `Team` | Équipe d'un coach. `ownerId` = coach. |
| `Membership` | Lie un `User` à une `Team`, `role: coach \| player`, permanent dès acceptation du lien d'invitation. |
| `Session` | Équivalent simplifié d'un `Event` Cogitator, mais sans notion de tournoi/format GW : `id`, `teamId`, `name`, `status: open \| closed`, `openedAt`, `closedAt`. |
| `TableState` | Une table en cours, rattachée à une `Session` : `sessionId`, `playerId`, `opponentName`, `score`, `round`, `phase`, `roundStartedAt`, `needsCoach: bool`, `source: auto \| player_manual \| coach_manual`, `updatedBy`, `updatedAt`. `source` ne verrouille rien : une même table peut passer de `coach_manual` (le coach l'a créée en passant) à `player_manual` (le joueur reprend la main sur son téléphone), `updatedBy` reflétant toujours le dernier à avoir écrit. |

Contrairement à `VoxTableEntry` (Cogitator), pas de détail primaire/secondaire par round ni de
conversion VP→GP : ce produit suit un score et un round, pas les règles de scoring compétitif GW.

## 4. Tableau de bord coach

**Vue d'ensemble** : grille de cartes, une carte par table active de la session (dimensionnée pour
5 à 10 tables simultanées).

Chaque carte affiche :
- Les deux joueurs, le score (typographie monospace, type Share Tech Mono).
- Round / phase en cours.
- Une **barre de rythme relatif** : temps écoulé sur le round en cours comparé au temps moyen
  observé sur les autres tables de la session. Passe en **rouge** (`--red #f87171`, sémantique
  "danger" du design system Cogitator — pas l'ambre, réservé à un usage "adversaire") quand une
  table dépasse significativement cette moyenne.
- Un indicateur "appel coach" si le joueur l'a déclenché (cf. §5), visible même sans dépasser le
  seuil de rythme.
- Un badge discret indiquant la source de la donnée (`auto`/`manuel`) — utile quand la session
  mélange des tables virtuelles et IRL.

Pas de miniature du plan de table dans la grille (jugé trop lourd à rafraîchir pour 5-10 tables ;
cf. alternative écartée en annexe).

**Édition par le coach** : sur une table `manual` (IRL), la carte s'ouvre en édition directe au
clic (score, round/phase) au lieu du zoom plein écran décrit ci-dessous — une table `manual` n'a
pas de plan de table à zoomer. Le coach peut aussi créer une nouvelle carte manuellement depuis la
grille (ex. table dont le joueur n'a pas encore ouvert son téléphone).

**Zoom (tables `auto` uniquement)** : clic sur une carte → vue plein écran de cette table, plan de
table complet en direct (reprend l'expérience du mode spectateur actuel `site/live.html`, mais sur
une table choisie depuis le tableau de bord plutôt que via un lien direct).

**Design visuel** : repris du design system Cogitator (`Cogitator/docs/UX_GUIDELINES.md`) —
fond `#080b10`, cartes `#0d1117`, texte principal `#e6edf3`/secondaire `#8b949e`, cyan `#38bdf8`
pour les informations joueur, rouge `#f87171` réservé aux alertes, typographie Barlow Condensed
(labels) + Share Tech Mono (valeurs numériques).

## 5. Signal "besoin du coach"

Trois canaux combinés, aucun n'exclut les autres :
1. **Auto-détecté** : la barre de rythme relatif (§4), basée sur le temps par round comparé à la
   moyenne de la session.
2. **Signalé par le joueur** : un bouton explicite côté joueur ("Appeler le coach"), qui lève
   `needsCoach` sur sa `TableState` — visible sur sa carte indépendamment du rythme.
3. **Jugement du coach** : le tableau de bord n'interprète jamais à la place du coach — score et
   round bruts restent toujours visibles, même sans alerte.

## 6. Debrief de session

À la clôture d'une session par le coach, un écran d'ensemble agrège les résultats de toutes les
tables de la soirée : qui a gagné/perdu par table, écarts de score, tables les plus longues — pour
lancer la discussion d'équipe. Pour les tables `auto`, ceci s'ajoute aux récaps individuels produits
indépendamment par l'outil de capture (ex. `app/recap.py` côté Servo-Skull), sans les remplacer. Pour
les tables `manual` (IRL), cet écran d'ensemble est le seul artefact de debrief disponible — il n'y
a pas de récap individuel détaillé à côté.

## Alternatives écartées

- **Liste triable sans plan de table** et **vue focus + bandeau de vignettes** : écartées au profit
  de la grille de cartes (plus lisible pour repérer vite une table en difficulté parmi 5-10).
- **Miniature du plan de table par carte** : écartée (coût de rafraîchissement trop élevé pour le
  nombre de tables visées) au profit de la barre de rythme relatif, suffisante comme signal.
- **Ambre pour l'alerte de retard** : écartée au profit du rouge, pour rester cohérent avec la
  sémantique du design system Cogitator (ambre = adversaires/attention, rouge = danger).
- **Mode arbitre dans l'overlay joueur** : écarté en amont de ce document (cf. Contexte) — usage
  réel rare, pas de sens de suivre plusieurs tables depuis son propre poste de jeu.
