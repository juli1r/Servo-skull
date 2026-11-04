# Règles impératives pour ce projet

Ces règles existent parce qu'elles ont déjà été violées en session malgré des rappels verbaux répétés. Elles s'appliquent sans exception, même sous pression ("go", "vas-y", "fais-le direct").

## 1. Plan obligatoire avant toute modification de code

Appeler `EnterPlanMode` avant le premier `Edit`/`Write` sur un fichier du projet, **y compris pour un fix ciblé déjà diagnostiqué**. Une urgence exprimée par l'utilisateur ("arrête de demander, corrige") porte sur le fait de ne plus s'arrêter pour poser des questions à chaque écart trouvé — jamais sur le fait de sauter le plan. En cas de doute : planifier quand même.

Si une question posée à l'utilisateur (AskUserQuestion ou autre) revient sans réponse exploitable ("pas de préférence", silence, réponse hors sujet) : ne JAMAIS interpréter ça comme un feu vert pour trancher seul. S'arrêter et reformuler la question en clair, en texte libre, jusqu'à obtenir une réponse réelle.

## 2. Hygiène git

- Committer l'état courant avant toute modification (checkpoint stable, permet de revenir en arrière).
- Ne jamais pousser sans confirmation explicite de l'utilisateur pour cette action précise (sauf instruction permanente contraire donnée explicitement par l'utilisateur pour ce projet).

## 3. Corriger les bugs immédiatement

Ne jamais reporter la correction d'un bug constaté "pour garder l'élan" d'autre chose en cours.

## 4. Commandes terminal données à l'utilisateur

Toujours complètes et autonomes (inclure le `cd` vers le dossier du projet si nécessaire) — jamais une commande partielle qui suppose un contexte déjà en place.

## 5. Ne jamais prendre le contrôle de l'écran/souris/clavier sans permission explicite et ponctuelle

Une approbation générale ("go", "c'est fini go !") ne vaut pas pour une nouvelle action de contrôle d'écran. Chaque prise de contrôle se redemande.
