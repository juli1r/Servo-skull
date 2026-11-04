"""Inactivité : le message du veilleur déclenche l'alerte, qui disparaît au changement de phase."""
import sys
sys.path.insert(0, "app")
from controller import Controller
from core import TurnTracker

class FakeClient:
    logs = []
    def log(self, m): self.logs.append(m)

c = Controller.__new__(Controller)
c.client = FakeClient()
c.state = {"phaseName": "Command Phase", "inGame": False}
emitted = []
c.emit = lambda ev, p=None: emitted.append((ev, p))
# partie pas (encore) lancée : pas d'alerte, le minuteur ne doit pas prévenir pour rien
c._on_stale({"stale": True, "json": '{"minutes": 5}'})
assert not emitted, emitted

c.state["inGame"] = True
c._on_stale({"stale": True, "json": '{"minutes": 5}'})
assert emitted and emitted[0][0] == "alert", emitted
txt = emitted[0][1]["text"]
print(txt)
assert "5 min" in txt and "pause" in txt
assert c._stale_alert is True
# message mal formé : pas de plantage
emitted.clear(); c._on_stale({"stale": True, "json": "pas du json"})
assert emitted[0][0] == "alert"
print("OK : alerte inactivité")
