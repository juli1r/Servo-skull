"""Vérifie que la table de chaque partie est identifiable comme un layout du Event Companion.
Usage: python tests/verif_layout.py [filtre]   (code retour 1 si une table à décors n'est pas reconnue / s'écarte)
Contrôles : layout reconnu parmi les 45 ; écart moyen <= 1,0" ; zones présentes. Le récap affiche
toujours la géométrie mesurée sur TTS (jamais une forme reconstituée du PDF), donc ce script ne
contrôle que l'IDENTIFICATION du layout, pas ce qui est dessiné."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from core import Session
import recap

root = Path(__file__).resolve().parent.parent / "parties"
only = sys.argv[1:]
bad = 0
for d in sorted(root.iterdir()):
    if not (d / "game.json").exists() or (only and not any(o in d.name for o in only)):
        continue
    try:
        data = recap.collect(Session.open(d))
    except Exception as e:
        print(f"ERREUR     {d.name}: {e}"); bad += 1; continue
    fit = data.get("layoutFit")
    foot = max((sum(1 for t in c.get("terrain") or [] if len(t) > 6 and t[6]) for c in data["captures"]), default=0)
    if foot == 0:
        print(f"sans décors {d.name}"); continue
    if not fit:
        print(f"NON RECONNUE {d.name} ({foot} décors) -> pas de layout officiel, carte approximative"); bad += 1; continue
    if fit.get("rejected"):
        print(f"REJETÉE    {d.name}: ressemble au layout {fit['layout']} (p.{fit['page']}) mais recouvrement {fit['overlap']:.0%} -> formes TTS affichées, à vérifier à la main"); bad += 1; continue
    probs = [] if fit.get("zones", {}).get("atk") else ["zones absentes"]
    print(("OK         " if not probs else "ÉCART      ") + f"{d.name}: {fit['name']} layout {fit['layout']} (PDF p.{fit['page']}), {fit['n']}/{fit['of']} décors, recouvrement des formes {fit['overlap']:.0%}" + (" | " + ", ".join(probs) if probs else ""))
    bad += bool(probs)
sys.exit(1 if bad else 0)
