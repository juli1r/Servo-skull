"""Construit site/stats.json (les statistiques agrégées de la page publique) à partir des contributions anonymes.

Entrées possibles :
  python tools/build_stats.py                       lit donnees_contributions/*.json (voir export_contributions.py)
  python tools/build_stats.py --local parties       construit les contributions à la volée depuis tes parties locales
Sortie : site/stats.json. Rien de personnel n'y entre : camps A/B, factions déduites, scores, dispositions.
La page ne lit jamais Firestore : c'est ce fichier, régénéré par toi, qui la nourrit."""
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tools"))

from factions import faction_of  # noqa: E402

MIN_GAMES = 8  # une partie plus courte (test, abandon) est ignorée


def wilson(w: int, n: int) -> tuple[int, int]:
    if n == 0:
        return 0, 0
    p, z = w / n, 1.96
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round(100 * (c - a) / d), round(100 * (c + a) / d)


def load_contributions(argv) -> list[dict]:
    if "--local" in argv:
        import contribution
        from core import Session
        root = Path(argv[argv.index("--local") + 1])
        out = []
        for d in sorted(root.glob("*")):
            if (d / "session.json").exists() or d.is_dir():
                try:
                    out.append(contribution.build(Session.open(d)))
                except Exception:
                    pass
        return out
    folder = ROOT / "donnees_contributions"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))
            if p.name != "resume.json"]


def one_game(c: dict, num: int) -> dict | None:
    caps = [x for x in (c.get("caps") or []) if x.get("round") is not None]
    if len(caps) < MIN_GAMES:
        return None
    last = (c["caps"][-1].get("score") or {})
    ta, tb = (last.get("A") or {}).get("total"), (last.get("B") or {}).get("total")
    if ta is None or tb is None:
        return None
    sq = c["squads"]
    m = c.get("mission") or {}
    dep = (m.get("deployment") or [""])[0]
    known = c.get("factions") or {}  # lue dans les règles d'armée par l'application ; à défaut, déduite des noms d'unités
    fa = known.get("A") or faction_of(sq, "A")
    fb = known.get("B") or faction_of(sq, "B")
    g = {"id": c["id"][:8], "month": c.get("month"), "layout": c.get("layout"), "deployment": dep.split(" - ")[-1],
         "dispoA": m.get("redDisposition"), "dispoB": m.get("blueDisposition"),
         "factionA": fa, "factionB": fb, "totalA": ta, "totalB": tb,
         "primA": (last.get("A") or {}).get("primary"), "primB": (last.get("B") or {}).get("primary"),
         "winner": "A" if ta > tb else "B" if tb > ta else "=", "margin": abs(ta - tb)}
    by = {}
    for cp in caps:
        by[cp["round"]] = cp
    rounds = []
    for r, cp in sorted(by.items()):
        row = {"r": r, "vpA": (cp.get("vp") or {}).get("A"), "vpB": (cp.get("vp") or {}).get("B")}
        for s in "AB":
            cur = mx = 0
            for u in cp["u"]:
                if sq[u[0]]["s"] == s:
                    cur += u[1]
                    mx += u[2]
            row["alive" + s], row["max" + s] = cur, mx
        rounds.append(row)
    g["rounds"] = rounds
    g["nrounds"] = len(rounds)
    lost = []
    final = c["caps"][-1]["u"]
    for i, s in enumerate(sq):
        cur = mx = 0
        for u in final:
            if u[0] == i:
                cur += u[1]
                mx += u[2]
        if mx and (mx - cur) / mx >= 0.4:
            lost.append({"unit": s["n"].split(" (")[0], "side": s["s"], "faction": fa if s["s"] == "A" else fb,
                         "lost_pct": round(100 * (mx - cur) / mx)})
    g["lost"] = lost
    return g


def agg(rows, key):
    out = {}
    for r in rows:
        o = out.setdefault(r[key], {key: r[key], "games": 0, "wins": 0, "vp": 0})
        o["games"] += 1
        o["wins"] += r["result"] == "V"
        o["vp"] += r["vp"]
    res = []
    for o in out.values():
        lo, hi = wilson(o["wins"], o["games"])
        res.append({key: o[key], "games": o["games"], "wins": o["wins"], "winrate": round(100 * o["wins"] / o["games"]),
                    "lo": lo, "hi": hi, "avg_vp": round(o["vp"] / o["games"], 1)})
    return sorted(res, key=lambda r: (-r["games"], -r["winrate"], str(r[key])))


def main(argv):
    games = [g for g in (one_game(c, i) for i, c in enumerate(load_contributions(argv))) if g]
    persp = []
    for g in games:
        for s, o in (("A", "B"), ("B", "A")):
            persp.append({"game": g["id"], "faction": g["faction" + s], "opp": g["faction" + o], "dispo": g["dispo" + s],
                          "vp": g["total" + s], "opp_vp": g["total" + o], "result": "V" if g["total" + s] > g["total" + o] else "D",
                          "deployment": g["deployment"]})
    mu = {}
    for r in persp:
        o = mu.setdefault((r["faction"], r["opp"]), {"faction": r["faction"], "opp": r["opp"], "games": 0, "wins": 0})
        o["games"] += 1
        o["wins"] += r["result"] == "V"
    stats = {"schema": 1, "updated": date.today().isoformat(), "min_reliable": 5, "games": games,
             "factions": agg(persp, "faction"), "dispositions": agg([r for r in persp if r["dispo"]], "dispo"),
             "matchups": list(mu.values()), "perspectives": persp}
    out = ROOT / "site"
    out.mkdir(exist_ok=True)
    blob = json.dumps(stats, ensure_ascii=False, indent=1)
    (out / "stats.json").write_text(blob, encoding="utf-8")
    (out / "stats.js").write_text("window.STATS = " + blob + ";\n", encoding="utf-8")  # la page s'ouvre aussi en double-clic
    print(f"{len(games)} parties -> site/stats.json et site/stats.js")


if __name__ == "__main__":
    main(sys.argv)
