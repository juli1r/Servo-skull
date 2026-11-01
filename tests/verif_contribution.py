"""Construit la contribution anonyme de chaque partie enregistrée, mesure la taille et vérifie l'absence de pseudo."""
import gzip, json, sys
from pathlib import Path
sys.path.insert(0, "app")
from core import Session
import contribution

root = Path("parties")
tot = 0
for d in sorted(root.iterdir()):
    if not (d / "game.json").exists() or not (d / "captures").exists():
        continue
    try:
        s = Session.open(d)
        if not s.game.get("captures"):
            continue
        data = contribution.build(s)
    except Exception as e:  # noqa: BLE001
        print(f"{d.name}: ECHEC {type(e).__name__}: {e}")
        continue
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    gz = len(gzip.compress(raw, 9))
    tot += gz
    names = [p for p in (s.game.get("players") or {}).values()]
    print(f"{d.name[:40]:40} caps={len(data['caps']):3} squads={len(data['squads']):3} brut={len(raw)//1024:4}Ko gz={gz//1024:3}Ko layout={data['layout']}")
print("total gz:", tot // 1024, "Ko")
