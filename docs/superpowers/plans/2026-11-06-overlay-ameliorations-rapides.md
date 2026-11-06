# 5 améliorations rapides de l'overlay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter les 5 idées "gains rapides" du spec `docs/superpowers/specs/2026-11-06-overlay-ameliorations-rapides-design.md` dans l'overlay en jeu (annuler la dernière capture, toast Windows, bascule hôte/invité, détection de fin de partie, marqueur "point à vérifier").

**Architecture:** Chaque tâche ajoute une petite fonction côté `core.py` (logique pure, testable sans Tk/TTS) et/ou `controller.py` (orchestration), puis le câblage UI dans `overlay.py` (bouton + état). Les 5 tâches sont indépendantes entre elles — chacune se termine par son propre commit et peut être livrée seule si besoin.

**Tech Stack:** Python 3 / Tkinter (overlay existant), pas de nouvelle dépendance pip. Le toast Windows passe par un appel `powershell.exe` en sous-processus (comme le reste du projet évite les dépendances lourdes type `pywin32`/`win10toast`).

**Convention de test de ce projet :** pas de pytest — des scripts `tests/verif_*.py` autonomes, exécutés avec `python tests/xxx.py` depuis la racine du repo, qui font des `assert` et terminent par `print("OK : ...")` (succès) ou une `AssertionError`/traceback (échec, exit code 1). On suit cette convention plutôt que d'introduire pytest.

---

## Task 1 : Annuler la dernière capture

**Files:**
- Modify: `app/core.py` (classe `Session`, après `add_capture`, ~ligne 485)
- Modify: `app/controller.py` (classe `Controller`, après `capture()`, ~ligne 510)
- Modify: `app/overlay.py` (`_build_main`, ~lignes 532-533 ; handler des événements `captured`/`idle`, ~lignes 934-944)
- Test: `tests/verif_undo_capture.py` (nouveau)

- [ ] **Step 1: Write the failing test**

```python
# tests/verif_undo_capture.py
"""Vérifie que `Session.remove_last_capture` retire bien la dernière capture (métadonnée +
fichiers data/screenshot sur disque) et laisse les précédentes intactes."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session

root = Path(tempfile.mkdtemp())
s = Session(root, "Red", "host", {"Red": "Alice", "Blue": "Bob"})

m1 = s.add_capture({"round": 1, "turn": "Red", "unitJson": {}}, "auto_phase", turn_key=(1, "Red"))
m2 = s.add_capture({"round": 1, "turn": "Blue", "unitJson": {}}, "auto_phase", turn_key=(1, "Blue"))
assert len(s.game["captures"]) == 2
data_path = root / s.dir.name / m2["data"]
assert data_path.exists(), "le fichier de données de la 2e capture doit exister avant l'annulation"

removed = s.remove_last_capture()
assert removed["id"] == m2["id"]
assert len(s.game["captures"]) == 1
assert s.game["captures"][0]["id"] == m1["id"], "la 1re capture ne doit pas être touchée"
assert not data_path.exists(), "le fichier de données de la capture annulée doit être supprimé"

assert s.remove_last_capture()["id"] == m1["id"]
assert s.game["captures"] == []
assert s.remove_last_capture() is None, "rien à annuler : ne doit pas planter"

print("OK : Session.remove_last_capture retire la dernière capture (métadonnée + fichiers)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/verif_undo_capture.py` (depuis la racine du repo)
Expected: `AttributeError: 'Session' object has no attribute 'remove_last_capture'`

- [ ] **Step 3: Write minimal implementation (core.py)**

Ajouter dans la classe `Session`, juste après la méthode `add_capture` (après la ligne `return meta` qui la termine, avant `def _label`) :

```python
    def remove_last_capture(self) -> dict | None:
        """Annule la dernière capture : retire sa métadonnée et ses fichiers (data/screenshot)
        sur disque. Les captures précédentes ne sont jamais touchées."""
        if not self.game["captures"]:
            return None
        meta = self.game["captures"].pop()
        for rel in (meta.get("data"), meta.get("screenshot")):
            if rel:
                p = self.dir / rel
                if p.exists():
                    p.unlink()
        self._save_game()
        return meta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/verif_undo_capture.py`
Expected: `OK : Session.remove_last_capture retire la dernière capture (métadonnée + fichiers)`

- [ ] **Step 5: Commit**

```bash
git add app/core.py tests/verif_undo_capture.py
git commit -m "feat(overlay): annuler la dernière capture (Session.remove_last_capture)"
```

- [ ] **Step 6: Wire into Controller**

Dans `app/controller.py`, ajouter une méthode juste après `capture()` (avant `def _check_layout`) :

```python
    def undo_last_capture(self) -> dict | None:
        """Annule la dernière capture de la partie en cours (bouton overlay). Idempotent :
        sans capture à annuler, ne fait rien."""
        if not self.session:
            return None
        meta = self.session.remove_last_capture()
        if meta:
            recap.build(self.session)
            if self.live_code:
                threading.Thread(target=live_share.push, args=(self.session, self.cfg, self.live_code),
                                 daemon=True).start()
        return meta
```

- [ ] **Step 7: Wire the button in overlay.py**

Dans `_build_main`, juste après la ligne qui empaquette `self.b_cap` :

```python
        self.b_cap = self._btn(f, f"Capturer avec cette note   [{hk}]", self._capture, kind="primary")
        self.b_cap.pack(fill="x", pady=(10, 4), ipady=3)
        n0 = len(self.ctl.session.game["captures"]) if self.ctl.session else 0
        self.b_undo = self._btn(f, "↩ Annuler la dernière capture", self._undo_last_capture)
        self.b_undo.pack(fill="x", pady=(0, 4))
        self.b_undo.config(state="normal" if n0 else "disabled")
```

Ajouter la méthode (par exemple juste après `_capture`) :

```python
    def _undo_last_capture(self):
        if not self.ctl.session or not self.ctl.session.game["captures"]:
            return
        meta = self.ctl.undo_last_capture()
        if not meta:
            return
        n = len(self.ctl.session.game["captures"])
        if hasattr(self, "lbl_count") and self.lbl_count.winfo_exists():
            self.lbl_count.config(text=f"{n} capture" + ("" if n == 1 else "s"))
        if hasattr(self, "b_undo") and self.b_undo.winfo_exists():
            self.b_undo.config(state="normal" if n else "disabled")
        self._status(f"↩ Capture annulée : {meta['label']}", AMBER)
```

Et garder le bouton synchronisé à chaque nouvelle capture : dans `_on`, cas `elif ev == "captured":` (le bloc qui met à jour `self.lbl_count`), ajouter l'activation du bouton :

```python
        elif ev == "captured":
            if hasattr(self, "lbl_count") and self.lbl_count.winfo_exists() and self.ctl.session:
                n = len(self.ctl.session.game["captures"])
                self.lbl_count.config(text=f"{n} capture" + ("" if n == 1 else "s"))
                if hasattr(self, "b_undo") and self.b_undo.winfo_exists():
                    self.b_undo.config(state="normal")
            if p["kind"] in ("manual", "catchup"):
```
(seule la ligne `if hasattr(self, "b_undo")...` est ajoutée ; le reste du bloc est inchangé.)

- [ ] **Step 8: Smoke-test the overlay still builds**

Étendre `tests/verif_overlay.py` : après `ui._build_main("host")`, ajouter `ui._undo_last_capture()` (sans capture : ne doit rien faire) pour s'assurer que le câblage ne plante pas quand la liste de captures est vide.

```python
        ui._build_main("host")
        ui.root.update()
        ui._undo_last_capture()  # aucune capture : ne doit pas lever d'exception
        ui.root.update()
```

Run: `python tests/verif_overlay.py`
Expected: `OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)`

- [ ] **Step 9: Commit**

```bash
git add app/controller.py app/overlay.py tests/verif_overlay.py
git commit -m "feat(overlay): bouton Annuler la dernière capture"
```

---

## Task 2 : Notification Windows (toast) à chaque capture

**Files:**
- Create: `app/toast.py`
- Modify: `app/controller.py` (import, helper `_toast_text`, appel dans `capture()`)
- Modify: `app/overlay.py` (`_build_main` : variable de réglage ; `_open_settings_menu` : case à cocher + `_toggle`)
- Test: `tests/verif_toast.py` (nouveau)

- [ ] **Step 1: Write the failing test**

```python
# tests/verif_toast.py
"""Vérifie l'échappement XML du toast et le texte round/score construit pour chaque capture.
N'affiche jamais un vrai toast (pas d'appel à toast.show) : ce test reste silencieux et rapide."""
import sys
sys.path.insert(0, "app")
import toast
import controller

xml = toast.build_xml('R5 · tour "Rouge" <test>', "Score & victoire")
assert "<test>" not in xml, "le texte doit être échappé dans le XML du toast"
assert "&lt;test&gt;" in xml
assert "&amp;" in xml
assert xml.count("<text>") == 2
print("OK : toast.build_xml échappe correctement titre/texte")

meta = {"turnKey": [2, "Red"], "vp": {"Red": 12, "Blue": 7}}
assert controller._toast_text(meta) == "R2 · tour Rouge · 12-7"
meta2 = {"turnKey": None, "vp": {}}
assert controller._toast_text(meta2) == "Capture"
print("OK : controller._toast_text formate round/score (ou juste « Capture » si inconnu)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/verif_toast.py`
Expected: `ModuleNotFoundError: No module named 'toast'`

- [ ] **Step 3: Write minimal implementation — app/toast.py**

```python
"""Notification Windows (toast natif) à chaque capture, sans nouvelle dépendance pip : le XML
du template est poussé via un appel `powershell.exe` en sous-processus, sous l'identité
PowerShell elle-même (ce qui évite d'avoir à enregistrer Servo-Skull comme application Windows
juste pour avoir le droit d'afficher un toast — limitation des exe non empaquetés)."""
import subprocess
import sys

_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_xml(title: str, message: str) -> str:
    return (f'<toast><visual><binding template="ToastGeneric">'
            f'<text>{_esc(title)}</text><text>{_esc(message)}</text>'
            f'</binding></visual></toast>')


def show(title: str, message: str) -> None:
    """Non bloquant : lance le toast dans un processus à part et ne lève jamais d'exception
    (une notification manquée ne doit jamais interrompre une capture)."""
    if sys.platform != "win32":
        return
    xml = build_xml(title, message)
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        f"$x.LoadXml('{xml}'); "
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_AUMID}')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
```

- [ ] **Step 4: Write minimal implementation — app/controller.py**

Ajouter l'import en haut du fichier (à côté des autres imports du projet) :

```python
import toast
```

Ajouter la fonction utilitaire au niveau module (par exemple juste avant `class Controller:`) :

```python
def _toast_text(meta: dict) -> str:
    key = tuple(meta["turnKey"]) if meta.get("turnKey") else None
    label = turn_label(key) if key else "Capture"
    vp = meta.get("vp") or {}
    if vp.get("Red") is not None or vp.get("Blue") is not None:
        label += f" · {vp.get('Red', '–')}-{vp.get('Blue', '–')}"
    return label
```

Dans `capture()`, juste avant `self.emit("captured", meta)` :

```python
            if self.cfg.get("toast_on_capture", False):
                try:
                    toast.show("Servo-Skull", _toast_text(meta))
                except Exception:
                    pass
            self.emit("captured", meta)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python tests/verif_toast.py`
Expected:
```
OK : toast.build_xml échappe correctement titre/texte
OK : controller._toast_text formate round/score (ou juste « Capture » si inconnu)
```

- [ ] **Step 6: Commit**

```bash
git add app/toast.py app/controller.py tests/verif_toast.py
git commit -m "feat(overlay): notification Windows (toast) à chaque capture"
```

- [ ] **Step 7: Wire the settings checkbox in overlay.py**

Dans `_build_main`, à côté des autres `tk.BooleanVar` de réglages :

```python
        self.v_photo = tk.BooleanVar(value=bool(self.cfg.get("photo_on_capture", False)))
        self.v_contrib = tk.BooleanVar(value=self.cfg.get("contribution") == "oui")
        self.v_envoi = tk.BooleanVar(value=self.cfg.get("envoi") == "oui")
        self.v_toast = tk.BooleanVar(value=bool(self.cfg.get("toast_on_capture", False)))
```

Dans `_open_settings_menu`, la fonction `_toggle` traite `photo_on_capture` comme un booléen brut (les autres réglages sont stockés en `"oui"`/`"non"`) ; ajouter `toast_on_capture` à cette même exception :

```python
        def _toggle(key, var, on="oui", off="non"):
            self.cfg[key] = (on if var.get() else off) if key not in ("photo_on_capture", "toast_on_capture") else var.get()
            self.save_cfg(self.cfg)
```

Puis ajouter la case, à côté de celle des stats anonymes :

```python
        m.add_checkbutton(label="Fichier anonyme pour les stats (rien n'est envoyé)", variable=self.v_contrib,
                          command=lambda: _toggle("contribution", self.v_contrib))
        m.add_checkbutton(label="Notification Windows à chaque capture", variable=self.v_toast,
                          command=lambda: _toggle("toast_on_capture", self.v_toast))
```

- [ ] **Step 8: Smoke-test the overlay still builds**

Run: `python tests/verif_overlay.py`
Expected: `OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)`

- [ ] **Step 9: Commit**

```bash
git add app/overlay.py
git commit -m "feat(overlay): case de réglage pour la notification Windows"
```

**Note de vérification manuelle (non automatisable) :** lancer une vraie partie, activer la case
dans les réglages, faire une capture (F8) et confirmer qu'un toast Windows apparaît avec le round
et le score — le test automatisé ne couvre que la construction du XML et le texte, pas l'affichage
réel du toast par Windows.

---

## Task 3 : Bouton "basculer hôte/invité"

**Files:**
- Modify: `app/controller.py` (nouvelle méthode `toggle_mode`)
- Modify: `app/overlay.py` (bouton dans la barre du bas + handler `_toggle_mode`)
- Test: `tests/verif_toggle_mode.py` (nouveau), extension de `tests/verif_overlay.py`

- [ ] **Step 1: Write the failing test (controller)**

```python
# tests/verif_toggle_mode.py
"""Vérifie que Controller.toggle_mode inverse le rôle hôte/invité sans toucher aux captures
déjà enregistrées, et que l'état est bien répercuté sur session.game (persisté sur disque)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session
from controller import Controller

root = Path(tempfile.mkdtemp())
session = Session(root, "Red", "host", {"Red": "Alice", "Blue": "Bob"})
session.add_capture({"round": 1, "turn": "Red", "unitJson": {}}, "auto_phase", turn_key=(1, "Red"))

class _FakeClient:
    on_game_saved = None
    on_custom = None

ctl = Controller(cfg={}, client=_FakeClient())
ctl.session = session
ctl.mode = "host"
session.mode = "host"

new_mode = ctl.toggle_mode()
assert new_mode == "guest"
assert ctl.mode == "guest" and session.mode == "guest"
assert session.game["mode"] == "guest"
assert len(session.game["captures"]) == 1, "basculer le rôle ne doit jamais toucher l'historique"

new_mode2 = ctl.toggle_mode()
assert new_mode2 == "host"
assert ctl.mode == "host" and session.mode == "host"

print("OK : Controller.toggle_mode inverse le rôle sans toucher aux captures existantes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/verif_toggle_mode.py`
Expected: `AttributeError: 'Controller' object has no attribute 'toggle_mode'`

- [ ] **Step 3: Write minimal implementation (controller.py)**

Ajouter dans `Controller`, par exemple juste après `retry_connection` :

```python
    def toggle_mode(self) -> str:
        """Bouton « basculer hôte/invité » : corrige une détection automatique erronée sans
        relancer la partie. N'affecte jamais les captures déjà enregistrées — seulement
        l'étiquetage des captures à venir."""
        if not self.session:
            return self.mode
        new_mode = "guest" if self.mode == "host" else "host"
        self.mode = self.session.mode = new_mode
        self.session.game["mode"] = new_mode
        self.session._save_game()
        return new_mode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/verif_toggle_mode.py`
Expected: `OK : Controller.toggle_mode inverse le rôle sans toucher aux captures existantes`

- [ ] **Step 5: Commit**

```bash
git add app/controller.py tests/verif_toggle_mode.py
git commit -m "feat(overlay): Controller.toggle_mode pour corriger le rôle hôte/invité"
```

- [ ] **Step 6: Wire the button in overlay.py**

Dans `_build_main`, dans la barre du bas (`bot`), ajouter le bouton près de "Restaurer" :

```python
        self._btn(bot, "Restaurer", self._restore_dialog).pack(side="left", padx=(4, 0))
        self._btn(bot, "⇄ Rôle", self._toggle_mode).pack(side="left", padx=(4, 0))
        gear = self._btn(bot, "⚙", lambda: self._open_settings_menu(gear), font=(FONT_H[0], 13))
```

Ajouter la méthode (par exemple juste après `_toggle_live`) :

```python
    def _toggle_mode(self):
        if not self.ctl.session:
            return
        target = "invité" if self.mode == "host" else "hôte"
        if not messagebox.askyesno(
            "Basculer de rôle",
            f"Passer en mode {target} ? Seules les captures à venir seront concernées — "
            "l'historique déjà enregistré ne change pas.", parent=self.root):
            return
        new_mode = self.ctl.toggle_mode()
        shell_was_open = self._shell_open
        n = len(self.ctl.session.game["captures"])
        self._build_main(new_mode)
        if hasattr(self, "lbl_count") and self.lbl_count.winfo_exists():
            self.lbl_count.config(text=f"{n} capture" + ("" if n == 1 else "s"))
        if shell_was_open:
            self._toggle_shell()
```

- [ ] **Step 7: Smoke-test the overlay still builds and the toggle doesn't crash**

Étendre `tests/verif_overlay.py` (après le passage en mode invité) :

```python
        ui.ctl = _FakeCtl("Red")
        ui._build_main("guest")
        ui.root.update()
```

`_FakeCtl` n'a pas de méthode `toggle_mode` — il suffit ici de vérifier que `_build_main` supporte
d'être rappelé deux fois de suite (ce que fait `_toggle_mode`) sans laisser de widget cassé ; pas
besoin d'appeler `_toggle_mode` directement dans ce smoke test (il dépend du vrai `Controller`,
déjà couvert par `verif_toggle_mode.py`).

Run: `python tests/verif_overlay.py`
Expected: `OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)`

- [ ] **Step 8: Commit**

```bash
git add app/overlay.py
git commit -m "feat(overlay): bouton pour basculer le rôle hôte/invité"
```

---

## Task 4 : Détection automatique de fin de partie

**Files:**
- Modify: `app/core.py` (fonction pure `is_final_phase_end`, après `PHASE_ORDER`/avant `TurnTracker` ou à côté de `turn_label`)
- Modify: `app/controller.py` (`tick()` : nouvel événement `finish_suggest`)
- Modify: `app/overlay.py` (`_build_main` : 2e bannière ; `_on` : cas `finish_suggest` ; `_badge_status` ; nouveau handler `_dismiss_finish`)
- Test: `tests/verif_finish_detect.py` (nouveau)

- [ ] **Step 1: Write the failing test**

```python
# tests/verif_finish_detect.py
"""Vérifie le signal de fin de partie probable : fin de la phase de Combat (dernière phase)
du DEUXIÈME tour (seq pair) d'un round >= 5 (missions LCT = 5 rounds, cf. score_summary)."""
import sys
sys.path.insert(0, "app")
from core import is_final_phase_end

# round 5, tour de Rouge (2e tour du round, seq pair) : fin de partie probable
assert is_final_phase_end((5, "Red"), "Fight", 10) is True
# round 5, tour de Bleu (1er tour du round, seq impair) : pas encore, l'autre joueur n'a pas joué
assert is_final_phase_end((5, "Blue"), "Fight", 9) is False
# bonne phase/round mais pas la dernière phase
assert is_final_phase_end((5, "Red"), "Movement", 10) is False
# round trop tôt
assert is_final_phase_end((4, "Red"), "Fight", 8) is False
# partie plus longue que la normale (round 6) : le signal reste valable
assert is_final_phase_end((6, "Red"), "Fight", 12) is True
# pas de clé (hors partie) : jamais de signal
assert is_final_phase_end(None, "Fight", 10) is False

print("OK : is_final_phase_end détecte la fin probable de partie (round >= 5, Combat, 2e tour)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/verif_finish_detect.py`
Expected: `ImportError: cannot import name 'is_final_phase_end' from 'core'`

- [ ] **Step 3: Write minimal implementation (core.py)**

Ajouter juste après la définition de `PHASE_ORDER` (ligne ~25) :

```python
def is_final_phase_end(key: tuple | None, phase_name: str, seq: int) -> bool:
    """Vrai à la fin de la phase de Combat (dernière phase) du 2e tour (seq pair = le round a
    été joué par les deux camps) d'un round >= 5 — les missions LCT se jouent sur 5 rounds
    (cf. score_summary, qui plafonne aussi à 5). Signal volontairement conservateur : pas de
    bannière si la condition n'est pas clairement remplie."""
    return bool(key) and key[0] >= 5 and phase_name == PHASE_ORDER[-1] and seq % 2 == 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/verif_finish_detect.py`
Expected: `OK : is_final_phase_end détecte la fin probable de partie (round >= 5, Combat, 2e tour)`

- [ ] **Step 5: Commit**

```bash
git add app/core.py tests/verif_finish_detect.py
git commit -m "feat(overlay): core.is_final_phase_end pour détecter la fin probable de partie"
```

- [ ] **Step 6: Wire into Controller.tick()**

Dans `app/controller.py`, ajouter l'import de la fonction (`from core import Session, TurnTracker, normalize_state, turn_label, is_final_phase_end`), puis dans `tick()`, dans la boucle `for ev in events:`, ajouter une branche (après celle de `missed_turn`) :

```python
            elif kind == "phase_ended" and is_final_phase_end(ev[1], ev[2], self.tracker.seq):
                self.emit("finish_suggest", {"round": ev[1][0]})
```

- [ ] **Step 7: Add the second banner in overlay.py**

Dans `_build_main`, juste après le bloc du `self.alert` existant (après `self._btn(ar, "Ignorer", self._dismiss).pack(side="left", padx=6)`, avant `self.alert_anchor`) :

```python
        self.alert2 = tk.Frame(self.shell, bg=ALERT, padx=10, pady=6, highlightthickness=1, highlightbackground=AMBER)
        self.alert2_lbl = tk.Label(self.alert2, text="", bg=ALERT, fg=INK, font=FONT_B, wraplength=280, justify="left")
        self.alert2_lbl.pack(anchor="w")
        ar2 = tk.Frame(self.alert2, bg=ALERT)
        ar2.pack(anchor="w", pady=(6, 0))
        self._btn(ar2, "Terminer", self._finish, kind="primary").pack(side="left")
        self._btn(ar2, "Pas encore", self._dismiss_finish).pack(side="left", padx=6)
        self.alert_anchor = tk.Frame(self.shell, bg=PANEL)
        self.alert_anchor.pack(fill="x")
```
(la ligne `self.alert_anchor = ...` existait déjà juste après le bloc `self.alert` — `self.alert2` et son contenu s'insèrent juste avant, dans le même ordre visuel.)

Ajouter les handlers (par exemple juste après `_dismiss`) :

```python
    def _dismiss_finish(self):
        self._finish_pending = False
        if hasattr(self, "alert2") and self.alert2.winfo_exists():
            self.alert2.pack_forget()
        self._update_badge()
        self._relayout()
```

Dans `_on`, ajouter un cas (par exemple juste après celui de `"alert_clear"`) :

```python
        elif ev == "finish_suggest" and hasattr(self, "alert2"):
            self._finish_pending = True
            self.alert2_lbl.config(text=f"⚠  Le round {p['round']} semble terminé. Terminer la partie ?")
            self.alert2.pack(fill="x", padx=8, pady=(6, 6), before=self.alert_anchor)
            beep()
            self._update_badge()
            self._relayout()
```

Dans `_badge_status`, étendre la condition qui met l'ambre/notification (ligne ~220) pour inclure ce nouveau signal :

```python
        if getattr(self, "_update_info", None) or getattr(self, "_unfinished_info", None) \
           or getattr(self, "_layout_info", None) or getattr(self, "_finish_pending", False):
            return AMBER, True
```

- [ ] **Step 8: Smoke-test the overlay still builds**

Run: `python tests/verif_overlay.py`
Expected: `OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)`

- [ ] **Step 9: Commit**

```bash
git add app/controller.py app/overlay.py
git commit -m "feat(overlay): bannière de détection de fin de partie probable"
```

---

## Task 5 : Marqueur "point à vérifier"

**Files:**
- Modify: `app/core.py` (`Session.flag_last_capture`)
- Modify: `app/controller.py` (`Controller.flag_last_capture`)
- Modify: `app/overlay.py` (bouton, raccourci clavier `_install_hotkey` généralisé, handler)
- Modify: `app/recap_template.html` (marqueur visuel sur la timeline)
- Test: `tests/verif_flag_capture.py` (nouveau)

- [ ] **Step 1: Write the failing test**

```python
# tests/verif_flag_capture.py
"""Vérifie que Session.flag_last_capture épingle un marqueur sur la DERNIÈRE capture, sans
texte, et qu'on peut en poser plusieurs sans limite."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session

root = Path(tempfile.mkdtemp())
s = Session(root, "Red", "host", {"Red": "Alice", "Blue": "Bob"})
assert s.flag_last_capture() is None, "rien à épingler sans capture"

m1 = s.add_capture({"round": 1, "turn": "Red", "unitJson": {}}, "auto_phase", turn_key=(1, "Red"))
flagged = s.flag_last_capture()
assert flagged["id"] == m1["id"]
assert s.game["captures"][0]["flagged"] is True

m2 = s.add_capture({"round": 1, "turn": "Blue", "unitJson": {}}, "auto_phase", turn_key=(1, "Blue"))
s.flag_last_capture()
assert s.game["captures"][0]["flagged"] is True, "le marqueur précédent reste en place"
assert s.game["captures"][1]["flagged"] is True, "la nouvelle dernière capture est marquée"

print("OK : Session.flag_last_capture épingle la dernière capture, plusieurs fois si besoin")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/verif_flag_capture.py`
Expected: `AttributeError: 'Session' object has no attribute 'flag_last_capture'`

- [ ] **Step 3: Write minimal implementation (core.py)**

Ajouter dans `Session`, juste après `remove_last_capture` (ajoutée à la Task 1) :

```python
    def flag_last_capture(self) -> dict | None:
        """Épingle un marqueur « à vérifier » sur la dernière capture, sans texte — distinct
        de la note libre. Peut être posé plusieurs fois (chaque pose est indépendante)."""
        if not self.game["captures"]:
            return None
        meta = self.game["captures"][-1]
        meta["flagged"] = True
        self._save_game()
        return meta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/verif_flag_capture.py`
Expected: `OK : Session.flag_last_capture épingle la dernière capture, plusieurs fois si besoin`

- [ ] **Step 5: Commit**

```bash
git add app/core.py tests/verif_flag_capture.py
git commit -m "feat(overlay): Session.flag_last_capture pour le marqueur point à vérifier"
```

- [ ] **Step 6: Wire into Controller**

Dans `app/controller.py`, ajouter après `undo_last_capture` :

```python
    def flag_last_capture(self) -> dict | None:
        if not self.session:
            return None
        meta = self.session.flag_last_capture()
        if meta:
            recap.build(self.session)
        return meta
```

- [ ] **Step 7: Generalize the hotkey registration in overlay.py**

Remplacer entièrement `_install_hotkey` (et ajouter `_parse_hotkey` juste avant) :

```python
    @staticmethod
    def _parse_hotkey(spec: str):
        mods, vk = 0x4000, None  # MOD_NOREPEAT
        for part in spec.lower().replace(" ", "").split("+"):
            if part in ("ctrl", "control"):
                mods |= 0x2
            elif part == "alt":
                mods |= 0x1
            elif part == "shift":
                mods |= 0x4
            elif part in ("win", "cmd"):
                mods |= 0x8
            elif part.startswith("f") and part[1:].isdigit():
                vk = 0x70 + int(part[1:]) - 1
            elif len(part) == 1:
                vk = ord(part.upper())
        return mods, vk

    def _install_hotkey(self):
        """Raccourcis globaux via RegisterHotKey (Windows) : aucun crochet clavier, aucun coût
        pour les autres programmes. L'ancien crochet (pynput) faisait passer chaque touche
        et chaque mouvement de TTS par Python."""
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes
        bindings = []  # (id, mods, vk, label, event)
        for hk_id, cfg_key, default, ev in ((1, "hotkey", "f8", "hotkey"),
                                             (2, "flag_hotkey", "f9", "flag_hotkey")):
            spec = self.cfg.get(cfg_key, default)
            mods, vk = self._parse_hotkey(spec)
            if vk is not None:
                bindings.append((hk_id, mods, vk, spec.upper(), ev))
        if not bindings:
            return
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

        def loop():
            self._hotkey_tid = kernel32.GetCurrentThreadId()
            registered = {}
            for hk_id, mods, vk, label, ev in bindings:
                if user32.RegisterHotKey(None, hk_id, mods, vk):
                    registered[hk_id] = ev
                else:
                    self.emit("error", f"Raccourci {label} déjà pris par un autre programme : "
                                       "change-le dans config.json.")
            if not registered:
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam in registered:  # WM_HOTKEY
                    self.emit(registered[msg.wParam])
            for hk_id in registered:
                user32.UnregisterHotKey(None, hk_id)
        threading.Thread(target=loop, daemon=True).start()
```

- [ ] **Step 8: Dispatch the new hotkey event and add the button**

Dans `_on`, à côté de `elif ev == "hotkey": self._capture()` :

```python
        elif ev == "hotkey":
            self._capture()
        elif ev == "flag_hotkey":
            self._flag_last_capture()
```

Dans `_build_main`, dans la barre du bas, près du bouton `⇄ Rôle` ajouté à la Task 3 :

```python
        self._btn(bot, "⇄ Rôle", self._toggle_mode).pack(side="left", padx=(4, 0))
        hk_flag = self.cfg.get("flag_hotkey", "f9").upper()
        self._btn(bot, f"🚩 [{hk_flag}]", self._flag_last_capture).pack(side="left", padx=(4, 0))
```

Ajouter le handler (par exemple juste après `_undo_last_capture`) :

```python
    def _flag_last_capture(self):
        if not self.ctl.session or not self.ctl.session.game["captures"]:
            return
        meta = self.ctl.flag_last_capture()
        if meta:
            self._status(f"🚩 Point à vérifier posé sur : {meta['label']}", AMBER)
```

- [ ] **Step 9: Add the visual marker in recap_template.html**

Dans la fonction `turnHtml`, remplacer la ligne qui construit `.pts` (celle qui calcule `hn` et le
bouton de phase) :

```js
  h+=`<div class="pts">`+PH_ORDER.map(p=>{const k=t.ph[p];const hn=t.idx.some(q=>notePh(q)===p&&(C[q].note||C[q].intent));return k==null?`<button class="pt" disabled title="Non capturé">${esc(phase(p))}</button>`:`<button class="pt${k===i?" on":""}${hn?" nt":""}" data-k="${k}"${hn?' title="Une note sur cette phase"':""}>${esc(phase(p))}</button>`}).join("")+`</div>`;
```

par :

```js
  h+=`<div class="pts">`+PH_ORDER.map(p=>{const k=t.ph[p];const hn=t.idx.some(q=>notePh(q)===p&&(C[q].note||C[q].intent));
    const fl=t.idx.some(q=>notePh(q)===p&&C[q].flagged);
    const ttl=[hn?"Une note sur cette phase":"",fl?"Point à vérifier":""].filter(Boolean).join(" · ");
    return k==null?`<button class="pt" disabled title="Non capturé">${esc(phase(p))}</button>`:`<button class="pt${k===i?" on":""}${hn?" nt":""}${fl?" fl":""}" data-k="${k}"${ttl?` title="${ttl}"`:""}>${esc(phase(p))}</button>`}).join("")+`</div>`;
```

Et ajouter la règle CSS, juste après `.pts .pt.nt::after{...}` (ligne ~228) :

```css
.pts .pt.fl::after{content:"🚩";margin-left:4px;font-size:10px;vertical-align:middle}
```

- [ ] **Step 10: Smoke-test the overlay still builds**

Run: `python tests/verif_overlay.py`
Expected: `OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)`

- [ ] **Step 11: Commit**

```bash
git add app/controller.py app/overlay.py app/recap_template.html
git commit -m "feat(overlay): marqueur point à vérifier (raccourci, bouton, repère dans le récap)"
```

---

## Self-Review (fait par l'auteur du plan, pas un sous-agent)

**Couverture du spec :** les 5 sections du spec (`...design.md`) ont chacune leur tâche ci-dessus ;
la section "Hors scope" (mode tournoi) n'a volontairement aucune tâche.

**Placeholders :** aucun "TBD"/"TODO" — chaque étape montre le code exact à écrire.

**Cohérence des types/noms :** `Session.remove_last_capture` / `Session.flag_last_capture`
renvoient toujours `dict | None` (la métadonnée ou rien) — même convention dans `Controller`
(`undo_last_capture`, `flag_last_capture`) qui les enveloppent. `is_final_phase_end(key, phase_name,
seq)` reprend exactement la forme des tuples déjà produits par `TurnTracker.update` (`ev[1]`,
`ev[2]`) et de `self.tracker.seq` — pas de nouveau format de données introduit.

## Verification (end-to-end, après les 5 tâches)

1. `python tests/verif_undo_capture.py && python tests/verif_toast.py && python tests/verif_toggle_mode.py && python tests/verif_finish_detect.py && python tests/verif_flag_capture.py && python tests/verif_overlay.py`
   — tout doit afficher `OK : ...`, aucune `AssertionError`/traceback.
2. Lancer l'outil pour de vrai (`python app/main.py` ou l'exe packagé) sur une partie TTS :
   - Faire 2 captures, cliquer "↩ Annuler la dernière capture" → la carte affiche `1 capture`.
   - Activer la notification Windows dans les réglages (⚙), faire une capture → un toast apparaît.
   - Cliquer "⇄ Rôle" → confirmer → le badge de statut change de couleur immédiatement.
   - Jouer (ou simuler) jusqu'à la fin de la phase de Combat du 2e tour du round 5 → la bannière
     "Le round 5 semble terminé. Terminer la partie ?" apparaît.
   - Poser un marqueur "point à vérifier" (bouton ou raccourci F9) sur une capture, terminer la
     partie, ouvrir le récap → le repère 🚩 apparaît sur le bouton de phase correspondant.
