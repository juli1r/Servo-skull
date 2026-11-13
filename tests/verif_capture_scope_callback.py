"""Vérifie que make_screenshotter() appelle on_capture_scope(found) à chaque capture, avec
found=True si _tts_client_rect() a trouvé la fenêtre TTS, False sinon — sans dépendre d'un vrai
écran (on monkeypatche _tts_client_rect)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import screenshot

calls = []
shoot = screenshot.make_screenshotter(on_capture_scope=lambda found: calls.append(found))

tmp = Path(tempfile.mkdtemp()) / "shot"

screenshot._tts_client_rect = lambda: (0, 0, 800, 600)
shoot(tmp)
assert calls == [True], calls

calls.clear()
screenshot._tts_client_rect = lambda: None
shoot(tmp)
assert calls == [False], calls

print("OK : make_screenshotter() rapporte via on_capture_scope si la fenêtre TTS a été trouvée")
