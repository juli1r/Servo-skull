"""Mode live, facultatif : pousse l'état de la partie en cours vers Firestore pour que des
coéquipiers la suivent depuis un lien (site/live.html), sans rien envoyer tant que l'utilisateur n'a
pas cliqué sur « Partager en live » dans l'overlay. Même schéma de transport que upload.py (API REST
Firestore pure, sans SDK), mais en PATCH (écrase le même document à chaque capture) plutôt qu'en
POST (un document par envoi)."""
from __future__ import annotations

import base64
import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import recap
from core import Session

MAX_PAYLOAD = 500_000  # octets une fois en base64 (plan complet : plus volumineux qu'une contribution)
TTL_HOURS = 12  # durée de vie du document, au-delà de la plus longue partie plausible


def settings(cfg: dict) -> dict | None:
    fb = cfg.get("firebase") or {}
    return fb if fb.get("project_id") and fb.get("api_key") else None


def new_code() -> str:
    return uuid.uuid4().hex[:8]


def viewer_url(code: str) -> str:
    return f"https://servo-skull-74f0a.web.app/live.html?code={code}"


def push(session: Session, cfg: dict, code: str, timeout: float = 10) -> None:
    """Écrase l'état live de cette partie. Ne lève jamais : une erreur réseau ne doit pas
    interrompre la capture en cours (appelé en fire-and-forget depuis le controller)."""
    st = settings(cfg)
    if not st:
        return
    raw = gzip.compress(json.dumps(recap.collect(session), ensure_ascii=False).encode("utf-8"))
    payload = base64.b64encode(raw).decode("ascii")
    if len(payload) > MAX_PAYLOAD:
        return  # partie trop volumineuse pour le live : on abandonne silencieusement ce push
    expire_at = (datetime.now(timezone.utc) + timedelta(hours=TTL_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fields = {
        "schema": {"integerValue": "1"},
        "payload": {"stringValue": payload},
        "expireAt": {"timestampValue": expire_at},
    }
    base = st.get("endpoint") or "https://firestore.googleapis.com"
    url = (f"{base}/v1/projects/{urllib.parse.quote(st['project_id'])}/databases/(default)/documents/"
           f"live_games/{urllib.parse.quote(code)}"
           f"?key={urllib.parse.quote(st['api_key'])}"
           "&updateMask.fieldPaths=schema&updateMask.fieldPaths=payload&updateMask.fieldPaths=expireAt")
    req = urllib.request.Request(url, data=json.dumps({"fields": fields}).encode("utf-8"), method="PATCH",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=timeout).read()
    except (urllib.error.URLError, OSError):
        pass  # réseau coupé : on retentera à la prochaine capture
