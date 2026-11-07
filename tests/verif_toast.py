"""Vérifie l'échappement XML du toast et le texte round/score construit pour chaque capture.
N'affiche jamais un vrai toast (pas d'appel à toast.show) : ce test reste silencieux et rapide."""
import sys
sys.path.insert(0, "app")
import toast
import controller

xml = toast.build_xml('R5 · tour "Rouge" <test>', "Score & victoire")
assert "<test>" not in xml, "le texte doit être échappé dans le XML du toast"
assert "&lt;test&gt;" in xml
assert "&amp;" in xml
assert xml.count("<text>") == 2
print("OK : toast.build_xml échappe correctement titre/texte")

meta = {"turnKey": [2, "Red"], "vp": {"Red": 12, "Blue": 7}}
assert controller._toast_text(meta) == "R2 · tour Rouge · 12-7"
meta2 = {"turnKey": None, "vp": {}}
assert controller._toast_text(meta2) == "Capture"
print("OK : controller._toast_text formate round/score (ou juste « Capture » si inconnu)")
