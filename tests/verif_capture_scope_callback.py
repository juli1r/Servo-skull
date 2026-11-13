"""Vérifie que make_screenshotter() appelle on_capture_scope(found) à chaque capture, avec
found=True si _tts_client_rect() a trouvé la fenêtre TTS, False sinon — et qu'un callback qui
lève une exception ne casse pas la capture. Isolé du vrai écran : on monkeypatche
_tts_client_rect ET mss.mss (sinon ce test échouerait sur une machine headless/CI sans
affichage, ce que ce dépôt cible justement avec le portage Linux)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import screenshot


class _FakeGrab:
    size = (4, 4)
    bgra = b"\x00\x00\x00\xff" * 16


class _FakeSct:
    monitors = [None, {"left": 0, "top": 0, "width": 4, "height": 4}]

    def grab(self, region):
        return _FakeGrab()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


screenshot.mss.mss = lambda: _FakeSct()

tmp = Path(tempfile.mkdtemp()) / "shot"

calls = []
shoot = screenshot.make_screenshotter(on_capture_scope=lambda found: calls.append(found))

screenshot._tts_client_rect = lambda: (0, 0, 800, 600)
shoot(tmp)
assert calls == [True], calls

calls.clear()
screenshot._tts_client_rect = lambda: None
shoot(tmp)
assert calls == [False], calls

# un callback qui lève ne doit jamais casser la capture (juste être journalisé sur stderr)
screenshot._tts_client_rect = lambda: (0, 0, 800, 600)
shoot_raising = screenshot.make_screenshotter(on_capture_scope=lambda found: (_ for _ in ()).throw(RuntimeError("boom")))
out = shoot_raising(tmp)
assert out is not None, "la capture doit réussir même si on_capture_scope lève"

print("OK : make_screenshotter() rapporte via on_capture_scope sans jamais casser la capture")
