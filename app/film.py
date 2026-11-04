"""Génère film.html : le « film » de la partie, ouvrable hors ligne dans un navigateur."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from core import Session, parse_unit_name, strip_tags

OBJECTIVE = re.compile(r"objecti", re.I)
NOT_OBJECTIVE = re.compile(r"button|show|card|secondary|secondaire", re.I)
OBJ_LABELS = (("home", "Maison"), ("expansion", "Expansion"), ("cent", "Centre"))


def _obj_label(nm: str) -> str:
    low = nm.lower()
    for k, v in OBJ_LABELS:
        if k in low:
            return v
    return ""


def _squad_key(o: dict) -> str:
    for t in o.get("tags") or []:
        if isinstance(t, str) and t.startswith("uuid:"):
            return t
    return o["guid"]


def reduce_snapshot(snap: dict, board: dict, cache: dict | None = None) -> dict:
    """cache : {guid: (taille x, taille z, escouade)} et {"_terrain": ...} hérités des captures
    complètes précédentes, pour compléter les captures légères de fin de phase."""
    cache = cache if cache is not None else {}
    hw, hd = board["w"] / 2, board["d"] / 2
    units, terrain, objectives = [], [], []
    light = False
    for o in snap.get("objects", []):
        p, r, s = o["pos"], o.get("rot", {}), o.get("size", {})
        x, z, ry = round(p["x"], 2), round(p["z"], 2), round(r.get("y", 0), 1)
        sx, sz = round(s.get("x", 1), 2), round(s.get("z", 1), 2)
        if o.get("unit"):
            name, cur, mx = parse_unit_name(o.get("name", ""))
            if o.get("k") and o["guid"] in cache:
                light = True
                sx, sz, sq = cache[o["guid"]][:3]
            else:
                sq = _squad_key(o)
                cache[o["guid"]] = (sx, sz, sq, "leaderModel" in (o.get("tags") or []))
            lead = cache.get(o["guid"], (0, 0, 0, False))[3] if len(cache.get(o["guid"], ())) > 3 else False
            units.append([o["guid"], name, cur, mx, x, z, ry, sx, sz, sq, 1 if lead else 0])
            continue
        cen = o.get("center")
        if isinstance(cen, dict) and cen.get("x") is not None:
            x, z = round(cen["x"], 2), round(cen["z"], 2)  # centre réel du décor, pas son pivot
        if abs(x) > hw + 0.5 or abs(z) > hd + 0.5:
            continue
        nm = strip_tags(o.get("name", ""))
        gm = (o.get("gm") or "").strip()
        if gm == "objective" or (OBJECTIVE.search(nm) and not NOT_OBJECTIVE.search(nm) and max(sx, sz) <= 3):
            objectives.append([x, z, _obj_label(nm)])
        elif gm:
            continue  # zones de déploiement, quarts de table, etc. (notes GM du mod) : pas des décors
        elif not o.get("locked", True) or o.get("kind") in ("Custom_Token", "Card", "Deck", "Dice"):
            continue  # jetons (Action, Battle-shocked…) posés sur la table
        elif sx * sz >= 1.0 and max(sx, sz) < min(board["w"], board["d"]) * 0.9:
            flat = s.get("y", 1) < 0.3
            poly = 0
            foot = flat and not nm  # socles de zones de décor : plats et sans nom (assetbundle ou modèle selon le thème)
            if foot:
                snapped = snap_footprint(sx, sz)
                foot = snapped is not None
                if foot:
                    msx, msz = sx, sz
                    sx, sz, poly = snapped
                    if not poly:
                        x, z = exact_center(p["x"], p["z"], ry, x, z, sx, sz)
            terrain.append([x, z, ry, sx, sz, 1 if flat else 0, 1 if foot else 0, poly])
    if light and not terrain and "_terrain" in cache:
        terrain, objectives = cache["_terrain"]
    elif terrain:
        _official(terrain, cache)
        for ob in objectives:  # 11e : l'objectif, c'est la zone de décor sur laquelle tombe le point
            a = area_at(ob[0], ob[1], terrain)
            if a:
                ob.append(a)
        cache["_terrain"] = (terrain, objectives)
    return {"units": units, "terrain": terrain, "objectives": objectives}


# empreintes officielles 11e (Event Companion) : 6x4, 10x2,5, 6x2, 7x11,5, polygone 8x11,5
FOOTPRINTS = ((6.0, 4.0), (10.0, 2.5), (6.0, 2.0), (11.5, 7.0))


def snap_footprint(sx: float, sz: float) -> tuple[float, float, int] | None:
    """Les bornes TTS des socles de zone débordent un peu (≈ 0,5″) : on ramène aux cotes officielles."""
    a, b = max(sx, sz), min(sx, sz)
    if a > 11.7 and b > 7.7:
        w, h, poly = 11.5, 8.0, 1
    else:
        w, h = min(FOOTPRINTS, key=lambda f: abs(f[0] - a) + abs(f[1] - b))
        if abs(w - a) + abs(h - b) > 1.6:
            return None
        poly = 0
    return (w, h, poly) if sx >= sz else (h, w, poly)


def exact_center(px: float, pz: float, ry: float, cx: float, cz: float, w: float, h: float) -> tuple[float, float]:
    """Le pivot des socles LCT est un coin exact de l'empreinte (vérifié sur l'Event Companion :
    Maison bleue à 5″ / 5″ des bords). Les bornes TTS débordent, donc on repart du coin + cotes officielles."""
    import math
    th = math.radians(ry)
    c, s_ = math.cos(th), math.sin(th)
    dx, dz = cx - px, cz - pz
    lx, lz = dx * c + dz * s_, -dx * s_ + dz * c
    if abs(lx) < .5 or abs(lz) < .5:  # pivot pas dans un coin : on garde le centre des bornes
        return cx, cz
    ex, ez = math.copysign(w / 2, lx), math.copysign(h / 2, lz)
    return round(px + ex * c - ez * s_, 3), round(pz + ex * s_ + ez * c, 3)


# --- layouts officiels (Event Companion) ------------------------------------------------------
# data/layouts_officiels.json : 45 layouts, empreintes extraites du PDF (repère page : 44 x 60, attaquant en haut).
_LAY = None
DISPOSITIONS = ("TAKE AND HOLD", "PURGE THE FOE", "RECONNAISSANCE", "PRIORITY ASSETS", "DISRUPTION")


def _layouts() -> list:
    global _LAY
    if _LAY is None:
        try:
            _LAY = json.loads((Path(__file__).resolve().parent / "data" / "layouts_officiels.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _LAY = []
    return _LAY


def _cls_tts(t) -> str:
    if len(t) > 7 and t[7]:
        return "P"
    a, b = max(t[3], t[4]), min(t[3], t[4])
    return "L" if a > 11 else "S" if a > 9 else "M" if b > 3 else "m"


def _cls_pdf(f) -> str:
    if f.get("trap"):
        return "P"
    w, h = f["bbox"][2], f["bbox"][3]
    a, b = max(w, h), min(w, h)
    return "L" if a > 11 else "S" if a > 9 else "M" if b > 3.5 else "m"


def _pdf_world(u: float, v: float, sg: tuple) -> tuple:
    return round(sg[0] * (v - 30), 3), round(sg[1] * (u - 22), 3)


def fit_official(terrain: list):
    """Cherche, parmi les 45 layouts officiels, celui qui colle à la table (empreintes de même catégorie à moins de 1,2″)."""
    foot = [t for t in terrain if len(t) > 6 and t[6]]
    if len(foot) < 12:
        return None
    best = None
    for l in _layouts():
        pcs = [((f["bbox"][0] + f["bbox"][2] / 2), (f["bbox"][1] + f["bbox"][3] / 2), _cls_pdf(f), f) for f in l["footprints"]]
        for sg in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            W = [(*_pdf_world(u, v, sg), k, f) for u, v, k, f in pcs]
            ds, pairs = [], []
            for t in foot:
                c = [(math.hypot(t[0] - x, t[1] - z), (x, z, f)) for x, z, k, f in W if k == _cls_tts(t)]
                d, m = min(c, key=lambda a: a[0]) if c else (99.0, None)
                ds.append(d)
                pairs.append(m)
            n = sum(1 for d in ds if d <= 1.2)
            sc = (n, -sum(ds))
            if best is None or sc > best[0]:
                best = (sc, l, sg, ds, pairs)
    (n, _), l, sg, ds, pairs = best
    if n < max(12, len(foot) - 2):
        return None
    return {"page": l["page"], "layout": l["layout"], "n": n, "of": len(foot), "sg": sg,
            "mean": round(sum(ds) / len(ds), 2), "max": round(max(ds), 2), "head": l.get("head", ""), "pairs": pairs, "ds": ds, "foot": foot}


def _fit_name(head: str) -> str:
    found = sorted((head.find(d), d) for d in DISPOSITIONS if d in head)
    names = [d.title() for _, d in found]
    return (names[0] + " vs " + (names[1] if len(names) > 1 else names[0])) if names else ""


def layout_hint(captures: list) -> dict | None:
    """Identité du layout lue dans le jeu : paire de forces de disposition + numéro de la carte de
    déploiement (« PtF vs Dis 3 - … » : 1/2/3 = layout A/B/C, comme le fait le mod). Source de vérité : le choix
    fait par les joueurs, pas une déduction à partir des positions."""
    pair, idx = None, None
    for m in captures:
        c = m.get("cards") or {}
        if not isinstance(c, dict):
            continue
        r, b = (c.get("redDisposition") or "").upper(), (c.get("blueDisposition") or "").upper()
        if pair is None and r in DISPOSITIONS and b in DISPOSITIONS:
            pair = frozenset((r, b))
        if idx is None:
            for dn in c.get("deployment") or []:
                mm = re.search(r"\s(\d+)\s*-", str(dn))
                if mm and mm.group(1) in "123":
                    idx = "ABC"[int(mm.group(1)) - 1]
                    break
        if pair and idx:
            break
    return {"pair": pair, "letter": idx} if (pair or idx) else None


def _head_pair(head: str):
    found = [d for d in DISPOSITIONS if d in head]
    return frozenset(found * 2) if len(found) == 1 else frozenset(found)


def fit_layout(terrain: list, hint: dict | None = None):
    """Identifie le layout officiel (45 du Event Companion) de la table : pour chaque layout et chaque orientation,
    écart de chaque empreinte TTS à l'empreinte officielle la plus proche (plafonné à 6″). Accepté seulement si
    l'écart moyen est faible ET le layout est nettement meilleur que tous les autres."""
    foot = [t for t in terrain if len(t) > 6 and t[6]]
    if len(foot) < 8:
        return None
    cands = []
    pool = _layouts()
    if hint:  # identité connue : on ne cherche que parmi les layouts de cette paire (et cette lettre)
        sel = [l for l in pool if (not hint.get("pair") or _head_pair(l.get("head", "")) == hint["pair"])
               and (not hint.get("letter") or l["layout"] == hint["letter"])]
        pool = sel or pool
        known = bool(sel) and (len(sel) == 1)
    else:
        known = False
    for l in pool:
        for sg in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            cs = [_pdf_world(f["bbox"][0] + f["bbox"][2] / 2, f["bbox"][1] + f["bbox"][3] / 2, sg) for f in l["footprints"]]
            ds = [min(math.hypot(t[0] - x, t[1] - z) for x, z in cs) for t in foot]
            cands.append((sum(min(d, 6.0) for d in ds), l, sg, ds))
    cands.sort(key=lambda a: a[0])
    sc, l, sg, ds = cands[0]
    other = next((c for c in cands[1:] if c[1]["page"] != l["page"]), None)
    mean = sum(ds) / len(ds)
    if not known and (mean > 3.0 or (other and sc > 0.75 * other[0])):
        return None
    return {"page": l["page"], "layout": l["layout"], "n": sum(1 for d in ds if d <= 3.0), "of": len(foot), "sg": sg,
            "mean": round(mean, 2), "max": round(max(ds), 2), "head": l.get("head", ""), "l": l, "known": known,
            "far": sum(1 for d in ds if d > 2.0)}


def _pt_in(x: float, z: float, poly: list) -> bool:
    ins = False
    for a in range(len(poly)):
        (xa, za), (xb, zb) = poly[a], poly[a - 1]
        if (za > z) != (zb > z) and x < (xb - xa) * (z - za) / (zb - za) + xa:
            ins = not ins
    return ins


def overlap(foot: list, fit: dict) -> list:
    """Pour chaque décor TTS (rectangle tourné) : part de sa surface qui tombe dans un contour officiel du layout."""
    polys = [[list(_pdf_world(u, v, fit["sg"])) for u, v in f["poly"]] for f in fit["l"]["footprints"]]
    out = []
    for t in foot:
        th = math.radians(t[2]); c, s = math.cos(th), math.sin(th); hit = 0
        for i in range(12):
            for j in range(12):
                lx, lz = (i + .5) / 12 * t[3] - t[3] / 2, (j + .5) / 12 * t[4] - t[4] / 2
                x, z = t[0] + lx * c - lz * s, t[1] + lx * s + lz * c
                hit += any(_pt_in(x, z, p) for p in polys)
        out.append(hit / 144)
    return out


def _official(terrain: list, cache: dict) -> None:
    """Vérifie si la table correspond à un layout officiel (Event Companion) et note l'écart dans
    cache["_fit"] (utilisé pour l'alerte de conformité). Quand l'identification est fiable
    (fit["ok"]), les socles de zone ("foot") sont redessinés avec le contour officiel réel du PDF
    (t[7] devient la liste de points du polygone, pas un rectangle approximé — les empreintes ne
    sont PAS des rectangles, même tournés, mais des silhouettes détaillées de 20 à 70 points) ;
    les décors nommés gardent leur géométrie TTS mesurée."""
    memo = cache.setdefault("_fitmemo", {})
    key = tuple((round(t[0], 1), round(t[1], 1)) for t in terrain if len(t) > 6 and t[6])
    if key not in memo:
        fit = fit_layout(terrain, cache.get("_hint"))
        if fit:  # contrôle de forme : les décors TTS doivent vraiment recouvrir les contours du PDF
            ov = overlap([t for t in terrain if len(t) > 6 and t[6]], fit)
            fit["overlap"], fit["ov_min"] = sum(ov) / len(ov), min(ov)
            # identité lue dans le jeu : on ne rejette pas (rectangles TTS vs contours en L/trapèze : jamais 100 %)
            fit["ok"] = fit.get("known") or (fit["overlap"] >= 0.6 and fit["ov_min"] >= 0.25)
        memo[key] = fit
    fit = memo[key]
    if fit and not fit["ok"]:  # trop différent : pas d'identification fiable, on le signale
        cache["_fit"] = {"rejected": True, "page": fit["page"], "layout": fit["layout"], "overlap": round(fit["overlap"], 2)}
        return
    cache["_fit"] = ({k: fit[k] for k in ("page", "layout", "n", "of", "mean", "max", "overlap", "known", "far")} | {"name": _fit_name(fit["head"])}) if fit else None
    if fit:
        cache["_fit"]["zones"] = {k: [list(_pdf_world(u, v, fit["sg"])) for u, v in pts] for k, pts in (fit["l"].get("zones") or {}).items()}
        cs = [(_pdf_world(f["bbox"][0] + f["bbox"][2] / 2, f["bbox"][1] + f["bbox"][3] / 2, fit["sg"]), f) for f in fit["l"]["footprints"]]
        letters = []
        for t in terrain:
            if len(t) > 6 and t[6]:
                (cx, cz), f = min(cs, key=lambda cf: math.hypot(t[0] - cf[0][0], t[1] - cf[0][1]))
                poly = [list(_pdf_world(px, py, fit["sg"])) for px, py in f["poly"]]
                t[0], t[1], t[2] = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly), 0
                t[3], t[4] = f["bbox"][3], f["bbox"][2]
                if len(t) > 7:
                    t[7] = poly
                else:
                    t.append(poly)
                letters.append(f.get("letter"))
        cache["_fit"]["letters"] = letters


def _in_poly(x: float, z: float, poly: list) -> bool:
    ins = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, zi = poly[i]; xj, zj = poly[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi + 1e-12) + xi:
            ins = not ins
        j = i
    return ins


def area_at(x: float, z: float, terrain: list) -> list | None:
    best = None
    for t in terrain:
        if len(t) < 7 or not t[6]:
            continue
        if isinstance(t[7], list):
            ok = _in_poly(x, z, t[7])
        else:
            th = math.radians(t[2])
            dx, dz = x - t[0], z - t[1]
            lx, lz = dx * math.cos(th) + dz * math.sin(th), -dx * math.sin(th) + dz * math.cos(th)
            ok = abs(lx) <= t[3] / 2 + .05 and abs(lz) <= t[4] / 2 + .05
        if ok and (best is None or t[3] * t[4] < best[3] * best[4]):
            best = t
    return [best[0], best[1], best[2], best[3], best[4], best[7]] if best else None


def _base_name(n: str) -> str:
    n = re.split(r"\s+(?:w/|with|avec)\s+", n, maxsplit=1)[0]
    return n.strip() or "?"


UNIT_NAME = re.compile(r'unitName\s*=\s*"([^"]+)"')


def squad_names(caps: list[dict], units_dir: Path | None = None) -> dict:
    """Nom lisible de chaque fiche d'unité : celui écrit par l'import de liste dans le script
    de la figurine chef (« Purifier Squad »), sinon le nom de figurine le plus fréquent."""
    from collections import Counter, defaultdict
    names = defaultdict(Counter)
    guids = defaultdict(set)
    leaders = set()
    for c in caps:
        for u in c.get("units") or []:
            names[u[9]][_base_name(u[1])] += 1
            guids[u[9]].add(u[0])
            if len(u) > 10 and u[10]:
                leaders.add(u[0])
    out = {k: v.most_common(1)[0][0] for k, v in names.items()}
    if units_dir and units_dir.exists():
        for k, gs in guids.items():
            gs = sorted(gs, key=lambda g: g not in leaders)[:4]  # chef d'abord, 4 fichiers max
            for g in gs:
                p = units_dir / f"{g}.json"
                if not p.exists():
                    continue
                try:  # le script Lua de la figurine chef, une fois le JSON décodé (accents compris)
                    lua = json.loads(p.read_text(encoding="utf-8", errors="replace")).get("LuaScript") or ""
                    m = UNIT_NAME.search(lua[:200000])
                except (OSError, ValueError):
                    m = None
                if m:
                    out[k] = m.group(1)
                    break
    return out


MISSION_KEYS = ("redPrimary", "bluePrimary", "deployment", "twist", "redSecondary", "blueSecondary",
                "redSecondaryDone", "blueSecondaryDone", "redSecMode", "blueSecMode", "redDisposition", "blueDisposition")


def _zone_cat(n: str) -> str | None:
    m = re.match(r"^(Red|Blue)Sec(\d+)$", n)
    if m:
        return m.group(1).lower() + ("Secondary" if int(m.group(2)) <= 2 else "SecondaryDone")
    if re.match(r"^RedPrimary\d$", n):
        return "redPrimary"
    if re.match(r"^BluePrimary\d$", n):
        return "bluePrimary"
    return {"DeploymentSlot": "deployment", "TwistSlot": "twist"}.get(n)


def mission_from_save(path: Path) -> dict:
    """Même rangement que le script Lua de capture, mais depuis une sauvegarde TTS (parties anciennes)."""
    d = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    zones, cards, images = [], [], {}
    for o in d.get("ObjectStates") or []:
        t = o.get("Transform") or {}
        if o.get("Name") == "ScriptingTrigger":
            cat = _zone_cat(o.get("Nickname") or "")
            if cat:
                zones.append((cat, t.get("posX", 0), t.get("posZ", 0)))
        elif o.get("Name") in ("Card", "CardCustom"):
            n = o.get("Nickname") or ""
            if n and not n.startswith("Blank"):
                cards.append((n, t.get("posX", 0), t.get("posZ", 0), "layout_art_card" in (o.get("Tags") or [])))
                img = _card_face(o)
                if img:
                    images[n] = img
    out: dict = {}
    for o in d.get("ObjectStates") or []:
        if o.get("Nickname") == "Start Menu" and o.get("LuaScriptState"):
            try:
                st = json.loads(o["LuaScriptState"])
            except ValueError:
                break
            m = re.search(r"dispositionValues\s*=\s*\{([^}]*)\}", o.get("LuaScript") or "")
            vals = re.findall(r'"([^"]+)"', m.group(1)) if m else []
            for side in ("red", "blue"):
                k = st.get("sv%sDispositionSelected" % side)
                if isinstance(k, int) and 1 <= k <= len(vals):
                    out[side + "Disposition"] = vals[k - 1]
            break
    if not zones:
        return out
    for n, x, z, lay in cards:
        best = min(zones, key=lambda q: (q[1] - x) ** 2 + (q[2] - z) ** 2)
        if lay:
            out.setdefault("deployment", []).append(n)
        elif ((best[1] - x) ** 2 + (best[2] - z) ** 2) ** .5 < 6:
            if n == "Tactical Objectives" or n.startswith("Fixed"):
                out[best[0].split("Secondary")[0] + "SecMode"] = n
            else:
                out.setdefault(best[0], []).append(n)
    keep = {n for k, v in out.items() if isinstance(v, list) for n in v}
    if keep:
        out["images"] = {n: u for n, u in images.items() if n in keep}
    return out


def _card_face(o: dict) -> str | None:
    """Image de la carte (cartes seules 1x1 uniquement : c'est le cas des cartes de mission LCT)."""
    for deck in (o.get("CustomDeck") or {}).values():
        if deck.get("NumWidth", 1) == 1 and deck.get("NumHeight", 1) == 1 and deck.get("FaceURL"):
            return deck["FaceURL"]
    return None


def save_missions(session: Session) -> list[tuple]:
    """(round, turn, mission) pour chaque copie de sauvegarde TTS de la partie ; mis en cache (lecture lente)."""
    cache_p = session.dir / "missions-cache.json"
    try:
        cache = json.loads(cache_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    out, dirty = [], False
    for sv in session.game.get("ttsSaves") or []:
        f = sv.get("file")
        if not f or sv.get("round") is None:
            continue
        if f not in cache:
            p = session.dir / f
            if not p.exists():
                continue
            try:
                cache[f] = mission_from_save(p)
            except (OSError, ValueError):
                cache[f] = {}
            dirty = True
        out.append((sv["round"], sv.get("turn"), cache[f]))
    if dirty:
        try:
            cache_p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def turn_missions(snaps: list[tuple]) -> dict:
    """Par tour : secondaires en jeu (vues pendant le tour) et celles passées dans les cartes jouées ce tour-là."""
    by, order = {}, []
    for r, t, m in snaps:
        k = f"{r}|{t}"
        if k not in by:
            by[k] = []
            order.append(k)
        by[k].append(m)
    res, prev_done = {}, {"red": [], "blue": []}
    for k in order:
        e = {}
        for side in ("red", "blue"):
            act = []
            for m in by[k]:
                for n in m.get(side + "Secondary") or []:
                    if n not in act:
                        act.append(n)
            last_done = list(by[k][-1].get(side + "SecondaryDone") or [])
            new = list(last_done)
            for n in prev_done[side]:
                if n in new:
                    new.remove(n)
            prev_done[side] = last_done
            if act:
                e[side + "Secondary"] = act
            if new:
                e[side + "SecondaryDone"] = new
        res[k] = e
    return res


def _cap_snaps(caps: list[dict]) -> list[tuple]:
    out = []
    for c in caps:
        cd = c.get("cards") or {}
        if c.get("round") is not None and (cd.get("redPrimary") or cd.get("bluePrimary")):
            out.append((c["round"], c.get("turn"), cd))
    return out


def mission_of(session: Session, caps: list[dict]) -> dict:
    m = _mission_last(session, caps)
    snaps = _cap_snaps(caps) or save_missions(session)
    if snaps:
        imgs = dict(m.get("images") or {})
        for side in ("red", "blue"):
            seen = []
            for _, _, x in snaps:
                for n in (x.get(side + "Secondary") or []) + (x.get(side + "SecondaryDone") or []):
                    if n not in seen:
                        seen.append(n)
            if seen:
                m[side + "SecondarySeen"] = seen
        for _, _, x in snaps:
            for n, u in (x.get("images") or {}).items():
                imgs.setdefault(n, u)
        if imgs:
            m["images"] = imgs
        m["turns"] = turn_missions(snaps)
    return m


def _mission_last(session: Session, caps: list[dict]) -> dict:
    for c in reversed(caps):
        cd = c.get("cards") or {}
        if cd.get("redPrimary") or cd.get("bluePrimary"):
            return {k: cd.get(k) for k in MISSION_KEYS + ("images",) if cd.get(k)}
    sd = session.dir / "sauvegardes-tts"
    for p in sorted(sd.glob("*.json"), reverse=True) if sd.exists() else []:
        try:
            m = mission_from_save(p)
        except (OSError, ValueError):
            continue
        if m:
            return m
    return {}


def _primaries() -> dict:
    """Résumés des missions primaires 11e, repris de Cogitator (app/data/primaires_cogitator.json)."""
    try:
        return json.loads((Path(__file__).resolve().parent / "data" / "primaires_cogitator.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _single_model_keys(caps: list, units_dir: Path | None) -> set:
    """Fiches de personnages (mot-clé « Character » dans la fiche de l'unité, lue dans le script de la figurine chef) :
    un personnage est toujours une unité à 1 figurine, donc chaque figurine de cette fiche est une unité à elle seule."""
    out = set()
    if not units_dir or not units_dir.exists():
        return out
    leaders = {}
    for c in caps:
        for u in c.get("units") or []:
            if len(u) > 10 and u[10]:
                leaders.setdefault(u[9], u[0])
    for k, g in leaders.items():
        try:
            lua = json.loads((units_dir / f"{g}.json").read_text(encoding="utf-8", errors="replace")).get("LuaScript") or ""
        except (OSError, ValueError):
            continue
        i = lua.find("local unitData = {")
        j = lua.find("\n}", i) if i >= 0 else -1  # uniquement le bloc de données de la fiche, pas le code du script
        m = re.search(r'^\s*keywords\s*=\s*"([^"]*)"', lua[i:j], re.M) if i >= 0 and j > i else None
        if m and re.search(r"\bCharacter\b", m.group(1)):
            out.add(k)
    return out


def split_squads(caps: list, board: dict, units_dir: Path | None = None) -> int:
    """Deux unités de même fiche partagent parfois le même identifiant dans le mod (ex. 2 Slaughterbound, 2 Gretchin) :
    elles étaient fusionnées en une seule entrée. On les sépare d'après les positions : deux figurines d'un même identifiant
    qui ne peuvent pas appartenir à la même unité (plus de 24″ l'une de l'autre sur la table,
    sur au moins 2 captures et plus d'un quart des cas) ne sont jamais regroupées ; celles qui se tiennent ensemble (≤ 9″) le sont. Renvoie le nombre d'unités ajoutées."""
    hw, hd = board["w"] / 2 + .5, board["d"] / 2 + .5
    onb = lambda x, z: abs(x) <= hw and abs(z) <= hd
    per = {}  # clé d'escouade -> {capture -> {guid: (x, z)}}
    for ci, c in enumerate(caps):
        for u in c.get("units") or []:
            per.setdefault(u[9], {}).setdefault(ci, {})[u[0]] = (u[4], u[5])
    added, remap = 0, {}
    single = _single_model_keys(caps, units_dir)
    for key, frames in per.items():
        guids = sorted({g for fr in frames.values() for g in fr})
        if len(guids) < 2:
            continue
        if key in single:  # fiche à 1 figurine : autant d'unités que de figurines
            for n, g in enumerate(guids[1:], 2):
                remap[g] = f"{key}#{n}"
                added += 1
            continue
        together, apart = {}, {}
        for fr in frames.values():
            items = list(fr.items())
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    (ga, a), (gb, b) = items[i], items[j]
                    d = math.dist(a, b)
                    oa, ob = onb(*a), onb(*b)
                    pair = (ga, gb) if ga < gb else (gb, ga)
                    if oa and ob:
                        kind = "t" if d <= 9 else ("a" if d > 24 else None)
                    elif oa != ob:
                        kind = None  # l'une arrive des réserves : rien à en conclure
                    else:  # deux en réserve : ensemble s'ils sont voisins
                        kind = "t" if d < 12 else None
                    if kind == "t":
                        together[pair] = together.get(pair, 0) + 1
                    elif kind == "a":
                        apart[pair] = apart.get(pair, 0) + 1
        comp = {g: {g} for g in guids}
        for (ga, gb), n in sorted(together.items(), key=lambda kv: -kv[1]):
            ca, cb = comp[ga], comp[gb]
            if ca is cb:
                continue
            def _apart(x, y):
                k = (x, y) if x < y else (y, x)
                ap, tg = apart.get(k, 0), together.get(k, 0)
                return ap >= 2 and ap >= .25 * (ap + tg)
            if any(_apart(x, y) for x in ca for y in cb):
                continue  # incompatibles : jamais fusionnées
            ca |= cb
            for g in cb:
                comp[g] = ca
        groups = []
        for g in guids:
            if not any(comp[g] is gr for gr in groups):
                groups.append(comp[g])
        if len(groups) < 2:
            continue
        groups.sort(key=lambda gr: (-len(gr), min(gr)))  # la plus grosse garde la clé d'origine
        for n, gr in enumerate(groups[1:], 2):
            for g in gr:
                remap[g] = f"{key}#{n}"
            added += 1
    if remap:
        for c in caps:
            for u in c.get("units") or []:
                if u[0] in remap:
                    u[9] = remap[u[0]]
    return added


def _doubt_names(g: dict, caps: list, names: dict) -> list:
    """Noms des escouades dont le camp est incertain (à vérifier dans le film)."""
    doubt = set(g.get("sidesDoubt") or [])
    if not doubt:
        return []
    out = []
    for c in caps:
        for u in c.get("units") or []:
            if u[0] in doubt:
                n = names.get(u[9], u[1])
                if n not in out:
                    out.append(n)
    return out


def shift_command_moves(caps: list[dict]) -> int:
    """Les joueurs passent rarement la phase de Commandement : tout le mouvement est alors posé « pendant »
    le Commandement (aucune règle ne permet pourtant de déplacer des figurines à ce moment). Quand au moins 4 unités
    sont posées pendant cette phase et que la capture suivante est le Mouvement du même tour, on range ces
    déplacements en phase de Mouvement : la capture de Commandement garde les positions d'avant, et les déplacements
    (avec leur ordre) passent à la capture de Mouvement, annotée. Les données brutes ne sont pas modifiées."""
    done = 0
    for i, c in enumerate(caps):
        if i == 0 or (c.get("endedPhase") or "") != "Command":
            continue
        drops = [d for d in (c.get("drops") or []) if isinstance(d, list) and d]
        n = len({d[0] for d in drops})
        nxt, prev = (caps[i + 1] if i + 1 < len(caps) else None), caps[i - 1]
        if n < 4 or not nxt or (nxt.get("endedPhase") or "") != "Movement":
            continue
        if (nxt.get("round"), nxt.get("turn")) != (c.get("round"), c.get("turn")):
            continue
        if not prev.get("units") or not c.get("units"):
            continue
        before = {u[0]: u for u in prev["units"]}
        rolled = []
        for u in c["units"]:
            q = before.get(u[0])
            if q:
                u = list(u)
                u[4], u[5], u[6] = q[4], q[5], q[6]
            rolled.append(u)
        c["units"] = rolled
        nxt["drops"] = (nxt.get("drops") or []) + drops
        c["drops"] = []
        nxt["shiftedFrom"] = n
        done += 1
    return done


def collect(session: Session) -> dict:
    """Toutes les données du film (aussi utilisées pour le GIF)."""
    g = session.game
    board = g.get("board") or {"w": 60, "d": 44}
    caps, cache = [], {"_hint": layout_hint(g["captures"])}
    for m in g["captures"]:
        c = {k: m.get(k) for k in ("id", "kind", "label", "round", "turn", "phaseName", "vp", "cp",
                                    "score", "cards", "intent", "note", "screenshot", "time", "endedPhase", "drops", "approx")}
        if m.get("data"):
            snap = session.load_snapshot(m["id"])
            if snap:
                c.update(reduce_snapshot(snap, board, cache))
        caps.append(c)
    split_squads(caps, board, session.dir / "units")
    shift_command_moves(caps)
    names = squad_names(caps, session.dir / "units")
    for k in sorted(k for k in names if "#" in k):  # « Slaughterbound », « Slaughterbound (2) »
        if k.split("#")[0] in names and names[k] == names[k.split("#")[0]]:
            names[k] = f"{names[k]} ({k.split('#')[1]})"
    data = {"ttsSaves": [{k: m.get(k) for k in ("file", "label", "time", "round", "turn")}
                         for m in g.get("ttsSaves") or []],
            "squadNames": names, "myColor": g["myColor"], "players": g.get("players", {}), "board": board,
            "sides": g.get("sides", {}), "created": g.get("created"), "mode": g.get("mode"),
            "sidesDoubt": _doubt_names(g, caps, names),
            "redPositiveZ": g.get("redPositiveZ", True), "captures": caps, "mission": mission_of(session, caps), "primaries": _primaries(), "layoutFit": cache.get("_fit"), "folder": session.dir.name}
    return data


def build(session: Session) -> Path:
    data = collect(session)
    html = TEMPLATE.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    out = session.dir / "film.html"
    out.write_text(html, encoding="utf-8")
    return out


TEMPLATE = (Path(__file__).resolve().parent / "film_template.html").read_text(encoding="utf-8")
