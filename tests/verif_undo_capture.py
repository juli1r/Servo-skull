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
