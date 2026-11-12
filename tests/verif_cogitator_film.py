"""Vérifie que cogitator_export.export_film écrit un film gzippé sans ttsSaves/folder/screenshot,
et qu'il n'écrit rien si la partie n'a aucune capture."""
import gzip, json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, "app")
from core import Session
import cogitator_export

root = Path(tempfile.mkdtemp())
src = Path("parties/2026-10-29_09h58_RaiJin-vs-Mankdebol")
d = root / "partie1"; d.mkdir()
shutil.copy(src / "game.json", d / "game.json")
shutil.copytree(src / "captures", d / "captures")
shutil.copytree(src / "units", d / "units")
s = Session.open(d)

path = cogitator_export.export_film(s)
assert path == d / "film-cogitator.json.gz", path
assert path.exists()

data = json.loads(gzip.decompress(path.read_bytes()))
assert "ttsSaves" not in data, "ttsSaves (références locales) ne doit pas être exporté"
assert "folder" not in data, "folder (nom de dossier local) ne doit pas être exporté"
assert data["captures"], "le film doit contenir des captures"
assert all("screenshot" not in c for c in data["captures"]), "aucune capture ne doit garder 'screenshot'"
assert data["players"], "les noms de joueurs restent en clair (pas d'anonymisation)"
assert "squadNames" in data and "mission" in data

# partie sans aucune capture : rien n'est écrit
empty_root = Path(tempfile.mkdtemp())
s2 = Session(empty_root, "Red", "host", {"Red": "Alice", "Blue": "Bob"})
assert cogitator_export.export_film(s2) is None
assert not (s2.dir / "film-cogitator.json.gz").exists()

print("OK : film-cogitator.json.gz écrit sans ttsSaves/folder/screenshot, rien si pas de capture")
