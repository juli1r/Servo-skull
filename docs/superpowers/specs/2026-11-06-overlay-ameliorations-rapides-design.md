# Overlay en jeu — 5 améliorations rapides

## Vue d'ensemble

Premier lot issu du brainstorm produit sur l'overlay en jeu (16 idées générées avec le compagnon
visuel de la skill `brainstorming`, triées par effort/impact). Ce spec couvre les 5 idées classées
"gains rapides" : des ajouts ciblés à `app/overlay.py` qui réutilisent les mécanismes déjà en
place (boutons de contrôle, dialogues, badge de statut, menu réglages) sans nouvelle dépendance
externe ni nouveau concept de données.

Chaque section ci-dessous est indépendante — elles peuvent être implémentées et livrées séparément
si besoin, mais partagent le même emplacement dans le code (overlay existant).

## 1. Annuler la dernière capture

**Comportement.** Un nouveau bouton dans la zone de contrôles de l'overlay, à côté du bouton de
capture manuelle. Au clic, il annule la capture la plus récente de la partie en cours — même effet
que choisir "Restaurer" avec le dossier de partie courant et la capture juste avant la dernière,
mais sans ouvrir le dialogue de sélection (`_restore_dialog`) : tout est déjà déterminé (partie en
cours = dossier courant, capture à annuler = la plus récente).

**UI.** Icône type "annuler"/flèche retour. Visible dès qu'il y a au moins une capture dans la
partie en cours ; grisé/masqué sinon (rien à annuler).

**Edge cases.**
- Partie sans aucune capture encore faite → bouton inactif.
- Deux clics rapprochés → le deuxième clic annule la capture précédente (celle qui était "la plus
  récente" juste avant le premier clic), pas d'effet cumulatif inattendu à gérer : chaque clic relit
  l'état courant au moment où il est traité.
- Aucune confirmation modale : l'action est répétable (on peut recapturer immédiatement après), pas
  besoin de ralentir le flux pendant une partie.

## 2. Notification Windows (toast) à chaque capture

**Comportement.** À chaque capture (automatique en fin de phase, ou manuelle), en plus du texte
discret déjà affiché dans l'overlay, une notification native Windows apparaît avec le round et le
score courant.

**UI / réglages.** Nouvelle case dans le menu réglages existant (`_open_settings_menu`), à côté des
cases "capture écran" et "stats anonymes" déjà présentes. Désactivée par défaut à la première
installation (cohérent avec les autres options opt-in du menu), activable à tout moment.

**Edge cases.**
- Si la case est désactivée, aucun toast n'est émis — seul le texte discret existant reste.
- Le toast ne doit pas voler le focus de la fenêtre active (important pendant une partie TTS en
  plein écran) : utiliser une notification système standard, pas une fenêtre qui prend le focus.

## 3. Bouton "basculer hôte/invité"

**Comportement.** Un bouton dans la zone de contrôles qui inverse le rôle hôte/invité actuellement
détecté pour la partie en cours. N'affecte aucune capture déjà enregistrée — seulement l'étiquetage
"qui est toi" / "qui est l'adversaire" pour les captures à venir à partir du moment du clic.

**UI.** Le badge de statut existant (`_render_badge`, anneau coloré vert=hôte connecté,
amber=invité) doit refléter le nouveau rôle immédiatement après le clic, sans attendre une nouvelle
capture.

**Edge cases.**
- Basculer en cours de partie ne retouche jamais l'historique déjà capturé (pas de ré-étiquetage
  rétroactif) — seulement les captures futures. C'est voulu : l'historique reflète ce qui a été vu
  au moment de la capture.
- Si la détection automatique se corrige elle-même ensuite (nouvelle capture avec détection
  différente), elle prévaut normalement sur le dernier état manuel — pas de verrou permanent après
  un basculement manuel.

## 4. Détection automatique de fin de partie

**Comportement.** Après une capture dont le round/score correspond à la fin de la mission active
(dernier round atteint, ou condition de victoire immédiate selon les règles connues de la mission),
une bannière apparaît proposant "Terminer la partie ?" avec deux actions, sur le même modèle visuel
que la bannière d'alerte existante ("Rattraper"/"Ignorer").

**UI.** Deux boutons : "Terminer" (déclenche le flux de fin de partie déjà existant dans l'overlay)
et "Pas encore" (ferme la bannière, ne redemande pas pour cette même capture).

**Edge cases.**
- Si l'utilisateur choisit "Pas encore" puis fait une capture supplémentaire qui correspond encore
  à une condition de fin, la bannière peut réapparaître (chaque capture est évaluée indépendamment).
- Mission inconnue ou règles de fin non déterminables automatiquement → pas de bannière (on ne
  propose la détection que quand la condition est fiable, pas d'heuristique approximative).

## 5. Marqueur "point à vérifier"

**Comportement.** Un raccourci clavier dédié et un bouton dans l'overlay permettent d'épingler un
timestamp sur la capture en cours, sans ouvrir de champ de texte ni interrompre le déroulement de
la partie.

**UI.** Dans le récap, ce marqueur apparaît comme un petit repère visuel (icône) sur la timeline du
round concerné, distinct des notes libres existantes — un repère "à vérifier après coup", pas une
note de contenu.

**Edge cases.**
- Peut être posé plusieurs fois dans le même round sans limite — chaque pose est un repère distinct
  sur la timeline.
- N'interagit pas avec le champ de note libre existant : les deux mécanismes coexistent (un
  marqueur n'empêche pas d'ajouter une note sur la même capture, et inversement).

## Hors scope

- **Mode tournoi multi-tables** (lier plusieurs parties de la même journée) : écarté de ce lot et
  du périmètre produit de l'overlay joueur en général. Servo-Skull overlay cible l'entraînement et
  le scrim 1v1 sur une seule table ; le suivi multi-tables est traité séparément dans un autre outil
  pensé pour un coach (voir brainstorm et spec dédiés, `2026-11-06-coach-multi-tables-design.md`).
- Les 10 autres idées issues du même brainstorm (import de liste, sauvegarde cloud, etc.) restent
  en attente de triage, hors périmètre de ce spec.

## Vérification

- Relecture de ce document juste après écriture : pas de placeholder, pas de contradiction entre
  sections, périmètre limité aux 5 idées + section hors-scope claire.
- Une fois ce spec approuvé par l'utilisateur, passage à la skill `writing-plans` pour transformer
  chacune des 5 idées (ou le lot complet) en plan d'implémentation concret sur `app/overlay.py`.
