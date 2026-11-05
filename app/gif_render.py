"""GIF animé du plan, généré en Python (Pillow) à la fin de chaque partie.

Même dessin que le plan du récap (recap_template.html), simplifié : décors, objectifs,
figurines avec PV, noms d'unités, flèches de mouvement depuis la capture précédente,
figurines retirées, et un bandeau round / tour / phase / score.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG0, BG1, BG3, BORDER, BORDER2 = "#080b10", "#10141e", "#232c42", "#2a3348", "#354158"
T1, T2 = "#dde3f0", "#8e95a8"
RED, BLUE, AMBER, BOARD, WALL = "#f87171", "#378add", "#fbbf24", "#151b27", "#0d1119"
LIGHT = {"Red": "#fca5a5", "Blue": "#7db7f0"}
SIDE = {"Red": RED, "Blue": BLUE}
OTHER = {"Red": "Blue", "Blue": "Red"}
PHASE = {"Command": "Commandement", "Movement": "Mouvement", "Shooting": "Tir", "Charge": "Charge",
         "Fight": "Combat"}
PAD = 2.5


def _font(size: int, bold: bool = True):
    names = (["bahnschrift.ttf", "BarlowCondensed-SemiBold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold
             else ["bahnschrift.ttf", "arial.ttf", "DejaVuSans.ttf"])
    dirs = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path(".")]
    for n in names:
        for d in dirs:
            try:
                return ImageFont.truetype(str(d / n), size)
            except OSError:
                pass
    return ImageFont.load_default()


def _phase(n):
    n = (n or "").replace(" Phase", "")
    return PHASE.get(n, n)


_STOP = {"of", "the", "on", "and", "de", "du", "la", "le", "des"}


def _short(n):
    """Nom court pour la carte : coupe après « with … », retire les parenthèses, 18 caractères maximum."""
    n = re.sub(r"\s*\(.*?\)", "", n or "?")
    n = re.split(r"\s+(?:with|w/)\s+", n, flags=re.I)[0].strip()
    w = n.split()
    while len(" ".join(w)) > 18 and len(w) > 1:
        w.pop()
    while len(w) > 1 and w[-1].lower() in _STOP:
        w.pop()
    n = " ".join(w)
    return n if len(n) <= 18 else n[:17] + "…"


def _ov(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _clusters(pts, sizes, d=3.5):
    n = len(pts)
    par = list(range(n))

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a in range(n):
        for b in range(a + 1, n):
            if math.dist(pts[a], pts[b]) - sizes[a] / 2 - sizes[b] / 2 <= d:
                par[f(a)] = f(b)
    groups = {}
    for a in range(n):
        groups.setdefault(f(a), []).append(a)
    return list(groups.values())


def render(data: dict, out: Path, indices: list[int] | None = None, width: int = 960,
           frame_ms: int = 5000, last_ms: int = 8000) -> Path | None:
    caps = data["captures"]
    idx = [k for k in (indices if indices is not None else range(len(caps))) if caps[k].get("units")]
    if not idx:
        return None
    W, H = data["board"]["w"], data["board"]["d"]
    me = data["myColor"]
    sides = data.get("sides", {})
    names = data.get("squadNames", {})
    players = data.get("players", {})
    sgn = 1 if data.get("redPositiveZ", True) else -1
    red_down = me == "Red"
    SS = 2  # sur-échantillonnage : dessin en 2x puis réduction (bords lissés)
    w = width * SS
    s = w / (W + 2 * PAD)
    bar = 54 * SS
    h = bar + round((H + 2 * PAD) * s)
    f_lab, f_bar, f_score = _font(int(0.66 * s)), _font(24 * SS), _font(30 * SS)

    def P(x, z):
        px, pz = (-x, z * sgn) if red_down else (x, -z * sgn)
        return ((px + W / 2 + PAD) * s, (pz + H / 2 + PAD) * s + bar)

    def rot(ry):
        return math.radians(ry + 180 if red_down else ry)

    def poly(cx, cy, sx, sz, a, ellipse=False):
        c, si = math.cos(a), math.sin(a)
        if ellipse:
            pts = [(sx / 2 * math.cos(t), sz / 2 * math.sin(t)) for t in [i * math.pi / 14 for i in range(28)]]
        else:
            pts = [(-sx / 2, -sz / 2), (sx / 2, -sz / 2), (sx / 2, sz / 2), (-sx / 2, sz / 2)]
        return [(cx + (lx * c - ly * si) * s, cy + (lx * si + ly * c) * s) for lx, ly in pts]

    def on_board(u):
        return abs(u[4]) <= W / 2 + .5 and abs(u[5]) <= H / 2 + .5

    def alive(u):
        return u[2] != 0

    frames = []
    prev = None
    for n, k in enumerate(idx):
        c = caps[k]
        im = Image.new("RGB", (w, h), BG0)
        d = ImageDraw.Draw(im)
        # plateau
        x0, y0 = P(-W / 2, H / 2 * sgn) if red_down else P(-W / 2, H / 2 * sgn)
        bx0, by0 = PAD * s, bar + PAD * s
        bx1, by1 = bx0 + W * s, by0 + H * s
        d.rectangle([bx0, by0, bx1, by1], fill=BOARD, outline=BORDER, width=SS)
        for gx in range(6, int(W), 6):
            d.line([(bx0 + gx * s, by0), (bx0 + gx * s, by1)], fill=BORDER, width=1)
        for gz in range(6, int(H), 6):
            d.line([(bx0, by0 + gz * s), (bx1, by0 + gz * s)], fill=BORDER, width=1)
        bottom = "Red" if red_down else "Blue"
        d.rectangle([bx0, by1 - .3 * s, bx1, by1], fill=SIDE[bottom])
        d.rectangle([bx0, by0, bx1, by0 + .3 * s], fill=SIDE[OTHER[bottom]])
        # décors : zones au sol puis murs
        for t in sorted(c.get("terrain", []), key=lambda t: -t[5]):
            cx, cy = P(t[0], t[1])
            d.polygon(poly(cx, cy, t[3], t[4], rot(t[2])), fill=BG3 if t[5] else WALL,
                      outline=None if t[5] else BORDER2)
        # objectifs
        for o in c.get("objectives", []):
            cx, cy = P(o[0], o[1])
            r = 3.79 * s
            for a0 in range(0, 360, 20):
                d.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + 11, fill=AMBER, width=SS)
            r2 = .79 * s
            d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=AMBER)
        cur = {u[0]: u for u in c["units"]}
        # figurines retirées depuis la capture précédente
        if prev:
            for u in prev["units"]:
                if not on_board(u) or not alive(u):
                    continue
                nu = cur.get(u[0])
                if not nu or not on_board(nu) or not alive(nu):
                    cx, cy = P(u[4], u[5])
                    r = .55 * s
                    col = SIDE[sides.get(u[0], "Red")]
                    d.line([(cx - r, cy - r), (cx + r, cy + r)], fill=col, width=3 * SS)
                    d.line([(cx + r, cy - r), (cx - r, cy + r)], fill=col, width=3 * SS)
            # flèches de mouvement
            pm = {u[0]: u for u in prev["units"]}
            for u in c["units"]:
                p = pm.get(u[0])
                if not p or not on_board(u) or not on_board(p):
                    continue
                dist = math.hypot(u[4] - p[4], u[5] - p[5])
                if dist < .5:
                    continue
                side = sides.get(u[0], "Red")
                (x1, y1), (X, Y) = P(p[4], p[5]), P(u[4], u[5])
                rr = max(u[7], u[8]) / 2 + .15
                kk = max(0, (dist - rr) / dist)
                x2, y2 = x1 + (X - x1) * kk, y1 + (Y - y1) * kk
                col = LIGHT[side]
                d.line([(x1, y1), (x2, y2)], fill=col, width=2 * SS)
                a = math.atan2(y2 - y1, x2 - x1)
                L = .55 * s
                d.polygon([(x2, y2), (x2 - L * math.cos(a - .45), y2 - L * math.sin(a - .45)),
                           (x2 - L * math.cos(a + .45), y2 - L * math.sin(a + .45))], fill=col)
                r0 = .26 * s
                d.ellipse([x1 - r0, y1 - r0, x1 + r0, y1 + r0], outline=col, width=SS)
        # figurines
        groups = {}
        for u in c["units"]:
            if not on_board(u) or not alive(u):
                continue
            side = sides.get(u[0], "Red")
            cx, cy = P(u[4], u[5])
            a_, b_ = max(u[7], u[8]), min(u[7], u[8])
            hurt = u[2] is not None and u[3] is not None and u[2] < u[3]
            outline = AMBER if hurt else (T1 if side == me else BG0)
            if a_ - b_ < .15:
                r = a_ / 2 * s
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SIDE[side], outline=outline,
                          width=2 * SS if hurt else SS)
            else:
                d.polygon(poly(cx, cy, u[7], u[8], rot(u[6]), ellipse=a_ <= 4.5), fill=SIDE[side],
                          outline=outline)
            if u[3] and u[3] > 1:
                fs = max(.45, min(1.15, b_ * .34))
                txt = f"{u[2]}/{u[3]}"
                d.text((cx, cy), txt, fill=BG0, font=_font(int(fs * s)), anchor="mm")
            groups.setdefault(u[9], []).append(((cx, cy), max(u[7], u[8]) * s, u))
        # noms d'unités : courts, placés sans collision (dessus, dessous, côtés, puis plus loin avec un trait)
        boxes = [(p[0] - sz / 2, p[1] - sz / 2, p[0] + sz / 2, p[1] + sz / 2) for it in groups.values() for (p, sz, _u) in it]
        cl = []
        for sq, items in groups.items():
            pts = [it[0] for it in items]
            sizes = [it[1] for it in items]
            for grp in _clusters(pts, sizes, 3.5 * s):
                cl.append((sq, len(grp), min(pts[j][0] - sizes[j] / 2 for j in grp), min(pts[j][1] - sizes[j] / 2 for j in grp),
                           max(pts[j][0] + sizes[j] / 2 for j in grp), max(pts[j][1] + sizes[j] / 2 for j in grp)))
        cl.sort(key=lambda t: -t[1])
        placed, hl_ = [], max(1, int(.66 * s))
        for sq, n, x0, y0, x1, y1 in cl:
            label = _short(names.get(sq, "?")) + (f" ×{n}" if n > 1 else "")
            tw = d.textlength(label, font=f_lab)
            cx, cy, g, a, dn, F = (x0 + x1) / 2, (y0 + y1) / 2, .3 * s, hl_ * .85, hl_ * .25, 1.6 * s
            C = [(cx, y0 - g, 0), (cx, y1 + g + a, 0), (x0 + tw / 2, y0 - g, 0), (x1 - tw / 2, y0 - g, 0),
                 (x0 + tw / 2, y1 + g + a, 0), (x1 - tw / 2, y1 + g + a, 0), (x1 + g + tw / 2, cy + hl_ * .3, 0),
                 (x0 - g - tw / 2, cy + hl_ * .3, 0), (cx, y0 - g - F, 1), (cx, y1 + g + a + F, 1),
                 (x1 + g + F + tw / 2, cy - 1.2 * s, 1), (x0 - g - F - tw / 2, cy - 1.2 * s, 1)]
            best = None
            for ci, (px_, py_, lead) in enumerate(C):
                r = (px_ - tw / 2, py_ - a, px_ + tw / 2, py_ + dn)
                cost = ci * .02 + (.5 if lead else 0)
                cost += sum(_ov(r, b_) for b_ in boxes) / (s * s) + 4 * sum(_ov(r, b_) for b_ in placed) / (s * s)
                oob = max(0, bx0 - r[0]) + max(0, r[2] - bx1) + max(0, by0 - r[1]) + max(0, r[3] - by1)
                cost += 3 * oob * (r[3] - r[1]) / (s * s)
                if best is None or cost < best[0]:
                    best = (cost, px_, py_, lead, r)
            _, px_, py_, lead, r = best
            placed.append(r)
            if lead:
                sx, sy = min(max(px_, x0), x1), min(max((r[1] + r[3]) / 2, y0), y1)
                d.line([(sx, sy), (min(max(sx, r[0]), r[2]), min(max(sy, r[1]), r[3]))], fill=T2, width=SS)
            d.text((px_, py_), label, fill=T1, font=f_lab, anchor="ms",
                   stroke_width=max(2, int(.12 * s)), stroke_fill=BG0)
        # bandeau
        d.rectangle([0, 0, w, bar], fill=BG1)
        turn = c.get("turn")
        txt = (f"ROUND {c['round']} · {'MON TOUR' if turn == me else 'TOUR ADVERSE'}" if c.get("round") is not None
               else (c.get("label") or ""))
        if c.get("endedPhase"):
            txt += f" · FIN DE {_phase(c['endedPhase']).upper()}"
        elif c.get("kind") == "manual" and c.get("phaseName"):
            txt += f" · {_phase(c['phaseName']).upper()}"
        elif c.get("kind") == "auto_deploy":
            txt += " · DÉPLOIEMENT"
        d.text((18 * SS, bar / 2), txt, fill=SIDE.get(turn, T1), font=f_bar, anchor="lm")
        vp = c.get("vp") or {}
        rb = f"{vp.get('Blue', '–')}"
        xr = w - 18 * SS
        d.text((xr, bar / 2), rb, fill=BLUE, font=f_score, anchor="rm")
        xr -= d.textlength(rb, font=f_score) + 10 * SS
        d.text((xr, bar / 2), "–", fill=T2, font=f_bar, anchor="rm")
        xr -= d.textlength("–", font=f_bar) + 10 * SS
        d.text((xr, bar / 2), f"{vp.get('Red', '–')}", fill=RED, font=f_score, anchor="rm")
        frames.append(im.resize((width, h // SS), Image.LANCZOS))
        prev = c
    out = Path(out)
    durations = [frame_ms] * (len(frames) - 1) + [last_ms]
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=255) for f in frames]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=False,
                disposal=1)
    return out


if __name__ == "__main__":  # python gif_render.py <dossier de partie>
    sys.path.insert(0, str(Path(__file__).parent))
    from core import Session
    import recap
    sess = Session.open(Path(sys.argv[1]))
    print(render(recap.collect(sess), sess.dir / "evolution-du-plan.gif"))
