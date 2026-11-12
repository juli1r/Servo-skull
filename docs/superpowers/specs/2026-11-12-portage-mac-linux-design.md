# Portage Mac/Linux — packaging + capture ciblée TTS

*2026-11-12*

## Contexte

Servo-Skull n'est distribué qu'en `.exe` Windows (`.github/workflows/release.yml` ne build que
sur `windows-latest`). Le code contient pas mal de dépendances Windows profondes, pas seulement
du packaging : `app/screenshot.py` utilise l'API `user32` pour retrouver précisément la fenêtre
"Tabletop Simulator" et n'y capturer que sa zone de rendu ; `app/overlay.py` utilise la feature Tk
`-transparentcolor` (Windows-only) pour la transparence couleur-clé, et quelques astuces DPI/icône
taskbar ; `app/self_update.py` installe les mises à jour via un script `.bat` + `robocopy`.

But : rendre l'app utilisable sur Mac et Linux, avec la même précision de capture que sur
Windows là où c'est techniquement possible, et un avertissement clair à l'utilisateur quand ça
ne l'est pas — plutôt qu'une dégradation silencieuse.

**Contrainte de test** : aucune machine Mac ou Linux physique disponible pour valider ce
portage. La vérification se fait via CI (confirme que ça build et démarre) ; la release sort
étiquetée beta avec un appel à retours sur Discord avant qu'on retire ce label.

## Périmètre

**Dans le périmètre :**
- Capture ciblée de la fenêtre TTS sur Mac (Quartz) et Linux X11 (Xlib)
- Détection Wayland + bannière d'avertissement universelle (3 OS) quand la fenêtre TTS n'est
  pas trouvée / pas détectable
- Build CI Mac + Linux (PyInstaller `--onedir`, matrice GitHub Actions)
- Dégradation propre de l'auto-update (manuel hors Windows) et de l'update_check (bon asset par OS)
- Retrait de la dépendance morte `pynput`

**Hors périmètre (reporté à une passe suivante, si le besoin est confirmé par les retours beta) :**
- Capture ciblée sous Wayland (nécessiterait `xdg-desktop-portal`, bien plus gros)
- Transparence couleur-clé équivalente à `-transparentcolor` sur Mac/Linux (l'overlay aura un
  fond uni au lieu de transparent partout sauf l'UI — cosmétique, pas bloquant)
- Auto-update un-clic sur Mac/Linux
- Signature de code Apple (pas de compte développeur) — Gatekeeper bloquera au premier lancement,
  documenté dans le `LISEZMOI.md` et le post beta (clic-droit → Ouvrir)

## Design

### 1. Capture ciblée TTS par OS (`app/screenshot.py`)

`_tts_client_rect()` se découpe par plateforme :

```python
def _tts_client_rect():
    if sys.platform == "win32":
        return _tts_rect_win32()      # code existant, inchangé
    if sys.platform == "darwin":
        return _tts_rect_macos()      # nouveau
    if sys.platform.startswith("linux"):
        if _is_wayland():
            return None
        return _tts_rect_x11()        # nouveau
    return None
```

- `_tts_rect_macos()` : `Quartz.CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly,
  kCGNullWindowID)`, filtre sur `kCGWindowOwnerName` / `kCGWindowName` == "Tabletop Simulator",
  lit `kCGWindowBounds` (x, y, w, h). Pas de permission système requise pour la géométrie seule.
- `_tts_rect_x11()` : `python-xlib`, parcourt les fenêtres top-level du display par défaut,
  matche `WM_NAME`/`WM_CLASS` sur "Tabletop Simulator", lit `get_geometry()` + translation vers
  les coordonnées écran (`translate_coords`).
- `_is_wayland()` : `os.environ.get("XDG_SESSION_TYPE") == "wayland" or "WAYLAND_DISPLAY" in
  os.environ`.
- Toute exception dans la détection (fenêtre fermée entre deux appels, lib absente, etc.) est
  capturée et traitée comme "non trouvée" — jamais de crash, comportement déjà en place côté
  Windows à reproduire tel quel.

### 2. Bannière "capture plein écran" — universelle, pas juste Mac/Linux

Aujourd'hui, quand `_tts_client_rect()` retourne `None` (TTS fermé, pas encore lancé, ou — après
ce changement — Wayland/détection indisponible), `make_screenshotter` retombe sur
`sct.monitors[1]` **silencieusement**, y compris sur Windows. On corrige ce point pour les trois
OS en même temps, puisque c'est le même chemin de code :

- `make_screenshotter(max_width, quality, on_capture_scope=None)` : `on_capture_scope(found:
  bool)` est appelé à chaque capture (`shoot()`), juste après la tentative de détection du rect.
- `Controller` (`app/controller.py`) relaie ce callback vers l'overlay via un `ui_hook` existant
  (même mécanisme que les autres notifications de session).
- `Overlay` (`app/overlay.py`) ajoute une bannière sur le modèle exact de
  `_unfinished_label`/`_apply_unfinished_banner` (lignes 387-406) : label ambre, texte
  `"⚠ Fenêtre Tabletop Simulator non détectée — capture de l'écran entier. Clique pour masquer."`,
  affichée au premier `on_capture_scope(False)` de la session, masquée au clic (comme les
  bannières existantes) ou automatiquement si une capture suivante retrouve la fenêtre.

### 3. Dépendances (`requirements.txt`)

*Environment markers* pip pour ne charger les libs natives que sur l'OS concerné :

```
mss>=9.0
pillow>=10.0
pyobjc-framework-Quartz; sys_platform == "darwin"
python-xlib; sys_platform == "linux"
```

`pynput` est retiré : plus utilisé dans le code (seule trace : un commentaire dans
`overlay.py:1054` qui parle d'un ancien mécanisme), inutile de le builder/tester sur 3 OS.

### 4. Auto-update dégradé hors Windows

- `app/update_check.py` : `ASSET_RE` devient une regex paramétrée par OS
  (`Servo-Skull-.*-windows\.zip` / `-macos\.zip` / `-linux\.zip` selon `sys.platform`), pour
  matcher le bon asset de la Release.
- `app/overlay.py` (`_apply_update_banner`, ligne ~355) : la branche "installer automatiquement"
  reste gardée par `self_update.is_frozen() and info.get("asset_url")` — sur Mac/Linux,
  `self_update.apply()` n'est simplement jamais appelé avec profit puisque le script de relais
  est un `.bat` ; on ajoute une garde explicite `sys.platform == "win32"` autour de l'appel à
  `self_update.apply()` pour que le texte du bandeau tombe toujours sur la branche "clique pour
  la page de téléchargement" hors Windows, plutôt que de tenter un `.bat` qui échouerait.

### 5. Build & CI (`.github/workflows/release.yml`)

- Le job `release` passe en matrice `os: [windows-latest, macos-latest, ubuntu-latest]`.
- Chaque job PyInstaller `--onedir` (même logique que `empaqueter.bat`), zippe en
  `Servo-Skull-<VERSION>-windows.zip` / `-macos.zip` / `-linux.zip`, tous attachés à la même
  Release GitHub (un seul tag `vX.Y.Z`, trois assets).
- `empaqueter.bat` reste tel quel pour un build local Windows ; pas de script `.sh` équivalent à
  maintenir — la logique de build Mac/Linux vit directement dans les steps du workflow CI, pour
  éviter la duplication entre deux scripts qu'on ne peut pas tester localement de toute façon.
- Pas de signature de code (ni Apple ni Windows) : documenté comme avant pour Windows
  (SmartScreen), et ajouté pour Gatekeeper côté Mac dans le `LISEZMOI.md`.

### 6. Rollout

- Prochain bump `VERSION` déclenche le build des 3 OS.
- Post Discord : annonce la beta Mac/Linux, mentionne explicitement que la bannière "capture
  plein écran" apparaîtra si la fenêtre TTS n'est pas détectée (Wayland notamment), et demande
  des retours avant de lever le label beta.

## Vérification

- CI : les 3 jobs de la matrice doivent terminer en succès et produire un zip par OS, attaché à
  la Release.
- Local (Windows, ce qu'on peut vérifier ici) : forcer `_tts_client_rect()` à retourner `None`
  (TTS fermé) et confirmer que la nouvelle bannière apparaît bien dans l'overlay, avec le bon
  texte, et se masque au clic — ça valide le mécanisme de callback/bannière sans dépendre de
  Mac/Linux.
- Beta Discord : retours de joueurs Mac/Linux sur (a) la précision de la capture TTS, (b)
  l'apparition correcte de la bannière quand elle doit apparaître, (c) tout crash au lancement.
