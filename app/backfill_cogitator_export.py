"""Script ponctuel : génère `resume-cogitator.json` pour toutes les parties
déjà enregistrées dans `parties/` qui n'en ont pas encore (ajouté après coup,
une fois que `finish_session()` a commencé à le générer automatiquement).

Usage (depuis le dossier Servo-Skull) :
    python app/backfill_cogitator_export.py
"""
from __future__ import annotations

from pathlib import Path

from core import Session
import cogitator_export

PARTIES_DIR = Path(__file__).resolve().parent.parent / "parties"


def main() -> None:
    created, skipped = [], []
    for folder in sorted(PARTIES_DIR.iterdir()):
        if not folder.is_dir() or not (folder / "game.json").exists():
            skipped.append((folder.name, "pas de game.json"))
            continue
        session = Session.open(folder)
        path = cogitator_export.export(session)
        if path is None:
            skipped.append((folder.name, "aucun score capturé"))
        else:
            created.append(folder.name)

    print(f"{len(created)} resume-cogitator.json créé(s)/mis à jour :")
    for name in created:
        print(f"  - {name}")
    print(f"\n{len(skipped)} dossier(s) ignoré(s) :")
    for name, reason in skipped:
        print(f"  - {name} ({reason})")


if __name__ == "__main__":
    main()
