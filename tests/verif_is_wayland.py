"""Vérifie que _is_wayland() lit les variables d'environnement standard de session Wayland,
sans dépendre de l'OS réel de la machine qui lance le test (on monkeypatch os.environ)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import screenshot

# ni XDG_SESSION_TYPE ni WAYLAND_DISPLAY -> pas Wayland
env = {}
assert screenshot._is_wayland(env) is False

# XDG_SESSION_TYPE=wayland -> Wayland
env = {"XDG_SESSION_TYPE": "wayland"}
assert screenshot._is_wayland(env) is True

# WAYLAND_DISPLAY présent (même sans XDG_SESSION_TYPE) -> Wayland
env = {"WAYLAND_DISPLAY": "wayland-0"}
assert screenshot._is_wayland(env) is True

# XDG_SESSION_TYPE=x11 -> pas Wayland
env = {"XDG_SESSION_TYPE": "x11"}
assert screenshot._is_wayland(env) is False

print("OK : _is_wayland lit XDG_SESSION_TYPE / WAYLAND_DISPLAY correctement")
