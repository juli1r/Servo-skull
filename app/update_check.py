"""Vérification facultative d'une nouvelle version sur GitHub (lecture seule, aucun envoi).

Compare VERSION (core.py, format AA.MM.JJ) au tag de la dernière Release GitHub publiée (pas au
code brut de la branche main : seule une Release a un zip réellement téléchargeable, c'est elle
que la CI (.github/workflows/release.yml) publie à chaque bump de VERSION). Ne télécharge et ne
remplace rien ici : juste de quoi informer l'appelant (self_update.apply fait le reste)."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

REPO = "juli1r/Servo-skull"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"

_PLATFORM_SUFFIX = {"win32": "windows", "darwin": "macos", "linux": "linux"}


def _asset_name_re(platform: str) -> re.Pattern:
    suffix = _PLATFORM_SUFFIX.get(platform, _PLATFORM_SUFFIX["win32"])
    return re.compile(rf"^Servo-Skull-.*-{suffix}\.zip$")


def check(current: str, timeout: float = 5) -> dict | None:
    """Retourne {"version", "url", "asset_url", "asset_size"} si une Release plus récente avec un
    zip Windows exploitable est publiée, sinon None. Ne lève jamais (pas de réseau, dépôt
    inaccessible, réponse inattendue...) : juste None."""
    try:
        req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    tag = data.get("tag_name") or ""
    remote = tag[1:] if tag.startswith("v") else tag
    if not remote or remote <= current:
        return None
    asset_re = _asset_name_re(sys.platform)
    asset = next((a for a in data.get("assets") or [] if asset_re.match(a.get("name") or "")), None)
    if not asset:
        return None
    return {"version": remote, "url": data.get("html_url") or f"https://github.com/{REPO}/releases",
            "asset_url": asset.get("browser_download_url"), "asset_size": asset.get("size")}
