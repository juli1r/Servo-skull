"""Vérification facultative d'une nouvelle version sur GitHub (lecture seule, aucun envoi).

Compare VERSION (core.py, format AA.MM.JJ) à celle du fichier core.py sur la branche main du
dépôt : pas d'API GitHub ni de Release à maintenir, juste le fichier source le plus récent.
Ne télécharge et ne remplace rien automatiquement : on prévient l'hôte, qui décide."""
from __future__ import annotations

import re
import urllib.error
import urllib.request

REPO = "juli1r/Servo-skull"
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/main/app/core.py"
REPO_URL = f"https://github.com/{REPO}"


def check(current: str, timeout: float = 5) -> dict | None:
    """Retourne {"version": ..., "url": ...} si une version plus récente est publiée, sinon None.
    Ne lève jamais (pas de réseau, dépôt inaccessible...) : juste None."""
    try:
        with urllib.request.urlopen(RAW_URL, timeout=timeout) as r:
            text = r.read(4096).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    if not m:
        return None
    remote = m.group(1)
    if remote > current:
        return {"version": remote, "url": REPO_URL}
    return None
