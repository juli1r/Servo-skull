# Structure live.html prête pour un futur panneau — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructurer `site/live.html` en grid à deux colonnes (plateau + colonne latérale réservée, masquée) sans changer le rendu visuel actuel, pour qu'un futur panneau (score/escouades) puisse être branché plus tard sans réécrire la page.

**Architecture:** Ajout d'un conteneur `#stage` (CSS grid, une seule colonne active) autour de l'iframe existante, avec un `<aside id="sidePanel" hidden>` vide à côté. La classe `has-panel` (jamais posée dans ce plan) activera une deuxième colonne le jour où `#sidePanel` sera rempli. `live.js` n'est pas modifié.

**Tech Stack:** HTML/CSS statique (`site/live.html`), pas de build, pas de framework JS.

Spec de référence : `docs/superpowers/specs/2026-11-12-live-ux-design.md`.

---

### Task 1: Restructurer `site/live.html` (plateau + colonne réservée)

**Files:**
- Modify: `site/live.html:11-38`

- [ ] **Step 1: Générer un payload local pour voir le live avant modification**

Depuis `C:\Users\Megaport\Documents\Claude\Projects\Servo-Skull` :

```bash
cd C:\Users\Megaport\Documents\Claude\Projects\Servo-Skull
python app/gen_local_live_payload.py
```

Expected: affiche `site/local-payload.json généré depuis <dossier>` (nécessite au moins une
partie enregistrée dans `parties/`).

- [ ] **Step 2: Capturer le rendu "avant" dans le navigateur intégré**

Ouvrir `site/live.html?code=local` dans le navigateur intégré (preview_start avec un serveur
statique sur `site/`, ou ouvrir le fichier directement si le navigateur le permet), puis prendre
une capture d'écran de référence. Garder cette capture sous les yeux pour la comparaison du
Step 6.

- [ ] **Step 3: Modifier le CSS**

Dans `site/live.html`, remplacer la ligne 17 :

```css
#frame{flex:1;border:0;width:100%}
```

par :

```css
#stage{flex:1;display:grid;grid-template-columns:1fr;min-height:0}
#stage.has-panel{grid-template-columns:1fr minmax(260px,340px)}
#frame{width:100%;height:100%;border:0}
#sidePanel{border-left:1px solid var(--border);overflow:auto}
```

- [ ] **Step 4: Modifier le HTML**

Remplacer la ligne 31 :

```html
<iframe id="frame" hidden></iframe>
```

par :

```html
<div id="stage">
<iframe id="frame" hidden></iframe>
<aside id="sidePanel" hidden></aside>
</div>
```

- [ ] **Step 5: Relire le fichier complet**

Le fichier `site/live.html` doit maintenant ressembler à :

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Servo-Skull · live</title>
<style>
:root{--bg0:#080b10;--bg1:#10141e;--border:#2a3348;--t1:#dde3f0;--t2:#8e95a8;--coral:#ff6b47;--cyan:#38bdf8;--amber:#fbbf24;color-scheme:dark}
@media (prefers-color-scheme:light){:root{--bg0:#f0f2f5;--bg1:#ffffff;--border:#d4d8e0;--t1:#111827;--t2:#52586a;--coral:#e8562e;--cyan:#0c87c9;--amber:#9a6a00;color-scheme:light}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg0);color:var(--t1);font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;height:100vh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border);background:var(--bg1)}
header b{color:var(--coral);letter-spacing:.06em}
#status{color:var(--t2)}
#status.live{color:var(--cyan)}
#status.err{color:var(--amber)}
#stage{flex:1;display:grid;grid-template-columns:1fr;min-height:0}
#stage.has-panel{grid-template-columns:1fr minmax(260px,340px)}
#frame{width:100%;height:100%;border:0}
#sidePanel{border-left:1px solid var(--border);overflow:auto}
#empty:not([hidden]){flex:1;display:flex;align-items:center;justify-content:center;color:var(--t2);padding:24px;text-align:center}
#livebar{flex:none;display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;padding:10px 16px;border-top:1px solid var(--border);background:var(--bg1)}
#livebar button{flex:none;width:38px;height:38px;border:1px solid var(--border);border-radius:50%;background:var(--bg0);color:var(--t1);font-size:15px;cursor:pointer}
#livebar button:hover{border-color:var(--cyan)}
#livebar #bLivePlay{width:44px;height:44px;color:var(--cyan)}
#liveLabel{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;color:var(--t1)}
#livebar #bLiveNow{width:auto;height:auto;flex:none;margin-left:auto;padding:8px 14px;border:1px solid var(--cyan);border-radius:999px;background:transparent;color:var(--cyan);font:inherit;font-size:12px;white-space:nowrap;cursor:pointer}
#bLiveNow:hover{background:rgba(56,189,248,.1)}
</style>
</head>
<body>
<header><b>SERVO-SKULL · LIVE</b><span id="status">connexion…</span></header>
<div id="empty" hidden>Lien invalide ou partie pas encore partagée.</div>
<div id="stage">
<iframe id="frame" hidden></iframe>
<aside id="sidePanel" hidden></aside>
</div>
<div id="livebar" hidden>
  <button id="bLivePrev" title="Phase précédente" aria-label="Phase précédente">◀</button>
  <button id="bLivePlay" title="Lecture" aria-label="Lecture">▶</button>
  <button id="bLiveNext" title="Phase suivante" aria-label="Phase suivante">▶</button>
  <span id="liveLabel"></span>
  <button id="bLiveNow">⟳ Revenir en direct</button>
</div>
<script src="live.js"></script>
</body>
</html>
```

- [ ] **Step 6: Recharger et comparer visuellement**

Recharger `site/live.html?code=local` dans le navigateur intégré et reprendre une capture
d'écran. Comparer avec la capture du Step 2 :

Expected: strictement identique — même plateau pleine largeur, même barre en bas. `#sidePanel`
reste invisible (`hidden`, et `#stage` n'a pas la classe `has-panel`).

- [ ] **Step 7: Vérifier qu'il n'y a pas d'erreur console**

Dans le navigateur intégré, lire les messages de console (`read_console_messages`) sur la page
rechargée.

Expected: aucune erreur liée à `#stage`, `#frame` ou `#sidePanel`.

- [ ] **Step 8: Commit**

```bash
cd C:\Users\Megaport\Documents\Claude\Projects\Servo-Skull
git add site/live.html
git commit -m "feat(live): grid #stage avec colonne reservee pour futur panneau"
```

---

## Self-Review

- **Couverture du spec :** le spec (`2026-11-12-live-ux-design.md`) ne demande qu'un changement
  structurel invisible dans `live.html` — Task 1 le couvre entièrement. Les points "hors
  périmètre" du spec (barre enrichie, token de lecture, remplissage du panneau) n'ont
  volontairement aucune tâche ici.
- **Pas de placeholder :** chaque step montre le code exact à écrire ou la commande exacte à
  lancer.
- **Cohérence des noms :** `#stage` / `#sidePanel` / `.has-panel` sont les seuls identifiants
  introduits, utilisés de façon cohérente entre le CSS (Step 3) et le HTML (Step 4), et repris
  tels quels dans le fichier complet du Step 5.
