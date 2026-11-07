"""Fumée : construit l'overlay (écran de départ, carte dépliée host/invité, replier/déplier,
réduire) sans se connecter à TTS, pour attraper les erreurs Tk (option invalide, widget détruit…)
avant qu'un joueur les découvre en pleine partie — sous pythonw, une telle erreur ferme la fenêtre
sans aucun message."""
import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import overlay


class _FakeSession:
    def __init__(self, color):
        self.my_color = color
        self.game = {"captures": []}


class _FakeCtl:
    def __init__(self, color):
        self.session = _FakeSession(color)


def _factory(color):
    return lambda ui: _FakeCtl(color)


def run():
    cfg = {"replays_dir": "parties", "hotkey": "f8"}
    ui = overlay.Overlay(cfg, lambda c: None, _factory("Blue"))
    try:
        ui._build_start()
        ui.root.update()
        ui._build_main("host")
        ui.root.update()
        ui._undo_last_capture()  # aucune capture : ne doit pas lever d'exception
        ui.root.update()
        ui._toggle_shell()
        ui.root.update()
        ui._toggle_shell()
        ui.root.update()
        ui._toggle_shell()
        ui.root.update()
        ui._collapse()
        ui.root.update()
        ui.ctl = _FakeCtl("Red")
        ui._build_main("guest")
        ui.root.update()
    finally:
        ui.root.destroy()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print("OK : overlay construit sans erreur (départ, carte host/invité, replier/déplier, réduire)")
