# Confidentialité — Servo-Skull

*Brouillon à relire avant toute collecte réelle. Les champs entre crochets sont à compléter par l'éditeur du projet.*

## En une phrase
Servo-Skull fonctionne entièrement sur ton PC. **Rien n'est envoyé automatiquement.** Si tu l'acceptes, il peut créer un
fichier anonyme de ta partie, que tu relis et que tu choisis (ou non) de partager.

## Qui est responsable
[Nom ou pseudo de l'éditeur] — contact : [adresse e-mail dédiée au projet].

## Ce qui est créé, et seulement si tu as coché la case
À la fin d'une partie, un fichier `contribution.json.gz` (et une copie lisible `contribution.json`) est écrit dans le
dossier de la partie, sur ton PC. Il contient :
- les unités présentes (nom de l'unité, camp A ou B), le nombre de figurines et leurs positions sur la table ;
- la mission, les cartes, le plan de table et les scores par tour ;
- le mois de la partie, le mode (hôte ou invité) et la version du logiciel ;
- un identifiant de partie tiré au hasard, qui sert uniquement à retrouver ou supprimer cette partie plus tard.

## Ce qui n'y est jamais
Les pseudos (remplacés par « Joueur A / Joueur B »), les captures d'écran, les noms de dossier, les liens, les
horodatages précis, les notes et libellés saisis, les identifiants de tes objets TTS, toute information sur ton PC.
Le logiciel vérifie avant écriture qu'aucun pseudo de la partie n'apparaît dans le fichier, et refuse l'export sinon.

## Ton adversaire
Son pseudo n'apparaît jamais. Seules ses unités et leurs positions figurent dans le fichier, sous la mention « Joueur B ».

## Finalité et base légale
Finalité : constituer des statistiques anonymes sur les parties de Warhammer 40K pour améliorer les outils de la
communauté. Base légale : ton consentement, libre (le logiciel marche pareil sans), donné par une case à cocher
décochée par défaut, retirable à tout moment.

## Envoi (second accord, distinct du fichier local)
À la fin d'une partie, si un serveur est configuré et que tu n'as pas déjà répondu, Servo-Skull te demande si tu veux
**envoyer** le fichier : « cette partie », « celle-ci et les suivantes » ou « ne pas envoyer » (trois choix de même poids),
avec un bouton pour ouvrir le fichier avant de décider. Tu peux changer d'avis avec la case à cocher de l'écran de partie.
Sans accord, rien ne part. L'envoi se fait vers une base Google Firebase (Firestore) hébergée en Europe (région Firestore « eur3 »),
en écriture seule : les applications peuvent déposer une partie mais pas relire celles des autres.
Les parties envoyées ne sont reliées à aucun compte ni à aucun autre service du même éditeur.

## Conservation, suppression
Durée de conservation prévue : [24 mois] après réception. Pour retirer une partie déjà partagée, écris à [contact] avec
l'identifiant de la partie (champ `id` du fichier). Le fichier sur ton PC t'appartient : supprime-le quand tu veux.

## Tes droits
Accès, suppression, retrait du consentement : [contact]. Réclamation possible auprès de la CNIL (cnil.fr).

## Jeu et propriété intellectuelle
Warhammer 40,000 est une marque de Games Workshop. Servo-Skull est un outil de fans, non officiel.
