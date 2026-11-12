# UX/UI du mode live — préparer la structure pour un futur panneau

*2026-11-12*

## Contexte

Le mode live (`site/live.html` + `site/live.js`) interroge Firestore toutes les 4s et réinjecte
le plan de table dans le même template que le récap final (`recap_template.html`), en masquant
volontairement tout le panneau d'analyse (récit, unités, score, ticks de phase) pour ne garder
que le plateau plein écran + une barre de lecture en bas (◀ ▶ lecture, "revenir en direct").

Un tiers (P@Tau, sur `servo-skull.benezech.net`) a construit une version parallèle hébergée sur
son propre serveur (API REST + SSE), consommant le JSON de session interne de Servo-Skull, avec
une UI plus riche : score, liste d'escouades, "dernier moment", frise par round. Ça a relancé la
question de l'UX du live actuel.

Après discussion (mockups comparatifs, cf. compagnon visuel), direction retenue : **ne rien
changer visuellement pour l'instant**, mais préparer le terrain pour qu'un panneau type
"score/escouades" puisse être branché plus tard sans réécrire `live.html`. Les autres pistes
(barre enrichie avec vrai titre/ticks de phase, token de lecture dans l'URL, panneau rempli tout
de suite) sont explicitement écartées de cette passe — elles pourront revenir dans une passe
suivante.

## Périmètre

**Dans le périmètre :** une seule chose — restructurer `site/live.html` en grid à deux colonnes
(plateau + colonne latérale réservée), colonne latérale vide et masquée (`hidden`) par défaut.
Aucun changement visuel, aucun changement de comportement.

**Hors périmètre (explicitement reporté) :**
- Remplir la colonne avec un vrai contenu (score, escouades, dernier moment...).
- Enrichir la barre de lecture avec le vrai titre/ticks de phase du template plutôt que le
  label texte actuel (`refreshLiveLabel`).
- Token de lecture (`?l=...`) pour les liens privés.
- Tout changement d'architecture (SSE vs Firestore).
- Intégration Cogitator — sujet suivant, traité après cette passe.

## Design

### Structure HTML/CSS

`site/live.html` a aujourd'hui une colonne verticale simple (`header`, `#empty`, `#frame`
iframe, `#livebar`). On introduit un conteneur `#stage` autour de l'iframe :

```html
<div id="stage">
  <iframe id="frame" hidden></iframe>
  <aside id="sidePanel" hidden></aside>
</div>
```

```css
#stage{flex:1;display:grid;grid-template-columns:1fr;min-height:0}
#stage.has-panel{grid-template-columns:1fr minmax(260px,340px)}
#sidePanel{border-left:1px solid var(--border);overflow:auto}
```

- `#sidePanel` reste `hidden` et `#stage` ne reçoit jamais la classe `has-panel` dans cette passe :
  le rendu est identique à l'existant, pixel pour pixel.
- `#frame` passe de `flex:1` (actuel) à occuper la cellule de grid `1fr` — comportement équivalent.
- La barre `#livebar` reste en dehors de `#stage`, pleine largeur sous la grid, inchangée.

### Pourquoi une grid plutôt que du flex

Le flex actuel (`body{display:flex;flex-direction:column}`) suffit pour une seule colonne, mais
ajouter une colonne latérale plus tard demanderait de réorganiser le markup à ce moment-là. La
grid posée maintenant (avec une classe `has-panel` à ajouter/retirer en JS le jour venu) rend ce
changement futur trivial : brancher du contenu dans `#sidePanel` et poser la classe, sans toucher
au reste de la page ni à `live.js`.

### Pas de changement JS

`live.js` n'est pas touché : il continue de manipuler `#frame` exactement comme avant. Le futur
remplissage de `#sidePanel` (quand on le fera) sera un ajout isolé, pas une modification de la
logique de poll/rendu existante.

## Vérification

Pas de comportement nouveau à tester fonctionnellement — c'est un changement de structure
invisible. Vérification : charger `site/live.html?code=local` (via
`app/gen_local_live_payload.py`) dans le navigateur intégré avant/après le changement et comparer
visuellement (capture d'écran) qu'il n'y a aucune différence.
