"""Vérifie que Session.flag_last_capture épingle un marqueur sur la DERNIÈRE capture, sans
texte, et qu'on peut en poser plusieurs sans limite."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session

root = Path(tempfile.mkdtemp())
s = Session(root, "Red", "host", {"Red": "Alice", "Blue": "Bob"})
assert s.flag_last_capture() is None, "rien à épingler sans capture"

m1 = s.add_capture({"round": 1, "turn": "Red", "unitJson": {}}, "auto_phase", turn_key=(1, "Red"))
flagged = s.flag_last_capture()
assert flagged["id"] == m1["id"]
assert s.game["captures"][0]["flagged"] is True

m2 = s.add_capture({"round": 1, "turn": "Blue", "unitJson": {}}, "auto_phase", turn_key=(1, "Blue"))
s.flag_last_capture()
assert s.game["captures"][0]["flagged"] is True, "le marqueur précédent reste en place"
assert s.game["captures"][1]["flagged"] is True, "la nouvelle dernière capture est marquée"

print("OK : Session.flag_last_capture épingle la dernière capture, plusieurs fois si besoin")
