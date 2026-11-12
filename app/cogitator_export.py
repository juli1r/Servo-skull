"""Export du score d'une partie pour import dans Cogitator.

Contrairement à `contribution.py`, ce fichier n'anonymise rien : il est fait
pour être relu et importé par le joueur lui-même dans l'onglet Résultats/Vox
d'un event Cogitator, à côté de `recap.html` et du GIF."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import recap
from core import Session

SCHEMA = 1


def _last_score(captures: list[dict]) -> dict | None:
    """Score de la dernière capture qui en contient un (le plus à jour)."""
    for c in reversed(captures):
        score = c.get("score")
        if isinstance(score, dict) and score:
            return score
    return None


def _rounds(side_score: dict | None) -> list[dict]:
    rounds = (side_score or {}).get("rounds") or []
    out = []
    for r in rounds:
        if not isinstance(r, dict) or r.get("round") is None:
            continue
        out.append({
            "round": r.get("round"),
            "primary": r.get("primary") or 0,
            "secondary": r.get("secondary") or 0,
        })
    return out


def export(session: Session) -> Path | None:
    g = session.game
    score = _last_score(g.get("captures") or [])
    if not score:
        return None
    out = {
        "schema": SCHEMA,
        "date": g.get("created"),
        "myColor": g.get("myColor"),
        "players": g.get("players") or {},
        "sides": {
            side: {
                "vp": side_score.get("total") or 0,
                "rounds": _rounds(side_score),
            }
            for side, side_score in score.items()
            if isinstance(side_score, dict)
        },
    }
    path = session.dir / "resume-cogitator.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def export_film(session: Session) -> Path | None:
    """Film complet de la partie (même payload que le récap/mode live, sans les références
    locales), pour import manuel dans Cogitator — voir docs/superpowers/specs/
    2026-11-12-cogitator-film-export-design.md."""
    if not session.game.get("captures"):
        return None
    data = dict(recap.collect(session))
    data.pop("ttsSaves", None)
    data.pop("folder", None)
    data["captures"] = [{k: v for k, v in c.items() if k != "screenshot"} for c in data["captures"]]
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    path = session.dir / "film-cogitator.json.gz"
    path.write_bytes(gzip.compress(raw))
    return path
