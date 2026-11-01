"""Essai réel de l'envoi : prend ta dernière partie enregistrée, crée son fichier anonyme et l'envoie sur Firestore.
Affiche clairement si ça a marché. À lancer une fois après avoir publié les règles (essai-envoi.bat).
La partie envoyée apparaît dans la console Firebase > Firestore > servoskull_contributions ; supprime-la ensuite à la main
si tu ne veux pas la garder comme donnée réelle."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "app"))
import contribution, upload  # noqa: E402
from core import Session  # noqa: E402
from main import DEFAULTS  # noqa: E402

cfg = dict(DEFAULTS)
parties = [d for d in sorted((root / "parties").iterdir()) if (d / "game.json").exists() and (d / "captures").exists()]
for d in reversed(parties):
    s = Session.open(d)
    if s.game.get("captures"):
        break
else:
    sys.exit("Aucune partie enregistrée à envoyer.")
gz = contribution.export(s)
print("Partie :", d.name, "| fichier anonyme :", gz.stat().st_size // 1024 or 1, "Ko")
try:
    r = upload.send(gz, cfg)
except Exception as e:
    body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")[:400]
    sys.exit(f"ECHEC : {type(e).__name__}: {e}\n{body}\n-> Vérifie que les règles Firestore sont publiées et que la base existe.")
print("OK : envoyé" if r == "ok" else "OK : cette partie était déjà reçue (aucun doublon créé)")
