"""Cœur : session de capture, suivi des tours, camps, score, stockage."""
from __future__ import annotations

import json
import re
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

COLOR_TAG = re.compile(r"\[[0-9a-fA-F]{6}\]|\[-\]")
WOUNDS = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*")
BOARDS = {  # deployMode du mod -> (largeur x, profondeur z) en pouces
    "strikeForce": (60, 44),
    "incursion": (44, 30),
    "onslaught": (90, 44),
}
PHASE_FR = {
    "Command": "Commandement", "Movement": "Mouvement", "Shooting": "Tir",
    "Charge": "Charge", "Fight": "Combat",
}
VERSION = "26.11.02"  # affichée dans l'overlay et le journal : permet de savoir quelle version tourne
PHASE_ORDER = ["Command", "Movement", "Shooting", "Charge", "Fight"]  # numéro de phase dans TTS = position + 1
COLOR_FR = {"Red": "Rouge", "Blue": "Bleu"}
OTHER = {"Red": "Blue", "Blue": "Red"}


def strip_tags(s: str) -> str:
    return COLOR_TAG.sub("", s or "").strip()


def parse_unit_name(nick: str):
    """'[00ff16]14/16[-] Repex reroll' -> ('Repex reroll', 14, 16)"""
    clean = strip_tags(nick)
    m = WOUNDS.match(clean)
    if not m:
        return clean, None, None
    return clean[m.end():].strip(), int(m.group(1)), int(m.group(2))


def board_size(deploy_mode: str | None):
    return BOARDS.get(deploy_mode or "", BOARDS["strikeForce"])


# ------------------------------------------------------------------ score
def _as_list(x):
    if isinstance(x, dict):  # tableau Lua encodé en objet {"1":..}
        return [x[k] for k in sorted(x, key=lambda k: int(k))]
    return x or []


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def score_summary(scores, sheet: dict | None = None) -> dict | None:
    """Score détaillé à partir de la feuille de score du mod.
    - LCT 11e : colonnes BOARD_PRIMARY_K / BOARD_SECONDARY_K, points de fin de bataille,
      plafonds GAME_*_CAP lus dans le mod.
    - LCT 10e : 1 challenger, 2-3 secondaires, 4 primaire, plafonds 50/40/12.
    Joueur 1 = Rouge, 2 = Bleu ; +10 armée peinte."""
    sheet = sheet or {}
    scores = scores if scores is not None else sheet.get("scores")
    if not scores:
        return None
    def k(name, default=None):
        v = sheet.get(name)
        return int(v) - 1 if isinstance(v, (int, float)) else default
    if sheet.get("BOARD_PRIMARY_K") is not None:      # 11e édition
        pri = k("BOARD_PRIMARY_K")
        secs = [k("BOARD_SECONDARY_K")]
        chl = None
    elif sheet.get("BTN_K_IX_SECONDARY") is not None and sheet.get("BTN_K_IX_SECONDARY_1") is None:
        pri, secs, chl = k("BTN_K_IX_PRIMARY"), [k("BTN_K_IX_SECONDARY")], None
    else:                                             # 10e édition
        pri, secs, chl = k("BTN_K_IX_PRIMARY", 3), [k("BTN_K_IX_SECONDARY_1", 1), k("BTN_K_IX_SECONDARY_2", 2)], k("BTN_K_IX_CHALLENGER", 0)
    cap_p = _num(sheet.get("GAME_PRIMARY_CAP")) or 50
    cap_s = _num(sheet.get("GAME_SECONDARY_CAP")) or 40
    base = sheet.get("GAME_BASE_POINTS")
    base = 10 if base is None else _num(base)
    cap_t = _num(sheet.get("GAME_TOTAL_CAP")) or 100
    eob = _as_list(sheet.get("eob")) if sheet.get("eob") is not None else [0, 0]
    out = {}
    players = _as_list(scores)
    for pid, color in ((0, "Red"), (1, "Blue")):
        rounds = _as_list(players[pid]) if len(players) > pid else []
        per_round, P, S, C = [], 0.0, 0.0, 0.0
        for j, r in enumerate(rounds[:5]):
            r = [_num(v) for v in _as_list(r)] + [0, 0, 0, 0]
            p = r[pri] if pri is not None else 0
            s_ = sum(r[i] for i in secs if i is not None)
            c = r[chl] if chl is not None else 0
            per_round.append({"round": j + 1, "primary": p, "secondary": s_, "challenger": c, "total": p + s_ + c})
            P, S, C = P + p, S + s_, C + c
        P += _num(eob[pid]) if len(eob) > pid else 0
        P, S, C = min(P, cap_p), min(S, cap_s), min(C, 12)
        out[color] = {"primary": P, "secondary": S, "challenger": C, "painted": base,
                      "total": min(P + S + C + base, cap_t), "rounds": per_round}
    return out


def phase_label(name: str | None) -> str:
    n = (name or "").replace(" Phase", "").strip()
    return PHASE_FR.get(n, n)


def normalize_state(st: dict | None) -> dict | None:
    """Uniformise une lecture de la table, quelle que soit la version du mod."""
    if not isinstance(st, dict):
        return st
    if st.get("phaseName"):
        st["phaseName"] = st["phaseName"].replace(" Phase", "").strip()
    turns = st.get("turns") if isinstance(st.get("turns"), dict) else {}
    rnd = st.get("round")
    if not rnd:
        best = max([int(v) for v in turns.values() if isinstance(v, (int, float))] or [0])
        rnd = best or (1 if st.get("inGame") else None)
    st["round"] = int(rnd) if rnd else None
    sheet = st.get("sheet")
    sc = score_summary(None, sheet) if sheet else (score_summary(st.get("scores")) if st.get("scores") else None)
    if sc:
        st["score"] = sc
    vp = st.get("vp") if isinstance(st.get("vp"), dict) else {}
    if sc and not any(isinstance(v, (int, float)) for v in vp.values()):
        st["vp"] = {c: int(sc[c]["total"]) for c in sc}
    if not isinstance(st.get("cp"), dict):
        st["cp"] = {}
    return st


# ------------------------------------------------------------------ camps
def _army_rule_lines(abilities: str) -> set[str]:
    lines = strip_tags(abilities).split("\n")[1:]
    return {l.strip().replace("\xa0", " ") for l in lines if l.strip()}


def _resolve_ungrouped(pending_units, result, allu, lines, tints, pos_vote, doubt):
    """Unités sans règle d'armée dominante (ex. Witchseekers/Prosecutors : codex Custodes, mais sans « Martial Ka'tah »). La position au premier regard
    ne suffit pas (avant le déploiement, tout peut être posé n'importe où) : on croise avec
    - la teinte du modèle (ColorDiffuse) déjà vue sur des unités attribuées (ex. Custodes dorés) ;
    - les règles de l'unité déjà portées par des unités attribuées d'un seul camp ;
    - la position (faible, sauf réserves hors table).
    On propage : une unité attribuée avec assez de marge sert de preuve aux suivantes."""
    pending = {u["guid"]: u for u in pending_units}
    # (1, 1, 1) = teinte par défaut de TTS : ne prouve rien, donc ignorée
    tk = lambda g: (tuple(round(x, 2) for x in tints[g]) if tints.get(g) and tuple(round(x, 2) for x in tints[g]) != (1.0, 1.0, 1.0) else None)
    for _ in range(4):
        by_line = {"Red": Counter(), "Blue": Counter()}
        by_tint = {"Red": Counter(), "Blue": Counter()}
        for g, side in result.items():
            if g in pending or side not in by_line:
                continue
            for l in lines.get(g, ()):
                by_line[side][l] += 1
            k = tk(g)
            if k:
                by_tint[side][k] += 1
        scores = {}
        for g, u in pending.items():
            sc = {"Red": 0.0, "Blue": 0.0}
            k = tk(g)
            if k:
                r, b = by_tint["Red"][k], by_tint["Blue"][k]
                if r + b:
                    sc["Red"] += 4 * r / (r + b)
                    sc["Blue"] += 4 * b / (r + b)
            lw = 0
            for l in sorted(lines.get(g, ())):
                r, b = by_line["Red"][l], by_line["Blue"][l]
                if r + b and lw < 6:
                    sc["Red"] += 3 * r / (r + b)
                    sc["Blue"] += 3 * b / (r + b)
                    lw += 3
            side, w = pos_vote(u)
            sc[side] += w
            scores[g] = sc
        done = [g for g, sc in scores.items() if abs(sc["Red"] - sc["Blue"]) >= 3]
        for g in done:
            result[g] = "Red" if scores[g]["Red"] > scores[g]["Blue"] else "Blue"
            del pending[g]
        if not pending or not done:
            break
    for g, u in pending.items():  # encore douteuses : meilleur score, et on le signale
        sc = scores.get(g) or {"Red": 0.0, "Blue": 0.0}
        result[g] = ("Red" if sc["Red"] > sc["Blue"] else "Blue") if sc["Red"] != sc["Blue"] else pos_vote(u)[0]
        if doubt is not None:
            doubt.add(g)


def infer_sides(units: list[dict], known: dict[str, str], board_hd: float,
                red_positive_z: bool = True, tints: dict | None = None, doubt: set | None = None) -> dict[str, str]:
    """Attribue chaque unité à Red/Blue.
    1) GMNotes 'Red'/'Blue' si le mod les a posées ;
    2) sinon regroupement par règle d'armée (ligne d'aptitude commune, ex. 'Oath of Moment'),
       puis vote par position : réserves (z au-delà de la table) et moitié de table ;
    3) partie miroir (une seule règle d'armée) : position seule.
    Les attributions déjà faites ne bougent plus."""
    result = dict(known)
    todo = [u for u in units if u["guid"] not in result]
    if not todo:
        return result
    sign = 1 if red_positive_z else -1

    def pos_vote(u):
        z = u["pos"]["z"] * sign
        if z > board_hd + 8:
            return "Red", 3.0
        if z < -(board_hd + 8):
            return "Blue", 3.0
        return ("Red" if z > 0 else "Blue"), 1.0

    for u in todo:
        if u.get("gm") in ("Red", "Blue"):
            result[u["guid"]] = u["gm"]
    todo = [u for u in todo if u["guid"] not in result]
    if not todo:
        return result

    allu = units
    lines = {u["guid"]: _army_rule_lines(u.get("abilities", "")) for u in allu}
    cnt = Counter(l for s in lines.values() for l in s)
    groups: dict[str, str] = {}
    if cnt:
        a = cnt.most_common(1)[0][0]
        rest = [u for u in allu if a not in lines[u["guid"]]]
        b = None
        if rest:
            c2 = Counter(l for u in rest for l in lines[u["guid"]])
            if c2:
                cand, n = c2.most_common(1)[0]
                if n >= 0.6 * len(rest):
                    b = cand
        if b:
            for u in allu:
                s = lines[u["guid"]]
                if a in s and b not in s:
                    groups[u["guid"]] = "A"
                elif b in s and a not in s:
                    groups[u["guid"]] = "B"

    if groups:
        votes = {"A": Counter(), "B": Counter()}
        for u in allu:
            g = groups.get(u["guid"])
            if not g:
                continue
            if u["guid"] in result:  # déjà connu : vote fort
                votes[g][result[u["guid"]]] += 10
            else:
                side, w = pos_vote(u)
                votes[g][side] += w
        score_a = votes["A"]["Red"] - votes["A"]["Blue"] - (votes["B"]["Red"] - votes["B"]["Blue"])
        side_a = "Red" if score_a >= 0 else "Blue"
        side_of = {"A": side_a, "B": OTHER[side_a]}
        loose = []
        for u in todo:
            g = groups.get(u["guid"])
            if g:
                result[u["guid"]] = side_of[g]
            else:
                loose.append(u)
        _resolve_ungrouped(loose, result, allu, lines, tints or {}, pos_vote, doubt)
    else:
        _resolve_ungrouped(todo, result, allu, lines, tints or {}, pos_vote, doubt)
    return result


# ------------------------------------------------------------ suivi tours
@dataclass
class TurnTracker:
    """Transforme la suite des lectures (poll) en événements.
    Les tours sont numérotés ICI (seq 1, 2, 3… puis round = (seq+1)//2) : le compteur de rounds du mod
    se décale quand c'est le joueur Rouge qui commence, ce qui rangeait ton T1 dans « Round 2 »."""
    my_color: str
    alert_scope: str = "all"  # "all" ou "mine"
    prev: dict | None = None
    captured_turns: set = field(default_factory=set)
    seq: int = 0                      # numéro du tour depuis le début de la partie (1 = premier tour)
    cur_color: str | None = None
    cur_key: tuple | None = None

    @staticmethod
    def key(st: dict | None):
        if not st or st.get("round") is None or not st.get("turn"):
            return None
        return (int(st["round"]), st["turn"])

    def restore(self, seq: int | None, color: str | None):
        """Reprise d'une partie déjà commencée (relance de l'outil en cours de partie)."""
        if seq and color:
            self.seq, self.cur_color = int(seq), color
            self.cur_key = ((self.seq + 1) // 2, color)

    @staticmethod
    def _guess_seq(st: dict) -> int:
        """Pas d'historique : on déduit le numéro de tour depuis les compteurs du mod."""
        rnd = int(st.get("round") or 1)
        turns = st.get("turns") if isinstance(st.get("turns"), dict) else {}
        first = "Red" if (turns.get("Blue") == 0 and turns.get("Red") == 1) else "Blue"
        return 2 * (rnd - 1) + (1 if st.get("turn") == first else 2)

    def _advance(self, st: dict, p: dict | None, was_in: bool):
        if not st.get("inGame") or not st.get("turn"):
            return self.cur_key
        color = st["turn"]
        if p is not None and not was_in:           # début de partie : le premier à jouer = tour 1
            self.seq, self.cur_color = 1, color
        elif self.cur_color is None:               # première lecture sans historique
            self.seq, self.cur_color = self._guess_seq(st), color
        elif color != self.cur_color:              # l'autre joueur a pris la main
            self.seq, self.cur_color = self.seq + 1, color
        self.cur_key = ((self.seq + 1) // 2, color)
        return self.cur_key

    def mark_captured(self, key):
        if key:
            self.captured_turns.add(tuple(key))

    def update(self, st: dict) -> list[tuple]:
        ev = []
        p = self.prev
        self.prev = st
        pk = self.cur_key
        nk = self._advance(st, p, bool(p and p.get("inGame")))
        if p is None:
            return ev
        if st.get("inGame") and not p.get("inGame"):
            ev.append(("game_started", nk))
        same_turn = pk == nk
        # fin de mouvement : la phase quitte 2 (Movement), ou le tour passe pendant le mouvement
        if p.get("inGame") and p.get("phase") and (not same_turn or (st.get("phase") or 0) != p.get("phase") or not st.get("inGame")):
            ev.append(("phase_ended", pk, p.get("phaseName") or ""))
            if p.get("phase") == 2:
                ev.append(("movement_ended", pk))
            # phases passées trop vite pour être vues entre deux lectures : on les ajoute, dans l'ordre, pour que le film ait toujours les 5 phases
            try:
                pp, np_ = int(p.get("phase") or 0), int(st.get("phase") or 0)
                if pk and nk and 1 <= pp <= 5:
                    if not st.get("inGame"):   # fin de partie : les phases restantes du dernier tour sont closes d'office
                        ev += [("phase_ended", pk, PHASE_ORDER[i - 1]) for i in range(pp + 1, 6)]
                    elif same_turn and np_ > pp + 1:
                        ev += [("phase_ended", pk, PHASE_ORDER[i - 1]) for i in range(pp + 1, min(np_, 6))]
                    elif not same_turn:
                        ev += [("phase_ended", pk, PHASE_ORDER[i - 1]) for i in range(pp + 1, 6)]
                        ev += [("phase_ended", nk, PHASE_ORDER[i - 1]) for i in range(1, min(np_, 6))]
            except (TypeError, ValueError):
                pass
        if pk and nk and not same_turn:
            ev.append(("turn_changed", pk, nk))
            if pk not in self.captured_turns and (self.alert_scope == "all" or pk[1] == self.my_color):
                if p.get("inGame") and pk[0] >= 1:
                    ev.append(("missed_turn", pk))
        return ev


def turn_label(key) -> str:
    if not key:
        return "—"
    return f"R{key[0]} · tour {COLOR_FR.get(key[1], key[1])}"


# ---------------------------------------------------------------- session
def _slug(s: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", s or "", flags=re.UNICODE).strip().replace(" ", "-")
    return s[:40] or "x"


def find_unfinished_session(root: Path) -> dict | None:
    """Démarrage : la dernière partie du dossier n'a jamais été marquée « terminée »
    (fermeture anormale de l'outil, perte de connexion TTS…) — on prévient l'hôte
    plutôt que de laisser un film/score tronqué passer inaperçu."""
    try:
        folders = sorted((d for d in root.iterdir() if (d / "game.json").exists()),
                         key=lambda d: d.stat().st_mtime, reverse=True)
    except OSError:
        return None
    if not folders:
        return None
    d = folders[0]
    try:
        g = json.loads((d / "game.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if g.get("finished") or not g.get("captures"):
        return None
    last = g["captures"][-1]
    return {"dir": str(d), "name": d.name, "captures": len(g["captures"]), "last_round": last.get("turnKey")}


class Session:
    def __init__(self, root: Path, my_color: str, mode: str, players: dict | None = None,
                 red_positive_z: bool = True):
        self.my_color = my_color
        self.mode = mode  # "host" ou "guest"
        self.red_positive_z = red_positive_z
        players = players or {}
        now = datetime.now()
        name = f"{now:%Y-%m-%d_%Hh%M}"
        if players.get("Red") or players.get("Blue"):
            name += f"_{_slug(players.get('Red', 'Rouge'))}-vs-{_slug(players.get('Blue', 'Bleu'))}"
        self.dir = Path(root) / name
        (self.dir / "captures").mkdir(parents=True, exist_ok=True)
        (self.dir / "units").mkdir(exist_ok=True)
        self.game = {
            "version": 1, "created": now.isoformat(timespec="seconds"),
            "myColor": my_color, "mode": mode, "players": players,
            "redPositiveZ": red_positive_z, "sides": {}, "captures": [], "board": None,
            "finished": False,
        }
        self._save_game()

    # -- stockage
    def _save_game(self):
        tmp = self.dir / "game.json.tmp"
        tmp.write_text(json.dumps(self.game, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.dir / "game.json")

    def has_full_capture(self) -> bool:
        return any(m.get("data") and not m.get("light") for m in self.game["captures"])

    def known_unit_guids(self) -> list[str]:
        return [p.stem for p in (self.dir / "units").glob("*.json")]

    def spawn_json(self, guids) -> dict[str, str]:
        out = {}
        for g in guids:
            p = self.dir / "units" / f"{g}.json"
            if p.exists():
                out[g] = p.read_text(encoding="utf-8")
        return out

    # -- capture
    def add_capture(self, snap: dict | None, kind: str, intent: str = "", note: str = "",
                    screenshot: Path | None = None, manual_score: dict | None = None,
                    turn_key=None, label: str | None = None, ended_phase: str | None = None,
                    drops: list | None = None) -> dict:
        idx = len(self.game["captures"]) + 1
        cid = f"{idx:04d}"
        meta = {"id": cid, "kind": kind, "time": datetime.now().isoformat(timespec="seconds"),
                "intent": intent.strip(), "note": note.strip(), "screenshot": None,
                "endedPhase": (ended_phase or "").replace(" Phase", "") or None}
        if drops:
            meta["drops"] = [d for d in drops if isinstance(d, list) and len(d) >= 4][:3000]
        if snap:
            for g, js in (snap.get("unitJson") or {}).items():
                (self.dir / "units" / f"{g}.json").write_text(js, encoding="utf-8")
            snap = {k: v for k, v in snap.items() if k != "unitJson"}
            meta["light"] = not any(not o.get("k") and not o.get("unit") for o in snap.get("objects", [])) \
                and any(o.get("k") for o in snap.get("objects", []))
            hw, hd = board_size(snap.get("deployMode"))
            self.game["board"] = {"w": hw, "d": hd, "deployMode": snap.get("deployMode")}
            units = [o for o in snap.get("objects", []) if o.get("unit")]
            doubt = set(self.game.get("sidesDoubt") or [])
            self.game["sides"] = infer_sides(units, self.game["sides"], hd / 2, self.red_positive_z,
                                             self._tints(u["guid"] for u in units), doubt)
            self.game["sidesDoubt"] = sorted(doubt)
            for c, n in (snap.get("players") or {}).items():
                self.game["players"].setdefault(c, n)
            normalize_state(snap)
            score = snap.get("score") or score_summary(snap.get("scores"))
            key = turn_key or TurnTracker.key(snap)
            meta.update({
                "round": key[0] if key else snap.get("round"),
                "turn": key[1] if key else snap.get("turn"), "phase": snap.get("phase"),
                "phaseName": snap.get("phaseName"), "vp": snap.get("vp"), "cp": snap.get("cp"),
                "score": score, "cards": snap.get("cards"), "turnKey": list(key) if key else None,
            })
            (self.dir / "captures" / f"{cid}.json").write_text(
                json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            meta["data"] = f"captures/{cid}.json"
        else:
            key = turn_key
            meta["turnKey"] = list(key) if key else None
            if manual_score:
                meta["vp"] = manual_score.get("vp")
                meta["round"] = manual_score.get("round")
                meta["turn"] = manual_score.get("turn")
        if screenshot and Path(screenshot).exists():
            dest = self.dir / "captures" / f"{cid}{Path(screenshot).suffix}"
            shutil.move(str(screenshot), str(dest))
            meta["screenshot"] = f"captures/{dest.name}"
        meta["label"] = label or self._label(meta)
        self.game["captures"].append(meta)
        self._save_game()
        return meta

    def _label(self, m: dict) -> str:
        parts = []
        if m.get("round") is not None:
            parts.append(f"R{m['round']}")
        if m.get("turn"):
            parts.append(f"tour {COLOR_FR.get(m['turn'], m['turn'])}")
        if m.get("phaseName") and m["kind"] == "manual":
            parts.append(PHASE_FR.get(m["phaseName"], m["phaseName"]))
        kinds = {"auto_move": "fin de Mouvement (auto)", "auto_deploy": "déploiement (auto)",
                 "catchup": "fin de tour (rattrapage)"}
        if m["kind"] == "auto_phase":
            parts.append(f"fin de {PHASE_FR.get(m.get('endedPhase') or '', m.get('endedPhase') or 'phase')} (auto)")
        elif m["kind"] in kinds:
            parts.append(kinds[m["kind"]])
        return " · ".join(parts) or f"Capture {m['id']}"

    # ------------------------------------------------- sauvegardes TTS
    def keep_tts_save(self, src: Path, state: dict | None) -> dict | None:
        import hashlib
        src = Path(str(src).replace("//", "/"))
        data = None
        for _ in range(10):  # TTS peut être encore en train d'écrire le fichier
            try:
                raw = src.read_bytes()
                json.loads(raw.decode("utf-8-sig"))
                data = raw
                break
            except (OSError, ValueError):
                time.sleep(0.5)
        if data is None:
            return None
        digest = hashlib.sha1(data).hexdigest()
        saves = self.game.setdefault("ttsSaves", [])
        if saves and saves[-1].get("sha1") == digest:
            return None  # rien n'a changé depuis la dernière copie
        st = state or {}
        rnd, turn = st.get("round"), st.get("turn")
        stamp = datetime.now()
        label = (f"R{rnd} · tour {COLOR_FR.get(turn, turn)}" if rnd and turn else "avant la partie")
        if st.get("phaseName") and st.get("inGame"):
            label += f" · {PHASE_FR.get(st['phaseName'], st['phaseName'])}"
        name = f"{stamp:%H%M%S}_" + (f"R{rnd}_{turn}" if rnd and turn else "hors-partie") + ".json"
        d = self.dir / "sauvegardes-tts"
        d.mkdir(exist_ok=True)
        (d / name).write_bytes(data)
        meta = {"file": f"sauvegardes-tts/{name}", "time": stamp.isoformat(timespec="seconds"),
                "round": rnd, "turn": turn, "phase": st.get("phaseName"), "label": label,
                "auto": "AutoSave" in src.name, "sha1": digest}
        saves.append(meta)
        self.game["ttsSavesDir"] = str(src.parent)
        self._save_game()
        return meta

    def export_tts_saves(self) -> Path | None:
        """Copie chaque sauvegarde dans le dossier Saves de TTS, avec un nom lisible
        (« R2 Rouge 14h05 ») et le nom de la partie changé pour la reconnaître dans le menu."""
        saves = self.game.get("ttsSaves") or []
        tts_dir = self.game.get("ttsSavesDir")
        if not saves or not tts_dir:
            return None
        out = Path(tts_dir) / "Servo-Skull" / self.dir.name
        out.mkdir(parents=True, exist_ok=True)
        for m in saves:
            srcf = self.dir / m["file"]
            if not srcf.exists():
                continue
            t = m["time"][11:16].replace(":", "h") + m["time"][17:19]
            tag = (f"R{m['round']} {COLOR_FR.get(m['turn'], m['turn'])}" if m.get("round") else "avant partie")
            try:
                js = json.loads(srcf.read_text(encoding="utf-8-sig"))
                js["SaveName"] = f"Servo-Skull · {tag} · {t}"
                (out / f"{tag} {t}.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
            except (OSError, ValueError):
                shutil.copy2(srcf, out / f"{tag} {t}.json")
        return out

    def update_text(self, cid: str, intent: str | None = None, note: str | None = None):
        for m in self.game["captures"]:
            if m["id"] == cid:
                if intent is not None:
                    m["intent"] = intent
                if note is not None:
                    m["note"] = note
        self._save_game()

    def finish(self):
        self.game["finished"] = True
        self._save_game()

    def _tints(self, guids) -> dict:
        """Teinte (ColorDiffuse) des modèles, lue dans units/<guid>.json (écrit à la première capture de l'unité)."""
        out = {}
        for g in guids:
            f = self.dir / "units" / f"{g}.json"
            try:
                c = json.loads(f.read_text(encoding="utf-8")).get("ColorDiffuse")
                if isinstance(c, dict):
                    out[g] = (float(c.get("r", 0)), float(c.get("g", 0)), float(c.get("b", 0)))
            except (OSError, ValueError, AttributeError):
                pass
        return out

    def recompute_sides(self) -> dict:
        """Refait l'attribution des camps depuis les captures enregistrées (même logique qu'en direct)."""
        old = dict(self.game.get("sides") or {})
        sides, doubt = {}, set()
        for m in self.game["captures"]:
            if not m.get("data"):
                continue
            snap = self.load_snapshot(m["id"])
            if not snap:
                continue
            units = [o for o in snap.get("objects", []) if o.get("unit")]
            hw, hd = board_size(snap.get("deployMode"))
            sides = infer_sides(units, sides, hd / 2, self.red_positive_z, self._tints(u["guid"] for u in units), doubt)
        for g in doubt:  # pas de preuve claire : on garde l'attribution déjà enregistrée
            if g in old:
                sides[g] = old[g]
        self.game["sides"], self.game["sidesDoubt"] = sides, sorted(doubt)
        self._save_game()
        return {g: (old.get(g), s_) for g, s_ in sides.items() if old.get(g) != s_}

    def load_snapshot(self, cid: str) -> dict | None:
        p = self.dir / "captures" / f"{cid}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    @classmethod
    def open(cls, folder: Path) -> "Session":
        s = cls.__new__(cls)
        s.dir = Path(folder)
        s.game = json.loads((s.dir / "game.json").read_text(encoding="utf-8"))
        s.my_color = s.game["myColor"]
        s.mode = s.game["mode"]
        s.red_positive_z = s.game.get("redPositiveZ", True)
        return s
