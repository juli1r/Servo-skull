"""Vérifie que _is_wayland() lit les variables d'environnement standard de session Wayland.
La plupart des cas passent un dict explicite (pas besoin de l'OS réel) ; un cas vérifie aussi le
chemin par défaut (env=None -> vrai os.environ), en le monkeypatchant puis en le restaurant."""
import os
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

# WAYLAND_DISPLAY présent, XDG_SESSION_TYPE absent -> Wayland (repli)
env = {"WAYLAND_DISPLAY": "wayland-0"}
assert screenshot._is_wayland(env) is True

# XDG_SESSION_TYPE=x11 -> pas Wayland
env = {"XDG_SESSION_TYPE": "x11"}
assert screenshot._is_wayland(env) is False

# XWayland : WAYLAND_DISPLAY peut être présent sur une session X11 -> XDG_SESSION_TYPE fait
# autorité quand il est défini, WAYLAND_DISPLAY ne doit pas le contredire
env = {"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0"}
assert screenshot._is_wayland(env) is False

# chemin par défaut (env=None) : lit le vrai os.environ
_saved = dict(os.environ)
try:
    os.environ.clear()
    os.environ["XDG_SESSION_TYPE"] = "wayland"
    assert screenshot._is_wayland() is True
finally:
    os.environ.clear()
    os.environ.update(_saved)

print("OK : _is_wayland lit XDG_SESSION_TYPE / WAYLAND_DISPLAY correctement (y compris XWayland et env=None)")
