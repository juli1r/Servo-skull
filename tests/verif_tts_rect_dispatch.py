"""Vérifie que _tts_client_rect() appelle la bonne fonction par OS, sans dépendre des libs
natives Mac/Linux (Quartz, Xlib) qui ne sont pas installées sur cette machine de dev Windows —
on monkeypatch les fonctions cibles plutôt que d'exécuter du vrai code Quartz/Xlib."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import screenshot

calls = []
screenshot._tts_rect_win32 = lambda: calls.append("win32") or None
screenshot._tts_rect_macos = lambda: calls.append("macos") or None
screenshot._tts_rect_x11 = lambda: calls.append("x11") or None

screenshot.sys.platform = "win32"
screenshot._tts_client_rect()
assert calls == ["win32"], calls

calls.clear()
screenshot.sys.platform = "darwin"
screenshot._tts_client_rect()
assert calls == ["macos"], calls

calls.clear()
screenshot.sys.platform = "linux"
screenshot._is_wayland = lambda: False
screenshot._tts_client_rect()
assert calls == ["x11"], calls

calls.clear()
screenshot.sys.platform = "linux"
screenshot._is_wayland = lambda: True
result = screenshot._tts_client_rect()
assert calls == [], "Wayland : aucune détection ne doit être tentée"
assert result is None

print("OK : _tts_client_rect() dispatch vers la bonne fonction par OS (win32/macos/x11/wayland)")
