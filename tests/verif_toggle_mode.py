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
