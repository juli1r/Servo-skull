# Export film-cogitator.json.gz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En fin de partie, écrire `film-cogitator.json.gz` (le même payload que `recap.collect()`, sans `ttsSaves`/`folder`/`screenshot`) à côté de `recap.html` et `resume-cogitator.json`, pour un futur import manuel dans Cogitator.

**Architecture:** Nouvelle fonction `export_film()` dans `app/cogitator_export.py` (module existant, inchangé sinon), appelée depuis `app/controller.py` à côté de l'appel existant à `cogitator_export.export()`, avec la même gestion d'erreur non bloquante.

**Tech Stack:** Python stdlib (`gzip`, `json`), réutilise `app/recap.py::collect()` et `app/core.py::Session`. Tests : scripts `tests/verif_*.py` existants (pas de framework pytest dans ce projet), exécutés directement avec `python`.

Spec de référence : `docs/superpowers/specs/2026-11-12-cogitator-film-export-design.md`.

---

### Task 1 : `cogitator_export.export_film()`

**Files:**
- Modify: `app/cogitator_export.py`
- Test: `tests/verif_cogitator_film.py` (nouveau)

- [ ] **Step 1: Écrire le test (qui doit échouer)**

Créer `tests/verif_cogitator_film.py` :

```python
"""Vérifie que cogitator_export.export_film écrit un film gzippé sans ttsSaves/folder/screenshot,
et qu'il n'écrit rien si la partie n'a aucune capture."""
import gzip, json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session
import cogitator_export

root = Path(tempfile.mkdtemp())
src = Path("parties/2026-10-29_09h58_RaiJin-vs-Mankdebol")
d = root / "partie1"; d.mkdir()
shutil.copy(src / "game.json", d / "game.json")
shutil.copytree(src / "captures", d / "captures")
shutil.copytree(src / "units", d / "units")
s = Session.open(d)

path = cogitator_export.export_film(s)
assert path == d / "film-cogitator.json.gz", path
assert path.exists()

data = json.loads(gzip.decompress(path.read_bytes()))
assert "ttsSaves" not in data, "ttsSaves (références locales) ne doit pas être exporté"
assert "folder" not in data, "folder (nom de dossier local) ne doit pas être exporté"
assert data["captures"], "le film doit contenir des captures"
assert all("screenshot" not in c for c in data["captures"]), "aucune capture ne doit garder 'screenshot'"
assert data["players"], "les noms de joueurs restent en clair (pas d'anonymisation)"
assert "squadNames" in data and "mission" in data

# partie sans aucune capture : rien n'est écrit
empty_root = Path(tempfile.mkdtemp())
s2 = Session(empty_root, "Red", "host", {"Red": "Alice", "Blue": "Bob"})
assert cogitator_export.export_film(s2) is None
assert not (s2.dir / "film-cogitator.json.gz").exists()

print("OK : film-cogitator.json.gz écrit sans ttsSaves/folder/screenshot, rien si pas de capture")
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python tests/verif_cogitator_film.py`
Expected: `AttributeError: module 'cogitator_export' has no attribute 'export_film'`

- [ ] **Step 3: Implémenter `export_film()`**

Dans `app/cogitator_export.py`, ajouter en haut du fichier (après les imports existants) :

```python
import gzip

import recap
```

Puis ajouter la fonction, après `export()` (fin de fichier) :

```python
def export_film(session: Session) -> Path | None:
    """Film complet de la partie (même payload que le récap/mode live, sans les références
    locales), pour import manuel dans Cogitator — voir docs/superpowers/specs/
    2026-11-12-cogitator-film-export-design.md."""
    if not session.game.get("captures"):
        return None
    data = dict(recap.collect(session))
    data.pop("ttsSaves", None)
    data.pop("folder", None)
    data["captures"] = [{k: v for k, v in c.items() if k != "screenshot"} for c in data["captures"]]
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    path = session.dir / "film-cogitator.json.gz"
    path.write_bytes(gzip.compress(raw))
    return path
```

Le fichier complet `app/cogitator_export.py` doit ressembler à :

```python
"""Export du score d'une partie pour import dans Cogitator.

Contrairement à `contribution.py`, ce fichier n'anonymise rien : il est fait
pour être relu et importé par le joueur lui-même dans l'onglet Résultats/Vox
d'un event Cogitator, à côté de `recap.html` et du GIF."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import recap
from core import Session

SCHEMA = 1


def _last_score(captures: list[dict]) -> dict | None:
    """Score de la dernière capture qui en contient un (le plus à jour)."""
    for c in reversed(captures):
        score = c.get("score")
        if isinstance(score, dict) and score:
            return score
    return None


def _rounds(side_score: dict | None) -> list[dict]:
    rounds = (side_score or {}).get("rounds") or []
    out = []
    for r in rounds:
        if not isinstance(r, dict) or r.get("round") is None:
            continue
        out.append({
            "round": r.get("round"),
            "primary": r.get("primary") or 0,
            "secondary": r.get("secondary") or 0,
        })
    return out


def export(session: Session) -> Path | None:
    g = session.game
    score = _last_score(g.get("captures") or [])
    if not score:
        return None
    out = {
        "schema": SCHEMA,
        "date": g.get("created"),
        "myColor": g.get("myColor"),
        "players": g.get("players") or {},
        "sides": {
            side: {
                "vp": side_score.get("total") or 0,
                "rounds": _rounds(side_score),
            }
            for side, side_score in score.items()
            if isinstance(side_score, dict)
        },
    }
    path = session.dir / "resume-cogitator.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def export_film(session: Session) -> Path | None:
    """Film complet de la partie (même payload que le récap/mode live, sans les références
    locales), pour import manuel dans Cogitator — voir docs/superpowers/specs/
    2026-11-12-cogitator-film-export-design.md."""
    if not session.game.get("captures"):
        return None
    data = dict(recap.collect(session))
    data.pop("ttsSaves", None)
    data.pop("folder", None)
    data["captures"] = [{k: v for k, v in c.items() if k != "screenshot"} for c in data["captures"]]
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    path = session.dir / "film-cogitator.json.gz"
    path.write_bytes(gzip.compress(raw))
    return path
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python tests/verif_cogitator_film.py`
Expected: `OK : film-cogitator.json.gz écrit sans ttsSaves/folder/screenshot, rien si pas de capture`

- [ ] **Step 5: Commit**

```bash
git add app/cogitator_export.py tests/verif_cogitator_film.py
git commit -m "feat(cogitator): export film-cogitator.json.gz pour import manuel dans Cogitator"
```

---

### Task 2 : Appel depuis `controller.py` en fin de partie

**Files:**
- Modify: `app/controller.py:242-249`

- [ ] **Step 1: Modifier le bloc de fin de partie**

Dans `app/controller.py`, remplacer :

```python
        out = recap.build(self.session)
        try:
            cogitator_export.export(self.session)
        except Exception as e:
            try:
                (self.session.dir / "cogitator-export-erreur.txt").write_text(str(e), encoding="utf-8")
            except OSError:
                pass
```

par :

```python
        out = recap.build(self.session)
        try:
            cogitator_export.export(self.session)
        except Exception as e:
            try:
                (self.session.dir / "cogitator-export-erreur.txt").write_text(str(e), encoding="utf-8")
            except OSError:
                pass
        try:
            cogitator_export.export_film(self.session)
        except Exception as e:
            try:
                (self.session.dir / "cogitator-film-erreur.txt").write_text(str(e), encoding="utf-8")
            except OSError:
                pass
```

- [ ] **Step 2: Vérifier manuellement le câblage de bout en bout**

Dans le dossier du projet (pas besoin d'un worktree séparé pour une vérification manuelle en
lecture) :

```bash
python app/gen_local_live_payload.py "2026-10-29_09h58_RaiJin-vs-Mankdebol"
```

Ceci ne teste pas `controller.py` directement (il n'y a pas de harnais d'UI automatisé dans ce
projet), mais confirme que `recap.collect()` fonctionne sur cette partie de test — la même
fonction que `export_film()` appelle. Pour vérifier le câblage réel dans `controller.py`, relire
le fichier modifié et confirmer par inspection que le nouveau bloc `try/except` est bien placé
immédiatement après celui de `cogitator_export.export()`, avant `sess = self.session` (ligne
250 avant modification).

Expected: le fichier se relit sans erreur de syntaxe (`python -c "import ast; ast.parse(open('app/controller.py', encoding='utf-8').read())"` ne lève pas d'exception), et les deux blocs `try/except` sont visuellement symétriques.

- [ ] **Step 3: Commit**

```bash
git add app/controller.py
git commit -m "feat(cogitator): appeler export_film en fin de partie"
```

---

## Self-Review

- **Couverture du spec :** le spec (`2026-11-12-cogitator-film-export-design.md`) demande (1) le
  contenu du fichier (couvert par Task 1, Step 3 — retrait de `ttsSaves`/`folder`/`screenshot`,
  pas d'anonymisation des noms), (2) l'emplacement et le déclenchement (Task 1 pour la fonction,
  Task 2 pour l'appel en fin de partie avec gestion d'erreur non bloquante), (3) l'absence de
  plafond de taille (aucune troncature ajoutée — conforme). Les points "hors périmètre" du spec
  (écran d'import Cogitator, Storage, règles, affichage) n'ont volontairement aucune tâche ici.
- **Pas de placeholder :** chaque step montre le code exact à écrire ou la commande exacte à
  lancer, y compris le fichier `cogitator_export.py` complet après modification (Task 1, Step 3).
- **Cohérence des noms :** `export_film`, `film-cogitator.json.gz`, `cogitator-film-erreur.txt`
  sont les seuls identifiants introduits, utilisés de façon identique dans le code, le test et le
  plan.
