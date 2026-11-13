"""Vérifie que l'overlay affiche une bannière quand la fenêtre TTS n'est pas détectée
(ev == "capture_scope", found=False), la masque quand elle est retrouvée ou cliquée, et que
le masquage par clic est durable : il ne doit pas réapparaître aux captures suivantes tant que
TTS reste introuvable, seulement après un futur found=True."""
import sys, time, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import overlay


class _FakeSession:
    my_color = "Red"
    game = {"captures": []}


class _FakeCtl:
    session = _FakeSession()


def _pump(ui):
    """Laisse le temps à _drain() (root.after(80, ...)) de traiter la file avant update()."""
    time.sleep(0.1)
    ui.root.update()


def _shown(lbl):
    """Vrai si le label est géré par pack() (donc affiché), faux après pack_forget().
    Fenêtre overrideredirect + topmost : winfo_ismapped()/winfo_viewable() ne reflètent pas
    de façon fiable l'état réel sur cette config, y compris pour lbl_layout (banniere
    pré-existante, même symptôme) — winfo_manager() reste le signal correct et déterministe."""
    return lbl.winfo_manager() == "pack"


def run():
    cfg = {"replays_dir": "parties", "hotkey": "f8"}
    ui = overlay.Overlay(cfg, lambda c: None, lambda ui: _FakeCtl())
    try:
        ui._build_main("host")
        ui.root.update()
        assert not _shown(ui.lbl_capture_scope), "pas de bannière avant le premier ev"

        ui.emit("capture_scope", {"found": False})
        _pump(ui)
        assert _shown(ui.lbl_capture_scope), "bannière attendue quand found=False"
        assert "Tabletop Simulator" in ui.lbl_capture_scope.cget("text")

        ui.emit("capture_scope", {"found": True})
        _pump(ui)
        assert not _shown(ui.lbl_capture_scope), "bannière masquée quand found=True"

        ui.emit("capture_scope", {"found": False})
        _pump(ui)
        ui._dismiss_capture_scope()
        ui.root.update()
        assert not _shown(ui.lbl_capture_scope), "clic doit masquer la bannière"

        # masquage durable : tant que TTS reste introuvable, la bannière ne doit pas revenir
        ui.emit("capture_scope", {"found": False})
        _pump(ui)
        assert not _shown(ui.lbl_capture_scope), "masquage durable : pas de retour avant found=True"

        # retrouvée puis re-perdue : la bannière doit pouvoir réapparaître
        ui.emit("capture_scope", {"found": True})
        _pump(ui)
        ui.emit("capture_scope", {"found": False})
        _pump(ui)
        assert _shown(ui.lbl_capture_scope), "après un found=True, la bannière réapparaît si TTS est reperdu"
    finally:
        ui.root.destroy()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print("OK : bannière 'capture plein écran' apparaît/disparaît correctement")
