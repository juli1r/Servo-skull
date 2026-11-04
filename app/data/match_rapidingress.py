"""Script one-shot : recale les contours de décors « Dense Terrain » extraits de
rapidingress.com/40k-layout-reference (app/data/rapidingress_raw.json) sur le repère pouces PDF
de layouts_officiels.json, et écrit app/data/decor_shapes.json.

Ne tourne PAS à chaque build de l'app — seulement pour régénérer decor_shapes.json si
rapidingress_raw.json change. Usage : python app/data/match_rapidingress.py
"""
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _in_poly(x: float, z: float, poly: list) -> bool:
    ins = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, zi = poly[i]; xj, zj = poly[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi + 1e-12) + xi:
            ins = not ins
        j = i
    return ins


def _centroid(poly):
    return sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)


def _disp_pair(head: str):
    m = re.search(r'VS \| (.+?) \| MISSION', head)
    if not m:
        return None
    parts = m.group(1).split()
    # les deux dispositions sont concaténées sans séparateur net ; on les retrouve en
    # cherchant le plus petit découpage qui donne deux noms valides parmi les 5 connus.
    names = ["TAKE AND HOLD", "PURGE THE FOE", "DISRUPTION", "RECONNAISSANCE", "PRIORITY ASSETS"]
    txt = m.group(1)
    found = [n for n in names if txt.count(n) >= 1]
    # cas mirroir (même nom deux fois) vs paire : reconstruit en retirant la 1re occurrence trouvée
    for n in names:
        if txt.startswith(n):
            rest = txt[len(n):].strip()
            if rest in names:
                return frozenset([n, rest]) if n != rest else frozenset([n])
            if rest == n:
                return frozenset([n])
    return None


def _ri_disp_pair(title: str):
    names = ["Take and Hold", "Purge the Foe", "Disruption", "Reconnaissance", "Priority Assets"]
    t = title.split(" Layout")[0]
    if "(mirror)" in t:
        n = t.replace(" (mirror)", "").strip()
        return frozenset([n.upper()])
    if " vs " in t:
        a, b = t.split(" vs ")
        return frozenset([a.strip().upper(), b.strip().upper()])
    return None


def rotate(pts, deg, flip_x):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    out = []
    for x, y in pts:
        if flip_x:
            x = -x
        out.append((x * c - y * s, x * s + y * c))
    return out


def fit_similarity(src, dst):
    """src, dst : listes de points appariés (même longueur). Retourne (a, b, tx, ty) tel que
    X = a*x - b*y + tx ; Y = b*x + a*y + ty (rotation + échelle uniforme + translation, moindres
    carrés, sans réflexion — la réflexion est gérée en amont via `flip_x`)."""
    mx = sum(p[0] for p in src) / len(src)
    my = sum(p[1] for p in src) / len(src)
    MX = sum(p[0] for p in dst) / len(dst)
    MY = sum(p[1] for p in dst) / len(dst)
    num_a = num_b = den = 0.0
    for (x, y), (X, Y) in zip(src, dst):
        dx, dy, dX, dY = x - mx, y - my, X - MX, Y - MY
        num_a += dx * dX + dy * dY
        num_b += dx * dY - dy * dX
        den += dx * dx + dy * dy
    a, b = num_a / den, num_b / den
    tx = MX - (a * mx - b * my)
    ty = MY - (b * mx + a * my)
    return a, b, tx, ty


def apply_sim(pts, a, b, tx, ty):
    return [(a * x - b * y + tx, b * x + a * y + ty) for x, y in pts]


def nn_match(src, dst):
    """Apparie chaque point de src au plus proche de dst (dst peut être réutilisé plusieurs fois :
    pas un appariement bijectif strict, suffisant pour une estimation de résidu/transform)."""
    pairs = []
    for p in src:
        q = min(dst, key=lambda d: (d[0] - p[0]) ** 2 + (d[1] - p[1]) ** 2)
        pairs.append(q)
    return pairs


def best_orientation(their_pts, our_pts):
    """Essaie les 8 orientations orthogonales (4 rotations x flip) + fit bbox grossier, retourne
    la meilleure (résidu le plus faible) comme (a,b,tx,ty,résidu)."""
    oxmin, oxmax = min(p[0] for p in our_pts), max(p[0] for p in our_pts)
    oymin, oymax = min(p[1] for p in our_pts), max(p[1] for p in our_pts)
    best = None
    for flip_x in (False, True):
        for deg in (0, 90, 180, 270):
            rot = rotate(their_pts, deg, flip_x)
            rxmin, rxmax = min(p[0] for p in rot), max(p[0] for p in rot)
            rymin, rymax = min(p[1] for p in rot), max(p[1] for p in rot)
            sx = (oxmax - oxmin) / max(rxmax - rxmin, 1e-6)
            sy = (oymax - oymin) / max(rymax - rymin, 1e-6)
            coarse = [((x - rxmin) * sx + oxmin, (y - rymin) * sy + oymin) for x, y in rot]
            matched = nn_match(coarse, our_pts)
            a, b, tx, ty = fit_similarity(rot, matched)
            fitted = apply_sim(rot, a, b, tx, ty)
            matched2 = nn_match(fitted, our_pts)
            resid = sum(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(fitted, matched2)) / len(fitted)
            if best is None or resid < best[-1]:
                best = (deg, flip_x, a, b, tx, ty, resid)
    return best


def main():
    layouts = json.loads((HERE / "layouts_officiels.json").read_text(encoding="utf-8"))
    cards = json.loads((HERE / "rapidingress_raw.json").read_text(encoding="utf-8"))
    assert len(layouts) == len(cards) == 45

    out = []
    for i, (lay, card) in enumerate(zip(layouts, cards)):
        our_key = (_disp_pair(lay["head"]), lay["layout"])
        ri_key = (_ri_disp_pair(card["title"]), card["title"].rsplit(" ", 1)[-1])
        if our_key[0] != ri_key[0] or our_key[1] != ri_key[1]:
            print(f"MISMATCH page {lay['page']}: {our_key} vs {ri_key} ({card['title']!r})")
            continue

        our_foot = [[tuple(p) for p in f["poly"]] for f in lay["footprints"]]
        our_cent = [_centroid(p) for p in our_foot]
        their_grey_cent = [_centroid(poly) for poly in card["grey"]]

        deg, flip_x, a, b, tx, ty, resid = best_orientation(their_grey_cent, our_cent)
        if resid > 1.5:
            print(f"page {lay['page']}: résidu élevé ({resid:.2f}\"), ignoré")
            continue

        decors = []
        for green in card["green"]:
            rot = rotate(green, deg, flip_x)
            pts = apply_sim(rot, a, b, tx, ty)
            pts = [[round(x, 2), round(y, 2)] for x, y in pts]
            cx, cy = _centroid(pts)
            letters = sorted({l for f, poly in zip(lay["footprints"], our_foot) if _in_poly(cx, cy, poly)
                               for l in f["letters"]})
            if not letters:
                continue
            decors.append({"letters": letters, "poly": pts})

        out.append({"page": lay["page"], "residual": round(resid, 2), "decors": decors})
        print(f"page {lay['page']} ({lay['layout']}): résidu {resid:.2f}\", {len(decors)} décors recalés")

    (HERE / "decor_shapes.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(out)}/45 pages recalées -> decor_shapes.json")


if __name__ == "__main__":
    main()
