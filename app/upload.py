"""Envoi facultatif d'une contribution anonyme vers Firestore (API REST publique, sans bibliothèque).

Rien ne part sans accord : ce module n'est appelé que si l'utilisateur a accepté l'envoi (réglage « envoi »).
Le document porte l'identifiant aléatoire de la partie : renvoyer la même partie ne crée jamais de doublon, et
c'est cet identifiant qui permet de supprimer une partie à la demande."""
from __future__ import annotations

import base64
import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GZ, QUEUED, SENT = "contribution.json.gz", "contribution.queued", "contribution.sent"
MAX_PAYLOAD = 200_000  # octets une fois en base64 (les parties réelles : 2 à 10 Ko)


def settings(cfg: dict) -> dict | None:
    fb = cfg.get("firebase") or {}
    return fb if fb.get("project_id") and fb.get("api_key") else None


def _fields(path: Path) -> tuple[str, dict]:
    raw = path.read_bytes()
    data = json.loads(gzip.decompress(raw))
    payload = base64.b64encode(raw).decode("ascii")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("contribution trop volumineuse")
    f = {
        "schema": {"integerValue": str(int(data["schema"]))},
        "app": {"stringValue": str(data.get("app", ""))},
        "month": {"stringValue": str(data.get("month", ""))},
        "mode": {"stringValue": str(data.get("mode") or "")},
        "layout": {"stringValue": str(data.get("layout") or "")},
        "nsquads": {"integerValue": str(len(data.get("squads") or []))},
        "ncaps": {"integerValue": str(len(data.get("caps") or []))},
        "payload": {"stringValue": payload},  # le fichier .json.gz tel quel : Firestore refuse les tableaux imbriqués
    }
    return data["id"], f


def send(path: Path, cfg: dict, timeout: float = 15) -> str:
    """Retourne « ok » ou « exists » ; lève une exception si l'envoi échoue."""
    st = settings(cfg)
    if not st:
        raise RuntimeError("envoi non configuré")
    gid, fields = _fields(Path(path))
    base = st.get("endpoint") or "https://firestore.googleapis.com"
    col = st.get("collection") or "servoskull_contributions"
    url = (f"{base}/v1/projects/{urllib.parse.quote(st['project_id'])}/databases/(default)/documents/"
           f"{urllib.parse.quote(col)}?documentId={gid}&key={urllib.parse.quote(st['api_key'])}")
    req = urllib.request.Request(url, data=json.dumps({"fields": fields}).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=timeout).read()
        return "ok"
    except urllib.error.HTTPError as e:
        if e.code == 409:  # déjà reçue
            return "exists"
        raise


def queue(folder: Path) -> None:
    """Marque la partie comme à envoyer (accord donné) ; permet de réessayer plus tard si le réseau manque."""
    (Path(folder) / QUEUED).write_text("1", encoding="utf-8")


def pending(root: Path) -> list[Path]:
    out = []
    for d in sorted(Path(root).iterdir()):
        if d.is_dir() and (d / QUEUED).exists() and not (d / SENT).exists() and (d / GZ).exists():
            out.append(d)
    return out


def send_pending(root: Path, cfg: dict, log=None) -> int:
    n = 0
    if not settings(cfg):
        return 0
    for d in pending(root):
        try:
            send(d / GZ, cfg)
            (d / SENT).write_text("1", encoding="utf-8")
            n += 1
        except Exception as e:  # réseau coupé, règles refusées… : on réessaiera après la prochaine partie
            if log:
                log(f"Envoi de la contribution {d.name} impossible : {type(e).__name__}: {e}")
    return n
