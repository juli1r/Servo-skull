# Export du "film" de partie pour import dans Cogitator

*2026-11-12*

## Contexte

Discussion de suivi après la passe UX/UI du mode live (`2026-11-12-live-ux-design.md`) : le lien
"Servo-Skull ↔ Cogitator" existant aujourd'hui (`app/cogitator_export.py`) n'exporte que le score
(`resume-cogitator.json`), à importer manuellement par le joueur dans l'onglet Résultats/Vox d'un
event Cogitator. Le besoin exprimé va plus loin : pouvoir uploader la partie capturée par
Servo-Skull dans un event d'équipe Cogitator, pour que l'équipe puisse ensuite **consulter le
film de la game** (pas juste le score).

Recherche préalable (sur les deux dépôts) :
- Servo-Skull a déjà un payload canonique pour ça : `recap.collect(session)` (`app/recap.py:888`),
  utilisé à la fois pour générer `recap.html` et pour le push du mode live
  (`app/live_share.py:push()`). Il contient tout ce qu'il faut pour rejouer une partie (terrain,
  objectifs, unités, score par tour) — le plateau est redessiné en vecteur, pas de capture d'écran
  nécessaire.
- Cogitator n'a **aucune porte d'écriture anonyme** : son `firestore.rules` exige
  `request.auth != null` + appartenance à l'équipe (`isTeamMember(teamId) || isAdmin()`) pour tout
  ce qui touche `teams/{teamId}/**`. Rien dans son modèle de données (`Result`, `Event`,
  `VoxEntry`) n'a de champ pour attacher un fichier/replay, et Firebase Storage n'est même pas
  câblé côté Cogitator (pas de dépendance `firebase_storage`, aucun flux d'upload existant).
- `docs/DONNEES.md` (Servo-Skull) anticipait déjà ce besoin : *"Les parties ne sont jamais reliées
  aux comptes, équipes ou ligues de Cogitator. Si un jour des parties doivent alimenter des
  scrims, ce sera un autre flux, avec un accord explicite au moment de lier."* — c'est ce flux.

Trois approches ont été comparées (connexion directe de Servo-Skull à un compte Cogitator ;
upload automatique via une nouvelle Cloud Function passerelle ; export + import manuel). La
troisième est retenue : c'est la seule qui ne crée aucune nouvelle porte d'écriture non
authentifiée côté Cogitator, et elle prolonge directement le geste manuel déjà en place
aujourd'hui avec `resume-cogitator.json`.

## Périmètre

**Dans le périmètre de cette implémentation (Servo-Skull, maintenant) :** produire, en fin de
partie, un fichier `film-cogitator.json.gz` prêt à être importé manuellement, à côté de
`recap.html` et `resume-cogitator.json`.

**Hors périmètre (reporté à une implémentation séparée, côté dépôt Cogitator) :**
- L'écran "Importer le film" dans Cogitator (sélection de fichier, upload Firebase Storage).
- Le nouveau champ sur `Result` pointant vers le film stocké.
- Les règles Storage/Firestore côté Cogitator pour ce nouveau chemin.
- L'affichage du film (réutilisation prévue de `recap_template.html` tel quel, en `srcdoc`, comme
  `site/live.js` le fait déjà).
- Toute automatisation de l'upload (approche B, upload automatique via Cloud Function) — peut
  être reconsidérée plus tard si le geste manuel s'avère trop frictionnel, mais n'est pas ce
  qu'on construit ici.

## Design

### Contenu du fichier

`film-cogitator.json.gz` = `gzip(json.dumps(recap.collect(session)))`, avec trois champs retirés
du dict avant sérialisation :

- `ttsSaves` — références à des sauvegardes TTS locales, inutiles hors de la machine du joueur.
- `screenshot` dans chaque entrée de `captures` — chemin d'image local.
- `folder` — nom du dossier local de la partie.

Vérifié dans `app/recap_template.html` : ces trois champs ne pilotent que des fonctionnalités
strictement locales qui se dégradent déjà proprement en leur absence —
`replayInTTS()` (`recap_template.html:926`) retourne immédiatement si `D.folder` est absent, et
l'affichage du bouton capture d'écran se masque déjà si aucune capture n'a de `screenshot`
(`recap_template.html:941`). **`recap_template.html` n'a besoin d'aucune modification.**

Pas d'anonymisation au-delà de ce retrait : les noms de joueurs restent en clair (comme
`resume-cogitator.json` aujourd'hui) — contrairement à `app/contribution.py`, ce fichier est
destiné à être relu par l'équipe elle-même, qui se connaît déjà dans Cogitator.

### Où et quand il est écrit

Nouvelle fonction `export_film(session) -> Path | None` dans `app/cogitator_export.py` (à côté de
`export()`, qui reste inchangée pour le score). Écrit `film-cogitator.json.gz` dans
`session.dir`. Condition d'écriture, volontairement différente de `export()` : le film est écrit
dès que `recap.collect(session)["captures"]` est non vide, indépendamment de la présence d'un
score — contrairement au score résumé, le film garde sa valeur même pour une partie interrompue
ou sans score final renseigné. Si `captures` est vide, retourne `None` sans rien écrire.

Appelée dans `app/controller.py`, juste à côté de l'appel existant à `cogitator_export.export()`
(ligne ~244, dans le flux de fin de partie, après `recap.build(self.session)`), avec la même
gestion d'erreur non bloquante déjà en place : écrire `cogitator-film-erreur.txt` dans
`session.dir` en cas d'exception, sans interrompre la fin de partie.

### Taille

Pas de plafond de taille imposé (contrairement à `live_share.push()` qui plafonne à 500 Ko à
cause de la limite de document Firestore) : ce fichier est un fichier local, pas poussé vers
Firestore. `recap.collect()` contient déjà l'intégralité de la partie (toutes les captures), donc
sa taille gzippée croît avec le nombre de tours mais reste dans le même ordre de grandeur que ce
qui est déjà poussé en mode live à chaque capture.

### Confidentialité

Aucun envoi automatique : le joueur choisit explicitement d'importer ce fichier précis dans son
event Cogitator (geste manuel, cohérent avec `docs/DONNEES.md`). Rien à ajouter au mécanisme de
consentement existant (`envoi` dans la config) puisque ce fichier n'est jamais transmis par
Servo-Skull lui-même.

## Vérification

- Lancer une partie de test, la terminer, vérifier la présence de `film-cogitator.json.gz` dans
  le dossier de session à côté de `recap.html` et `resume-cogitator.json`.
- Décompresser le fichier et vérifier par inspection JSON que `ttsSaves`, `folder` et tous les
  `captures[].screenshot` sont absents, et que `squadNames`, `players`, `captures[].units`,
  `mission` sont bien présents.
- Charger ce JSON décompressé dans le gabarit (`recap_template.html` avec `/*__DATA__*/`
  remplacé manuellement, ou via une petite extension de `app/gen_local_live_payload.py` pour ce
  test) dans le navigateur intégré, et confirmer que le plateau, le score et la frise de rounds
  s'affichent normalement, sans erreur console liée aux champs retirés.
- Vérifier le cas d'erreur : simuler un échec dans `export_film` (ex. dossier en lecture seule) et
  confirmer que `cogitator-film-erreur.txt` est écrit et que la fin de partie n'est pas bloquée.
