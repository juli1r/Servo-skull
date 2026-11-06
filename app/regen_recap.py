"""Script ponctuel : régénère `recap.html` et `evolution-du-plan.gif` pour
toutes les parties déjà enregistrées, avec le rendu des décors à jour
(correctifs empreintes officielles du 4-5 novembre).

Usage (depuis le dossier Servo-Skull) :
    python app/regen_recap.py
"""
from __future__ import annotations

from pathlib import Path

import gif_render
import recap
from core import Session

PARTIES_DIR = Path(__file__).resolve().parent.parent / "parties"


def main() -> None:
    recap_ok, gif_ok, skipped = [], [], []
    for folder in sorted(PARTIES_DIR.iterdir()):
        if not folder.is_dir() or not (folder / "game.json").exists():
            skipped.append((folder.name, "pas de game.json"))
            continue
        try:
            session = Session.open(folder)
            recap.build(session)
            recap_ok.append(folder.name)
            gif_path = gif_render.render(recap.collect(session), folder / "evolution-du-plan.gif")
            if gif_path is not None:
                gif_ok.append(folder.name)
        except Exception as e:
            skipped.append((folder.name, f"erreur : {e}"))

    print(f"{len(recap_ok)} recap.html régénéré(s)")
    print(f"{len(gif_ok)} evolution-du-plan.gif régénéré(s)")
    print(f"\n{len(skipped)} dossier(s) ignoré(s)/en erreur :")
    for name, reason in skipped:
        print(f"  - {name} ({reason})")


if __name__ == "__main__":
    main()
