"""Contribution anonyme : transforme les données d'une partie en un petit fichier sans donnée personnelle.

Principe : on part de ce qui sert au film (film.collect), puis on ne garde que ce qui sert aux statistiques
(composition des armées, mission, plan de table, positions, scores) et on retire tout le reste : pseudos
(remplacés par Joueur A / Joueur B), identifiants d'objets, captures d'écran, horodatages précis, notes libres,
noms de dossiers, liens. Le fichier n'est jamais envoyé automatiquement : il est écrit sur le disque et son contenu
peut être relu par l'utilisateur avant tout partage."""
from __future__ import annotations

import gzip
import json
import re
import uuid
from collections import Counter
from pathlib import Path

import film
from core import VERSION, Session

SCHEMA = 1
SIDE = {"Red": "A", "Blue": "B"}
KEEP_MISSION = ("redPrimary", "bluePrimary", "deployment", "twist", "redSecondary", "blueSecondary",
                "redSecondaryDone", "blueSecondaryDone", "redSecMode", "blueSecMode",
                "redDisposition", "blueDisposition")
NUM = (int, float)


def _side(c) -> str | None:
    return SIDE.get(c)


def _num(v, nd=1):
    return round(v, nd) if isinstance(v, NUM) and not isinstance(v, bool) else None


def _by_side(d) -> dict:
    """{"Red": x, "Blue": y} -> {"A": x, "B": y}, valeurs numériques ou petits dicts numériques seulement."""
    out = {}
    for k, v in (d or {}).items():
        s = _side(k)
        if not s:
            continue
        if isinstance(v, dict):
            v = {kk: _num(vv) for kk, vv in v.items() if isinstance(vv, NUM) and not isinstance(vv, bool)}
        elif isinstance(v, NUM) and not isinstance(v, bool):
            v = _num(v)
        else:
            continue
        out[s] = v
    return out


def _clean_name(n: str, secrets: list[str]) -> str:
    n = re.sub(r"\[[0-9a-fA-F]{6}\]|\[-\]", "", n or "")
    n = re.sub(r"[\x00-\x1f]", " ", n).strip()[:60]
    for s in secrets:
        n = re.sub(re.escape(s), "?", n, flags=re.I)
    return n or "?"


def _mission(m: dict, secrets: list[str]) -> dict:
    out = {}
    for k in KEEP_MISSION:
        v = (m or {}).get(k)
        if isinstance(v, str):
            out[k] = _clean_name(v, secrets)
        elif isinstance(v, list):
            out[k] = [_clean_name(x, secrets) for x in v if isinstance(x, str)]
    return out


def build(session: Session) -> dict:
    d = film.collect(session)
    g = session.game
    secrets = [p for p in (g.get("players") or {}).values() if isinstance(p, str) and len(p) >= 3]
    secrets += [session.dir.name]

    names = d.get("squadNames") or {}
    doubt = set(d.get("sidesDoubt") or [])
    caps_in = d["captures"]
    # camp de chaque escouade = camp majoritaire de ses figurines
    votes: dict = {}
    for c in caps_in:
        for u in c.get("units") or []:
            s = _side(d["sides"].get(u[0]))
            if s:
                votes.setdefault(u[9], Counter())[s] += 1
    keys = sorted({u[9] for c in caps_in for u in c.get("units") or []})
    idx = {k: i for i, k in enumerate(keys)}
    squads = []
    for k in keys:
        s = votes.get(k, Counter()).most_common(1)
        nm = names.get(k) or "?"
        sq = {"n": _clean_name(nm, secrets), "s": s[0][0] if s else None}
        if nm in doubt:
            sq["doubt"] = 1
        squads.append(sq)

    terrain, objectives = [], []
    caps = []
    for c in caps_in:
        if c.get("terrain"):
            terrain = [[_num(v, 2) for v in t] for t in c["terrain"]]
            objectives = [[_num(o[0], 2), _num(o[1], 2)] + [x for x in o[2:] if isinstance(x, (str, int))] for o in c.get("objectives") or []]
        units = [[idx[u[9]], u[2], u[3], _num(u[4]), _num(u[5])] for u in c.get("units") or []]
        t = c.get("turn")
        caps.append({"round": c.get("round"), "turn": _side(t) if isinstance(t, str) else t,
                     "phase": c.get("phaseName") if isinstance(c.get("phaseName"), str) else None,
                     "vp": _by_side(c.get("vp")), "cp": _by_side(c.get("cp")),
                     "score": _by_side(c.get("score")), "u": units})

    fit = d.get("layoutFit") or {}
    out = {
        "schema": SCHEMA, "app": VERSION,
        "id": _game_id(session),
        "month": (g.get("created") or "")[:7],
        "mode": g.get("mode"),
        "board": {"w": d["board"].get("w"), "d": d["board"].get("d")},
        "layout": _clean_name(str(fit.get("name") or ""), secrets) if fit.get("name") else None,
        "mission": _mission(d.get("mission"), secrets),
        "squads": squads, "terrain": terrain, "objectives": objectives, "caps": caps,
    }
    leak(out, secrets)
    return out


def _game_id(session: Session) -> str:
    """Identifiant aléatoire de la partie (jamais déduit des pseudos ni de la date) : sert uniquement à
    demander la suppression d'une partie déjà partagée."""
    p = session.dir / "contribution.id"
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        gid = uuid.uuid4().hex
        try:
            p.write_text(gid, encoding="utf-8")
        except OSError:
            pass
        return gid


def leak(obj: dict, secrets: list[str]) -> None:
    blob = json.dumps(obj, ensure_ascii=False).lower()
    for s in secrets:
        if s.lower() in blob:
            raise ValueError("donnée personnelle détectée dans la contribution : export refusé")


def export(session: Session) -> Path:
    """Écrit contribution.json.gz (et une copie lisible contribution.json) dans le dossier de la partie."""
    data = build(session)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (session.dir / "contribution.json").write_bytes(
        json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
    out = session.dir / "contribution.json.gz"
    out.write_bytes(gzip.compress(raw, 9))
    return out
