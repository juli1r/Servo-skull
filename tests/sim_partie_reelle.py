"""Rejoue les états TTS de la vraie partie du 27/10 (lus dans servo-skull.log) à travers TurnTracker.
Attendu : le joueur Rouge commence, 2 tours par round, rounds réels 1..4+, et toutes les phases vues ou rattrapées."""
import json, re, sys, collections
sys.path.insert(0, "app")
from core import TurnTracker, normalize_state

L = open("servo-skull.log", encoding="utf-8", errors="replace").read().splitlines()
start = [i for i, l in enumerate(L) if l.startswith("18:26:43")][-1]
states = []
for ln in L[start:]:
    if "id=4 " not in ln or "customMessage" not in ln:
        continue
    m = re.search(r'"json": "(.*)"\}, "messageID"', ln)
    if not m:
        continue
    try:
        states.append(json.loads(json.loads('"' + m.group(1) + '"')))
    except ValueError:
        pass
tr = TurnTracker(my_color="Red")
caps = collections.OrderedDict()
for st in states:
    st = normalize_state(st)
    for ev in tr.update(st):
        if ev[0] == "phase_ended":
            caps.setdefault(ev[1], []).append(ev[2])
for k, v in caps.items():
    print(k, len(v), v)
print("turnes:", len(caps), "dernier seq:", tr.seq)
