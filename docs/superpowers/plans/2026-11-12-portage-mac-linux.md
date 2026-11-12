# Portage Mac/Linux Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Builder et lancer Servo-Skull sur Mac/Linux, avec capture ciblée de la fenêtre Tabletop
Simulator là où c'est techniquement possible (Mac, Linux X11), et un avertissement explicite dans
l'overlay — sur les 3 OS — quand la capture retombe en "écran complet".

**Architecture:** `app/screenshot.py` se découpe en dispatch par `sys.platform`, chaque branche
import ses libs natives en lazy (pour ne jamais casser l'import sur les autres OS). Un nouveau
callback `on_capture_scope` prévient l'overlay via le mécanisme d'événements existant
(`ui.emit(ev, payload)`) pour afficher une bannière sur le modèle des bannières déjà en place
(`_apply_unfinished_banner`, `_apply_layout_banner`). Le CI (`release.yml`) passe en matrice à 3
OS, chacun produisant son zip, attaché à la même Release GitHub.

**Tech Stack:** Python 3.11, Tkinter, `mss`, `pyobjc-framework-Quartz` (Mac), `python-xlib`
(Linux X11), PyInstaller, GitHub Actions (PowerShell Core partout, `pwsh` est préinstallé sur les
3 images hébergées).

Référence : [docs/superpowers/specs/2026-11-12-portage-mac-linux-design.md](../specs/2026-11-12-portage-mac-linux-design.md)

**Contrainte de test connue :** aucune machine Mac/Linux physique. Les tâches 1-3, 6-9 sont
vérifiables ici (logique pure ou smoke-test Tk sur Windows). Les tâches 4-5 (Quartz/Xlib) et 11
(build CI réel) ne peuvent être vérifiées que par les logs du run GitHub Actions après le premier
push, et par les retours des joueurs Mac/Linux en beta — chaque tâche le dit explicitement.

---

### Task 1: Retirer la dépendance morte `pynput`

**Files:**
- Modify: `requirements.txt`
- Modify: `.github/workflows/release.yml:54-57`

- [ ] **Step 1: Confirmer qu'il n'y a aucun import actif**

Run: `grep -rn "^import pynput\|^from pynput" app/`
Expected: aucune ligne (déjà vérifié pendant le brainstorming — seul `app/overlay.py:1054`
mentionne "pynput" dans un commentaire, aucun import réel).

- [ ] **Step 2: Retirer la ligne de `requirements.txt`**

Contenu actuel :
```
mss>=9.0
pillow>=10.0
pynput>=1.7
```
Nouveau contenu :
```
mss>=9.0
pillow>=10.0
```

- [ ] **Step 3: Retirer les hidden-imports PyInstaller devenus inutiles**

Dans `.github/workflows/release.yml`, la step "Build (--onedir, comme empaqueter.bat)" :
```powershell
pyinstaller --noconfirm --onedir --windowed --name Servo-Skull --paths app `
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 `
  --add-data "app\recap_template.html;." --add-data "app\assets;assets" --add-data "app\data;data" --icon "app\assets\servo-skull.ico" `
  app\main.py
```
devient (la ligne `--hidden-import` disparaît — elle sera de toute façon réécrite au Task 11) :
```powershell
pyinstaller --noconfirm --onedir --windowed --name Servo-Skull --paths app `
  --add-data "app\recap_template.html;." --add-data "app\assets;assets" --add-data "app\data;data" --icon "app\assets\servo-skull.ico" `
  app\main.py
```

- [ ] **Step 4: Vérifier que l'app se lance toujours en dev (Windows)**

Run: `python app/main.py`
Expected: l'overlay Servo-Skull s'ouvre normalement (fenêtre "nouvelle partie"). Fermer la
fenêtre pour terminer la vérification.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .github/workflows/release.yml
git commit -m "chore: retire la dépendance morte pynput"
```

---

### Task 2: Détection Wayland (`_is_wayland`)

**Files:**
- Modify: `app/screenshot.py`
- Test: `tests/verif_is_wayland.py`

- [ ] **Step 1: Écrire le test (doit échouer : la fonction n'existe pas encore)**

Créer `tests/verif_is_wayland.py` :
```python
"""Vérifie que _is_wayland() lit les variables d'environnement standard de session Wayland,
sans dépendre de l'OS réel de la machine qui lance le test (on monkeypatch os.environ)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import screenshot

# ni XDG_SESSION_TYPE ni WAYLAND_DISPLAY -> pas Wayland
env = {}
assert screenshot._is_wayland(env) is False

# XDG_SESSION_TYPE=wayland -> Wayland
env = {"XDG_SESSION_TYPE": "wayland"}
assert screenshot._is_wayland(env) is True

# WAYLAND_DISPLAY présent (même sans XDG_SESSION_TYPE) -> Wayland
env = {"WAYLAND_DISPLAY": "wayland-0"}
assert screenshot._is_wayland(env) is True

# XDG_SESSION_TYPE=x11 -> pas Wayland
env = {"XDG_SESSION_TYPE": "x11"}
assert screenshot._is_wayland(env) is False

print("OK : _is_wayland lit XDG_SESSION_TYPE / WAYLAND_DISPLAY correctement")
```

- [ ] **Step 2: Lancer le test, confirmer l'échec**

Run: `python tests/verif_is_wayland.py`
Expected: `AttributeError: module 'screenshot' has no attribute '_is_wayland'`

- [ ] **Step 3: Implémenter `_is_wayland`**

Dans `app/screenshot.py`, ajouter après les imports (après la ligne `from PIL import Image`) :
```python
def _is_wayland(env=None) -> bool:
    env = os.environ if env is None else env
    return env.get("XDG_SESSION_TYPE") == "wayland" or "WAYLAND_DISPLAY" in env
```
Ajouter `import os` en haut du fichier (actuellement seuls `sys` et `Path` sont importés).

- [ ] **Step 4: Relancer le test, confirmer le succès**

Run: `python tests/verif_is_wayland.py`
Expected: `OK : _is_wayland lit XDG_SESSION_TYPE / WAYLAND_DISPLAY correctement`

- [ ] **Step 5: Commit**

```bash
git add app/screenshot.py tests/verif_is_wayland.py
git commit -m "feat(screenshot): détection de session Wayland"
```

---

### Task 3: Dispatch de `_tts_client_rect()` par OS

**Files:**
- Modify: `app/screenshot.py`
- Test: `tests/verif_tts_rect_dispatch.py`

**But de cette tâche :** extraire le code Windows existant dans `_tts_rect_win32()` sans le
modifier, brancher `_tts_client_rect()` sur le bon OS, et vérifier le dispatch lui-même (pas
encore l'implémentation Mac/Linux réelle — stubs à ce stade, remplis aux Tasks 4 et 5).

- [ ] **Step 1: Écrire le test de dispatch (échoue : les fonctions n'existent pas encore)**

Créer `tests/verif_tts_rect_dispatch.py` :
```python
"""Vérifie que _tts_client_rect() appelle la bonne fonction par OS, sans dépendre des libs
natives Mac/Linux (Quartz, Xlib) qui ne sont pas installées sur cette machine de dev Windows —
on monkeypatch les fonctions cibles plutôt que d'exécuter du vrai code Quartz/Xlib."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import screenshot

calls = []
screenshot._tts_rect_win32 = lambda: calls.append("win32") or None
screenshot._tts_rect_macos = lambda: calls.append("macos") or None
screenshot._tts_rect_x11 = lambda: calls.append("x11") or None

screenshot.sys.platform = "win32"
screenshot._tts_client_rect()
assert calls == ["win32"], calls

calls.clear()
screenshot.sys.platform = "darwin"
screenshot._tts_client_rect()
assert calls == ["macos"], calls

calls.clear()
screenshot.sys.platform = "linux"
screenshot._is_wayland = lambda: False
screenshot._tts_client_rect()
assert calls == ["x11"], calls

calls.clear()
screenshot.sys.platform = "linux"
screenshot._is_wayland = lambda: True
result = screenshot._tts_client_rect()
assert calls == [], "Wayland : aucune détection ne doit être tentée"
assert result is None

print("OK : _tts_client_rect() dispatch vers la bonne fonction par OS (win32/macos/x11/wayland)")
```

- [ ] **Step 2: Lancer le test, confirmer l'échec**

Run: `python tests/verif_tts_rect_dispatch.py`
Expected: `AttributeError: module 'screenshot' has no attribute '_tts_rect_win32'` (ou équivalent)

- [ ] **Step 3: Extraire le code Windows existant et écrire le dispatch**

Dans `app/screenshot.py`, renommer la fonction existante `_tts_client_rect` en `_tts_rect_win32`
(corps inchangé, juste le nom), puis ajouter :
```python
def _tts_rect_macos():
    return None  # implémenté au Task 4


def _tts_rect_x11():
    return None  # implémenté au Task 5


def _tts_client_rect():
    """Rectangle écran (x, y, w, h) de la zone de rendu de TTS, ou None si indétectable."""
    try:
        if sys.platform == "win32":
            return _tts_rect_win32()
        if sys.platform == "darwin":
            return _tts_rect_macos()
        if sys.platform.startswith("linux"):
            if _is_wayland():
                return None
            return _tts_rect_x11()
    except Exception:
        pass
    return None
```
(la garde `if sys.platform != "win32": return None` en tête de l'ancienne fonction, maintenant
`_tts_rect_win32`, devient redondante avec le dispatch — la retirer de son corps.)

- [ ] **Step 4: Relancer le test, confirmer le succès**

Run: `python tests/verif_tts_rect_dispatch.py`
Expected: `OK : _tts_client_rect() dispatch vers la bonne fonction par OS (win32/macos/x11/wayland)`

- [ ] **Step 5: Vérifier que la capture Windows fonctionne toujours**

Run: `python app/main.py`, lancer TTS si possible, ou juste confirmer qu'aucune exception n'est
levée au lancement de l'overlay (le dispatch passe par `_tts_rect_win32` sans TTS lancé : doit
retourner `None` silencieusement, comme avant).

- [ ] **Step 6: Commit**

```bash
git add app/screenshot.py tests/verif_tts_rect_dispatch.py
git commit -m "refactor(screenshot): dispatch de la détection de fenêtre TTS par OS"
```

---

### Task 4: Détection de fenêtre sur Mac (Quartz)

**Files:**
- Modify: `app/screenshot.py`
- Modify: `requirements.txt`

**Pas de machine Mac disponible** : cette tâche ne peut pas être vérifiée par un test qui tourne
réellement ici. Le code est écrit avec import lazy (ne touche jamais l'import du module sur
Windows/Linux) et une gestion d'erreur large ; la vérification réelle vient du run CI macOS
(Task 11) puis des retours beta.

- [ ] **Step 1: Ajouter la dépendance (marqueur d'environnement pip)**

Dans `requirements.txt` :
```
mss>=9.0
pillow>=10.0
pyobjc-framework-Quartz; sys_platform == "darwin"
```

- [ ] **Step 2: Implémenter `_tts_rect_macos()`**

Remplacer le stub dans `app/screenshot.py` :
```python
def _tts_rect_macos():
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    for w in windows or []:
        name = w.get("kCGWindowOwnerName") or w.get("kCGWindowName") or ""
        if name.strip() != "Tabletop Simulator":
            continue
        bounds = w.get("kCGWindowBounds")
        if not bounds:
            return None
        x, y = int(bounds["X"]), int(bounds["Y"])
        w_, h_ = int(bounds["Width"]), int(bounds["Height"])
        if w_ < 100 or h_ < 100:
            return None
        return x, y, w_, h_
    return None
```

- [ ] **Step 3: Vérification statique (seule possible sans machine Mac)**

Run: `python -c "import ast; ast.parse(open('app/screenshot.py').read())"`
Expected: aucune sortie (pas d'erreur de syntaxe). Confirmer aussi que le module s'importe
toujours sans erreur sur Windows (l'import `Quartz` est bien à l'intérieur de la fonction, jamais
exécuté sur cette machine) :

Run: `python -c "import sys; sys.path.insert(0, 'app'); import screenshot; print('import OK')"`
Expected: `import OK`

- [ ] **Step 4: Commit**

```bash
git add app/screenshot.py requirements.txt
git commit -m "feat(screenshot): détection de la fenêtre TTS sur Mac via Quartz"
```

---

### Task 5: Détection de fenêtre sur Linux X11 (python-xlib)

**Files:**
- Modify: `app/screenshot.py`
- Modify: `requirements.txt`

**Même contrainte que Task 4** : pas de machine Linux disponible, vérification réelle via CI +
beta uniquement.

- [ ] **Step 1: Ajouter la dépendance**

Dans `requirements.txt` :
```
mss>=9.0
pillow>=10.0
pyobjc-framework-Quartz; sys_platform == "darwin"
python-xlib; sys_platform == "linux"
```

- [ ] **Step 2: Implémenter `_tts_rect_x11()`**

Remplacer le stub dans `app/screenshot.py` :
```python
def _tts_rect_x11():
    from Xlib import display

    d = display.Display()
    root = d.screen().root
    net_client_list = d.intern_atom("_NET_CLIENT_LIST")
    net_wm_name = d.intern_atom("_NET_WM_NAME")
    prop = root.get_full_property(net_client_list, 0)
    if not prop:
        return None
    for window_id in prop.value:
        win = d.create_resource_object("window", window_id)
        wm_name = win.get_full_property(net_wm_name, 0) or win.get_wm_name()
        name = (wm_name.value.decode("utf-8", "replace") if hasattr(wm_name, "value") else wm_name) or ""
        if name.strip() != "Tabletop Simulator":
            continue
        geom = win.get_geometry()
        coords = win.translate_coords(root, 0, 0)
        x, y = -coords.x, -coords.y
        w_, h_ = geom.width, geom.height
        if w_ < 100 or h_ < 100:
            return None
        return x, y, w_, h_
    return None
```

- [ ] **Step 3: Vérification statique (seule possible sans machine Linux)**

Run: `python -c "import ast; ast.parse(open('app/screenshot.py').read())"`
Expected: aucune sortie.

Run: `python -c "import sys; sys.path.insert(0, 'app'); import screenshot; print('import OK')"`
Expected: `import OK` (l'import `Xlib` est lazy, jamais exécuté sur cette machine Windows).

- [ ] **Step 4: Commit**

```bash
git add app/screenshot.py requirements.txt
git commit -m "feat(screenshot): détection de la fenêtre TTS sur Linux X11 via python-xlib"
```

---

### Task 6: Callback `on_capture_scope` dans `make_screenshotter`

**Files:**
- Modify: `app/screenshot.py:62-79`
- Test: `tests/verif_capture_scope_callback.py`

- [ ] **Step 1: Écrire le test (échoue : le paramètre n'existe pas encore)**

Créer `tests/verif_capture_scope_callback.py` :
```python
"""Vérifie que make_screenshotter() appelle on_capture_scope(found) à chaque capture, avec
found=True si _tts_client_rect() a trouvé la fenêtre TTS, False sinon — sans dépendre d'un vrai
écran (on monkeypatch _tts_client_rect)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import screenshot

calls = []
shoot = screenshot.make_screenshotter(on_capture_scope=lambda found: calls.append(found))

tmp = Path(tempfile.mkdtemp()) / "shot"

screenshot._tts_client_rect = lambda: (0, 0, 800, 600)
shoot(tmp)
assert calls == [True], calls

calls.clear()
screenshot._tts_client_rect = lambda: None
shoot(tmp)
assert calls == [False], calls

print("OK : make_screenshotter() rapporte via on_capture_scope si la fenêtre TTS a été trouvée")
```

- [ ] **Step 2: Lancer le test, confirmer l'échec**

Run: `python tests/verif_capture_scope_callback.py`
Expected: `TypeError: make_screenshotter() got an unexpected keyword argument 'on_capture_scope'`

- [ ] **Step 3: Implémenter le callback**

Dans `app/screenshot.py`, remplacer la fonction `make_screenshotter` :
```python
def make_screenshotter(max_width: int = 1920, quality: int = 85, on_capture_scope=None):
    def shoot(base: Path) -> Path | None:
        rect = _tts_client_rect()
        if on_capture_scope:
            try:
                on_capture_scope(rect is not None)
            except Exception:
                pass
        with mss.mss() as sct:
            if rect:
                x, y, w, h = rect
                region = {"left": x, "top": y, "width": w, "height": h}
            else:  # TTS introuvable : écran principal
                region = sct.monitors[1]
            raw = sct.grab(region)
        im = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
        out = Path(str(base) + ".jpg")
        im.save(out, "JPEG", quality=quality, optimize=True)
        return out

    return shoot
```

- [ ] **Step 4: Relancer le test, confirmer le succès**

Run: `python tests/verif_capture_scope_callback.py`
Expected: `OK : make_screenshotter() rapporte via on_capture_scope si la fenêtre TTS a été trouvée`

- [ ] **Step 5: Commit**

```bash
git add app/screenshot.py tests/verif_capture_scope_callback.py
git commit -m "feat(screenshot): callback on_capture_scope à chaque capture"
```

---

### Task 7: Brancher le callback dans `main.py`

**Files:**
- Modify: `app/main.py:129`

- [ ] **Step 1: Modifier l'appel à `make_screenshotter`**

Ligne actuelle :
```python
ui = Overlay(cfg, save_cfg, lambda ui: Controller(cfg, client, make_screenshotter(), ui))
```
Nouvelle version (le paramètre `ui` de la lambda est l'instance Overlay elle-même, déjà vivante
à ce point — cf. `Overlay.__init__` qui appelle `controller_factory(self)`) :
```python
ui = Overlay(cfg, save_cfg, lambda ui: Controller(
    cfg, client,
    make_screenshotter(on_capture_scope=lambda found: ui.emit("capture_scope", {"found": found})),
    ui))
```

- [ ] **Step 2: Vérifier que l'app démarre toujours**

Run: `python app/main.py`
Expected: l'overlay s'ouvre sans exception. Fermer pour terminer.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat(main): relie le callback de portée de capture à l'overlay"
```

---

### Task 8: Bannière "capture plein écran" dans l'overlay

**Files:**
- Modify: `app/overlay.py`
- Test: `tests/verif_capture_scope_banner.py`

- [ ] **Step 1: Écrire le test smoke (échoue : l'événement n'est pas géré)**

Créer `tests/verif_capture_scope_banner.py`, sur le modèle exact de `tests/verif_overlay.py`
(construction réelle d'un `Tk` root, pas de mock de Tkinter) :
```python
"""Vérifie que l'overlay affiche une bannière quand la fenêtre TTS n'est pas détectée
(ev == "capture_scope", found=False), et la masque quand elle est retrouvée ou cliquée."""
import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import overlay


class _FakeSession:
    my_color = "Red"
    game = {"captures": []}


class _FakeCtl:
    session = _FakeSession()


def run():
    cfg = {"replays_dir": "parties", "hotkey": "f8"}
    ui = overlay.Overlay(cfg, lambda c: None, lambda ui: _FakeCtl())
    try:
        ui._build_main("host")
        ui.root.update()
        assert not ui.lbl_capture_scope.winfo_ismapped(), "pas de bannière avant le premier ev"

        ui.emit("capture_scope", {"found": False})
        ui.root.update()
        assert ui.lbl_capture_scope.winfo_ismapped(), "bannière attendue quand found=False"
        assert "Tabletop Simulator" in ui.lbl_capture_scope.cget("text")

        ui.emit("capture_scope", {"found": True})
        ui.root.update()
        assert not ui.lbl_capture_scope.winfo_ismapped(), "bannière masquée quand found=True"

        ui.emit("capture_scope", {"found": False})
        ui.root.update()
        ui._dismiss_capture_scope()
        ui.root.update()
        assert not ui.lbl_capture_scope.winfo_ismapped(), "clic doit masquer la bannière"
    finally:
        ui.root.destroy()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print("OK : bannière 'capture plein écran' apparaît/disparaît correctement")
```

- [ ] **Step 2: Lancer le test, confirmer l'échec**

Run: `python tests/verif_capture_scope_banner.py`
Expected: `AttributeError: 'Overlay' object has no attribute 'lbl_capture_scope'`

- [ ] **Step 3: Ajouter le label, sur le modèle de `_layout_label`/`_apply_layout_banner`**

Dans `app/overlay.py`, juste après `_layout_label`/`_apply_layout_banner`/`_dismiss_layout`
(lignes 408-424 actuelles), ajouter :
```python
    def _capture_scope_label(self, parent, bg=BG):
        lbl = tk.Label(parent, text="", bg=bg, fg=AMBER, font=FONT, cursor="hand2",
                       wraplength=330, justify="left", padx=10, pady=4)
        lbl.bind("<Button-1>", lambda e: self._dismiss_capture_scope())
        self.lbl_capture_scope = lbl
        self._apply_capture_scope_banner()

    def _apply_capture_scope_banner(self):
        info = getattr(self, "_capture_scope_info", None)
        if info and hasattr(self, "lbl_capture_scope") and self.lbl_capture_scope.winfo_exists():
            self.lbl_capture_scope.config(
                text="⚠ Fenêtre Tabletop Simulator non détectée — capture de l'écran entier. "
                     "Clique pour masquer.")
            self.lbl_capture_scope.pack(fill="x")

    def _dismiss_capture_scope(self):
        self._capture_scope_info = None
        if hasattr(self, "lbl_capture_scope") and self.lbl_capture_scope.winfo_exists():
            self.lbl_capture_scope.pack_forget()
```

- [ ] **Step 4: Appeler `_capture_scope_label` dans `_build_main`**

Dans `_build_main`, juste après la ligne existante `self._layout_label(self.shell, bg=PANEL)`
(ligne ~503), ajouter :
```python
        self._capture_scope_label(self.shell, bg=PANEL)
```

- [ ] **Step 5: Gérer l'événement dans `_on`**

Dans `_on`, juste après le bloc `elif ev == "layout_warn": ...` (lignes 983-987 actuelles),
ajouter :
```python
        elif ev == "capture_scope":
            if p.get("found"):
                self._capture_scope_info = None
                if hasattr(self, "lbl_capture_scope") and self.lbl_capture_scope.winfo_exists():
                    self.lbl_capture_scope.pack_forget()
            else:
                self._capture_scope_info = p
                self._apply_capture_scope_banner()
            self._update_badge()
            self._relayout()
```

- [ ] **Step 6: Inclure la bannière dans le badge de statut**

Dans `_badge_status` (ligne ~220), la condition :
```python
        if getattr(self, "_update_info", None) or getattr(self, "_unfinished_info", None) \
           or getattr(self, "_layout_info", None) or getattr(self, "_finish_pending", False):
            return AMBER, True
```
devient :
```python
        if getattr(self, "_update_info", None) or getattr(self, "_unfinished_info", None) \
           or getattr(self, "_layout_info", None) or getattr(self, "_finish_pending", False) \
           or getattr(self, "_capture_scope_info", None):
            return AMBER, True
```

- [ ] **Step 7: Relancer le test, confirmer le succès**

Run: `python tests/verif_capture_scope_banner.py`
Expected: `OK : bannière 'capture plein écran' apparaît/disparaît correctement`

- [ ] **Step 8: Relancer le smoke-test existant de l'overlay (pas de régression)**

Run: `python tests/verif_overlay.py`
Expected: `OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)`

- [ ] **Step 9: Commit**

```bash
git add app/overlay.py tests/verif_capture_scope_banner.py
git commit -m "feat(overlay): bannière d'avertissement quand la capture retombe en écran entier"
```

---

### Task 9: Asset de mise à jour par OS (`update_check.py`)

**Files:**
- Modify: `app/update_check.py`
- Test: `tests/verif_update_check_asset.py`

- [ ] **Step 1: Écrire le test (échoue : la regex est encore fixe sur "windows")**

Créer `tests/verif_update_check_asset.py` :
```python
"""Vérifie que update_check choisit l'asset de la bonne plateforme (windows/macos/linux) parmi
les assets d'une Release GitHub simulée."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import update_check

assets = [
    {"name": "Servo-Skull-26.11.13-windows.zip", "browser_download_url": "u-win", "size": 1},
    {"name": "Servo-Skull-26.11.13-macos.zip", "browser_download_url": "u-mac", "size": 2},
    {"name": "Servo-Skull-26.11.13-linux.zip", "browser_download_url": "u-linux", "size": 3},
]

assert update_check._asset_name_re("win32").match("Servo-Skull-26.11.13-windows.zip")
assert not update_check._asset_name_re("win32").match("Servo-Skull-26.11.13-macos.zip")
assert update_check._asset_name_re("darwin").match("Servo-Skull-26.11.13-macos.zip")
assert update_check._asset_name_re("linux").match("Servo-Skull-26.11.13-linux.zip")

print("OK : update_check sélectionne l'asset de la bonne plateforme")
```

- [ ] **Step 2: Lancer le test, confirmer l'échec**

Run: `python tests/verif_update_check_asset.py`
Expected: `AttributeError: module 'update_check' has no attribute '_asset_name_re'`

- [ ] **Step 3: Remplacer la regex fixe par une fonction par plateforme**

Dans `app/update_check.py`, remplacer :
```python
ASSET_RE = re.compile(r"^Servo-Skull-.*-windows\.zip$")
```
par :
```python
_PLATFORM_SUFFIX = {"win32": "windows", "darwin": "macos", "linux": "linux"}


def _asset_name_re(platform: str) -> re.Pattern:
    suffix = _PLATFORM_SUFFIX.get(platform, _PLATFORM_SUFFIX["win32"])
    return re.compile(rf"^Servo-Skull-.*-{suffix}\.zip$")
```
Puis dans `check()`, remplacer la ligne qui filtre les assets :
```python
    asset = next((a for a in data.get("assets") or [] if ASSET_RE.match(a.get("name") or "")), None)
```
par :
```python
    asset_re = _asset_name_re(sys.platform)
    asset = next((a for a in data.get("assets") or [] if asset_re.match(a.get("name") or "")), None)
```
Et ajouter `import sys` en haut du fichier (actuellement seuls `json`, `re`, `urllib.error`,
`urllib.request` sont importés).

- [ ] **Step 4: Relancer le test, confirmer le succès**

Run: `python tests/verif_update_check_asset.py`
Expected: `OK : update_check sélectionne l'asset de la bonne plateforme`

- [ ] **Step 5: Commit**

```bash
git add app/update_check.py tests/verif_update_check_asset.py
git commit -m "feat(update_check): sélectionne l'asset de Release selon l'OS"
```

---

### Task 10: Dégrader l'auto-update hors Windows

**Files:**
- Modify: `app/overlay.py:343-376` (`_apply_update_banner`, `_open_update`)

- [ ] **Step 1: Lire le code actuel pour confirmer les lignes exactes**

Run: `grep -n "self_update.is_frozen" app/overlay.py`
Expected : deux occurrences, dans `_apply_update_banner` (ligne ~355) et `_open_update`
(ligne ~374).

- [ ] **Step 2: Restreindre l'auto-install à Windows**

Dans `_apply_update_banner`, la ligne :
```python
        elif self_update.is_frozen() and info.get("asset_url"):
```
devient :
```python
        elif sys.platform == "win32" and self_update.is_frozen() and info.get("asset_url"):
```

Dans `_open_update`, la ligne :
```python
        if not (self_update.is_frozen() and info.get("asset_url")):
```
devient :
```python
        if not (sys.platform == "win32" and self_update.is_frozen() and info.get("asset_url")):
```

(`sys` est déjà importé en haut de `app/overlay.py` — pas d'import à ajouter.)

- [ ] **Step 3: Vérifier qu'aucune régression Windows n'est introduite**

Run: `python tests/verif_overlay.py`
Expected: `OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)`
(ce test ne couvre pas directement la bannière de mise à jour, mais confirme l'absence
d'exception à la construction — `sys.platform == "win32"` est `True` sur cette machine, donc le
comportement Windows reste inchangé par construction.)

- [ ] **Step 4: Commit**

```bash
git add app/overlay.py
git commit -m "fix(overlay): auto-update un-clic réservé à Windows, lien manuel ailleurs"
```

---

### Task 11: CI — build Mac/Linux en matrice

**Files:**
- Modify: `.github/workflows/release.yml`

**Vérification réelle uniquement après push** : ce fichier ne peut pas être testé localement
(pas de `act` installé, et l'objectif est précisément de valider sur de vrais runners macOS/Linux
hébergés par GitHub). La vérification est au Step final de cette tâche : lire les logs du run.

- [ ] **Step 1: Séparer la création de la Release (une fois) du build (par OS)**

Remplacer tout le contenu de `.github/workflows/release.yml` par :
```yaml
name: release

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  prepare:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.version }}
      tag: ${{ steps.version.outputs.tag }}
      exists: ${{ steps.existing.outputs.exists }}
    steps:
      - uses: actions/checkout@v4

      - name: Lire VERSION (app/core.py)
        id: version
        shell: pwsh
        run: |
          $text = Get-Content app/core.py -Raw
          if ($text -notmatch 'VERSION\s*=\s*"([^"]+)"') {
            throw "VERSION introuvable dans app/core.py"
          }
          $version = $Matches[1]
          "version=$version" >> $env:GITHUB_OUTPUT
          "tag=v$version" >> $env:GITHUB_OUTPUT

      - name: Release déjà publiée ? (VERSION = signal explicite)
        id: existing
        shell: pwsh
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release view "${{ steps.version.outputs.tag }}" *> $null
          if ($LASTEXITCODE -eq 0) {
            "exists=true" >> $env:GITHUB_OUTPUT
          } else {
            "exists=false" >> $env:GITHUB_OUTPUT
          }
          exit 0

      - name: Créer la Release GitHub (vide, assets ajoutés par le job build)
        if: steps.existing.outputs.exists == 'false'
        shell: pwsh
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "${{ steps.version.outputs.tag }}" `
            --title "Servo-Skull ${{ steps.version.outputs.version }}" --generate-notes

  build:
    needs: prepare
    if: needs.prepare.outputs.exists == 'false'
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            suffix: windows
          - os: macos-latest
            suffix: macos
          - os: ubuntu-latest
            suffix: linux
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Dépendances
        run: pip install -r requirements.txt pyinstaller

      - name: Build (--onedir, comme empaqueter.bat)
        shell: pwsh
        run: |
          $sep = $IsWindows ? ';' : ':'
          $iconArgs = @()
          if ($IsWindows) { $iconArgs = @('--icon', 'app/assets/servo-skull.ico') }
          pyinstaller --noconfirm --onedir --windowed --name Servo-Skull --paths app `
            --add-data "app/recap_template.html${sep}." --add-data "app/assets${sep}assets" --add-data "app/data${sep}data" @iconArgs `
            app/main.py

      - name: Empaqueter le zip
        id: zip
        shell: pwsh
        run: |
          $built = if (Test-Path "dist/Servo-Skull.app") { "dist/Servo-Skull.app" } else { "dist/Servo-Skull" }
          $stage = "release/stage/Servo-Skull"
          New-Item -ItemType Directory -Force (Split-Path $stage) | Out-Null
          Copy-Item $built $stage -Recurse -Force
          Copy-Item LISEZMOI.md (Join-Path $stage "LISEZMOI.md")
          Copy-Item README.md (Join-Path $stage "LISEZ-MOI-D-ABORD.md")
          $zip = "release/Servo-Skull-${{ needs.prepare.outputs.version }}-${{ matrix.suffix }}.zip"
          Compress-Archive -Path $stage -DestinationPath $zip
          "path=$zip" >> $env:GITHUB_OUTPUT

      - name: Attacher le zip à la Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release upload "${{ needs.prepare.outputs.tag }}" "${{ steps.zip.outputs.path }}"
```

- [ ] **Step 2: Vérifier la syntaxe YAML localement**

Run: `python -c "import yaml, sys; yaml.safe_load(open('.github/workflows/release.yml'))" `
(si le module `yaml` n'est pas installé : `pip install pyyaml` d'abord, ou simplement relire le
fichier visuellement — l'indentation est le point de friction le plus probable en YAML.)
Expected: aucune exception.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "feat(ci): build et release Mac/Linux en plus de Windows"
```

- [ ] **Step 4: Vérification réelle après le prochain bump de VERSION**

Une fois cette tâche (et toutes les précédentes) mergées sur `main`, et un commit `Version :
X.Y.Z` poussé :

Run: `gh run list --limit 5`
Expected: un run `release` récent, avec deux jobs (`prepare`, puis `build` en matrice x3).

Run: `gh run view <run-id>` (remplacer `<run-id>` par l'id du run le plus récent)
Expected: `prepare` en succès, puis les 3 jobs `build (windows-latest)`, `build (macos-latest)`,
`build (ubuntu-latest)` tous en succès.

Run: `gh release view vX.Y.Z --json assets -q ".assets[].name"`
Expected: 3 fichiers listés — `Servo-Skull-X.Y.Z-windows.zip`, `-macos.zip`, `-linux.zip`.

Si un des jobs macOS/Linux échoue : lire son log (`gh run view <run-id> --log-failed`), corriger
le step en cause (le point le plus fragile est le chemin `dist/Servo-Skull.app` vs
`dist/Servo-Skull` sur macOS — ajuster la condition `Test-Path` si le nom réel diffère), commit,
et refaire un bump de `VERSION` pour re-déclencher.

---

### Task 12: Documenter la beta Mac/Linux

**Files:**
- Modify: `LISEZMOI.md`

- [ ] **Step 1: Ajouter une section courte en tête du fichier**

Dans `LISEZMOI.md`, juste après le premier bloc de description (avant `## Installation et mises
à jour`), ajouter :
```markdown
---

## Mac / Linux (beta)

Ces deux plateformes sont nouvelles et pas testées sur du vrai matériel — seule la CI confirme
que ça build et démarre. En particulier :
- Si Tabletop Simulator n'est pas détecté précisément (notamment sous Linux **Wayland**, où la
  détection de fenêtre n'est pas possible), une bannière ambre apparaît dans l'overlay pour te
  prévenir que la capture se fait sur l'écran entier plutôt que juste sur TTS.
- Pas de mise à jour automatique en un clic sur Mac/Linux pour l'instant : télécharger la
  nouvelle version manuellement depuis la page Releases.
- **Mac uniquement** : l'app n'est pas signée (pas de compte développeur Apple) — au premier
  lancement, macOS (Gatekeeper) bloquera l'ouverture. Clic droit sur l'app → **Ouvrir**, puis
  confirmer dans la popup. Une seule fois.

Un souci à signaler ? Un message sur le Discord avec ton OS exact (version de macOS/distribution
Linux + compositeur X11/Wayland) aide beaucoup.

---
```

- [ ] **Step 2: Relire le rendu**

Run: `python -c "print(open('LISEZMOI.md', encoding='utf-8').read()[:2000])"`
Expected: la nouvelle section s'affiche correctement, sans caractères mal encodés.

- [ ] **Step 3: Commit**

```bash
git add LISEZMOI.md
git commit -m "docs: section Mac/Linux (beta) dans LISEZMOI.md"
```

---

## Self-Review

**Couverture de la spec** (`docs/superpowers/specs/2026-11-12-portage-mac-linux-design.md`) :
- §1 (dépendances déjà gardées) : aucune tâche nécessaire, confirmé par l'exploration.
- §2 (capture ciblée Mac/Linux + bannière universelle) : Tasks 2-3-4-5 (détection) + 6-7-8
  (callback + bannière).
- §3 (dépendances `requirements.txt`) : Tasks 1, 4, 5.
- §4 (auto-update dégradé) : Tasks 9-10.
- §5 (CI matrice) : Task 11.
- §6 (rollout / beta) : Task 12 (doc) — l'annonce Discord elle-même reste une action manuelle de
  l'utilisateur, hors scope d'un plan de code.

Aucun écart trouvé entre la spec et les tâches.
