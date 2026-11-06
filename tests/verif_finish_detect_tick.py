"""Rejoue une partie complète de 5 rounds à travers Controller.tick (pas seulement la fonction
pure is_final_phase_end) : c'est le seul moyen d'attraper deux bugs réels trouvés en revue —
(1) la détection ne se déclenchait jamais en mode "phases" (le mode par défaut), parce que la
branche était un elif après la branche de capture auto ; (2) le seq utilisé était celui
d'APRÈS l'avance du tracker, donc la bannière sortait un tour trop tôt (après le 1er tour du
round 5 au lieu du 2e)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session, PHASE_ORDER
from controller import Controller


def st(r, t, ph, in_game=True):
    return {"inGame": in_game, "round": r, "turn": t,
            "phase": ph, "phaseName": PHASE_ORDER[ph - 1] if ph else ""}


def full_game():
    seq = [st(0, "Blue", 0, False), st(1, "Blue", 1)]
    for r in range(1, 6):
        for t in ("Blue", "Red"):
            for ph in range(1, 6):
                seq.append(st(r, t, ph))
    seq.append(st(5, "Red", 5, False))  # fin de partie
    return seq


class _FakeClient:
    on_game_saved = None
    on_custom = None


class _Recorder:
    def __init__(self):
        self.events = []

    def emit(self, ev, payload=None):
        self.events.append((ev, payload))

    def hide(self):
        pass

    def show(self):
        pass


def run(cfg):
    root = Path(tempfile.mkdtemp())
    session = Session(root, "Red", "guest", {"Red": "Alice", "Blue": "Bob"})
    rec = _Recorder()
    ctl = Controller(cfg=cfg, client=_FakeClient(), ui_hooks=rec)
    ctl.session = session
    ctl.mode = "guest"
    from core import TurnTracker
    ctl.tracker = TurnTracker(my_color="Red")
    for s in full_game():
        ctl.tick(s)
    return [p for ev, p in rec.events if ev == "finish_suggest"]


suggestions = run({})  # auto_capture absent -> défaut "phases"
assert len(suggestions) == 1, f"attendu exactement 1 suggestion en mode phases, eu {suggestions}"
assert suggestions[0]["round"] == 5

suggestions_off = run({"auto_capture": "off"})
assert len(suggestions_off) == 1, f"attendu exactement 1 suggestion en mode off, eu {suggestions_off}"
assert suggestions_off[0]["round"] == 5

print("OK : finish_suggest se déclenche exactement une fois, au round 5, en mode phases et off")
