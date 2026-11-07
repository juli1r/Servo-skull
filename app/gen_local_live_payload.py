"""Script ponctuel : génère site/local-payload.json à partir d'une partie déjà enregistrée, dans le
même format que ce que Firestore REST renverrait pour live_games/{code} (cf. live_share.push()),
pour itérer sur le rendu de site/live.html en local sans dépendre de Firestore.

Usage (depuis le dossier Servo-Skull) :
    python app/gen_local_live_payload.py [nom_du_dossier_dans_parties]
"""
from __future__ import annotations

import base64
import gzip
import json
import sys
from pathlib import Path

import recap
from core import Session

ROOT = Path(__file__).resolve().parent.parent
PARTIES_DIR = ROOT / "parties"
OUT_PATH = ROOT / "site" / "local-payload.json"


def latest_game_folder() -> Path:
    folders = [f for f in PARTIES_DIR.iterdir() if f.is_dir() and (f / "game.json").exists()]
    return sorted(folders)[-1]


def main() -> None:
    folder = PARTIES_DIR / sys.argv[1] if len(sys.argv) > 1 else latest_game_folder()
    session = Session.open(folder)
    raw = gzip.compress(json.dumps(recap.collect(session), ensure_ascii=False).encode("utf-8"))
    payload = base64.b64encode(raw).decode("ascii")
    OUT_PATH.write_text(json.dumps({"fields": {"payload": {"stringValue": payload}}}), encoding="utf-8")
    print(f"{OUT_PATH} généré depuis {folder.name}")


if __name__ == "__main__":
    main()
