"""Vérifie que `Controller.finish_session` prend bien une dernière capture (catchup) avant de
clore la partie, pour que le récap/score reflètent l'état réel au moment de "Terminer" et pas
seulement la dernière capture automatique (bug repéré en session : une partie terminée mi-round 5
sans capture derrière avait un score final amputé du dernier round)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session, TurnTracker
from controller import Controller


class _FakeClient:
    def run_lua(self, *a, **kw):
        return None


class _Recorder:
    def emit(self, ev, payload=None):
        pass

    def hide(self):
        pass

    def show(self):
        pass


root = Path(tempfile.mkdtemp())
session = Session(root, "Red", "guest", {"Red": "Alice", "Blue": "Bob"})
# une capture automatique "normale" avant la fin, comme en jeu réel
session.add_capture({"round": 5, "turn": "Blue", "unitJson": {}}, "auto_phase",
                     turn_key=(9, "Blue"), ended_phase="Shooting")
assert len(session.game["captures"]) == 1

ctl = Controller(cfg={}, client=_FakeClient(), ui_hooks=_Recorder())
ctl.session = session
ctl.tracker = TurnTracker(my_color="Red")
ctl.tracker.restore(9, "Blue")  # reprend au point où la vraie capture s'est arrêtée

ctl.finish_session()

assert len(session.game["captures"]) == 2, \
    "finish_session doit ajouter une capture finale avant de clore la partie"
last = session.game["captures"][-1]
assert last["kind"] == "catchup", f"la capture finale doit être de type catchup, eu {last['kind']!r}"
assert session.game["finished"] is True

print("OK : finish_session prend une dernière capture (catchup) avant de marquer la partie terminée")
