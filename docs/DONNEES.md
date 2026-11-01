# Données d'une partie : inventaire, anonymisation, collecte

## Où sont les 200 Mo ?
Une partie pèse ~4 Mo de données utiles ; le reste est `sauvegardes-tts/` (copies des sauvegardes TTS, ~190 Mo,
utiles seulement pour rejouer un moment). La contribution anonyme, elle, fait **3 à 6 Ko compressés** par partie
(mesuré sur les 12 parties enregistrées : 36 Ko au total).

| Contenu | Poids typique | Personnel ? | Dans la contribution ? |
|---|---|---|---|
| `sauvegardes-tts/` | ~190 Mo | oui (pseudos, noms de listes) | non |
| `units/` (scripts du mod par figurine) | ~3 Mo | possible (surnoms) | non |
| `film.html`, `evolution-du-plan.gif` | ~4 Mo | oui (pseudos) | non |
| `game.json` (captures + pseudos) | ~160 Ko | oui | non, reconstruit |
| `captures/` | ~700 Ko | possible | non |
| Unités : nom, camp, effectifs, positions | quelques Ko | non | **oui** |
| Mission, cartes, plan de table, scores | < 2 Ko | non | **oui** |
| Pseudos, captures d'écran, horodatages précis, notes | — | oui | **non** |

## Anonymisation
`app/contribution.py` : pseudos → Joueur A / B, identifiants d'objets remplacés par des numéros, mois au lieu de la
date, positions arrondies au dixième de pouce, noms nettoyés (balises de couleur, longueur limitée, pseudos masqués).
Garde-fou : `leak()` refuse l'export si un pseudo ou le nom du dossier apparaît dans le résultat.

Limite connue : une liste d'armée très particulière + un mois précis peut ré-identifier quelqu'un dans un petit
milieu. D'où : consentement, mois et non jour, et pas de publication des fichiers bruts (seulement des agrégats).

## Pourquoi un identifiant de suppression
Un fichier 100 % anonyme (sans aucun identifiant) ne relève plus du RGPD, mais il est alors impossible de retirer
une partie à la demande. L'identifiant aléatoire permet la suppression ; en contrepartie le fichier est
« pseudonyme » et le RGPD s'applique : d'où le consentement et la page CONFIDENTIALITE.md.

## Hébergement : options pour la collecte (à vérifier au moment de choisir : tarifs et conditions changent)
1. **Sans serveur (recommandé au début)** : le joueur t'envoie `contribution.json.gz` (5 Ko) par message. Zéro
   infrastructure, zéro coût ; tenable jusqu'à quelques dizaines de parties.
2. **Supabase (offre gratuite, région UE)** : base + fonction d'envoi ; gratuit à cette échelle ; un projet inactif
   peut être mis en pause.
3. **Cloudflare Workers + R2/D1** : gratuit à cette échelle ; société américaine (cadre de transfert à documenter).
4. **Petit serveur français (OVH, Scaleway)** : quelques euros par mois, tout sous ton contrôle, plus de maintenance.
À éviter : un dépôt public (GitHub, Gist) comme boîte de dépôt, puisque tout y est lisible par tous.

## Étapes
1. Finalité écrite — fait. 2. Inventaire — fait. 3. Consentement — fait (fenêtre au premier lancement + case).
4–5. Adversaire et anonymisation — fait. 6. Pas d'envoi automatique — fait. 7. Hébergement — à choisir.
8. Suppression — procédure décrite, à outiller avec le serveur. 9. Politique — brouillon : CONFIDENTIALITE.md.
10. Test avec 3 à 5 amis — à faire. 11. Statistiques agrégées — après ~100 parties.

## Envoi vers Firestore (choisi : même compte Firebase que Cogitator, collection séparée `servoskull_contributions`)
- Code : `app/upload.py` (API REST, sans bibliothèque), appelé seulement après un accord explicite (réglage `envoi`).
- Règles de sécurité à AJOUTER (pas remplacer) : `docs/firestore.rules.txt` — création seule, format et taille vérifiés.
- Un document par partie, identifiant = identifiant aléatoire de la partie : renvoyer ne crée jamais de doublon.
- Lecture, export et suppression : `tools/export_contributions.py` (avec ton compte, jamais depuis l'application).
- Les parties ne sont jamais reliées aux comptes, équipes ou ligues de Cogitator. Si un jour des parties doivent
  alimenter des scrims, ce sera un autre flux, avec un accord explicite au moment de lier.
- Tests : `tests/verif_upload.py` (faux Firestore local : format, doublon, hors ligne, rien sans accord).
- Mise en service : renseigner `firebase.project_id` et `firebase.api_key` (clé web du projet, publique par nature)
  dans les réglages par défaut ; tant qu'ils sont vides, aucun écran d'envoi n'apparaît.
