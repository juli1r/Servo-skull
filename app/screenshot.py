"""Capture d'écran de la fenêtre Tabletop Simulator (Windows), JPEG compressé."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import mss
from PIL import Image


def _is_wayland(env=None) -> bool:
    env = os.environ if env is None else env
    return env.get("XDG_SESSION_TYPE") == "wayland" or "WAYLAND_DISPLAY" in env


def enable_dpi_awareness():
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _tts_client_rect():
    """Rectangle écran (x, y, w, h) de la zone de rendu de TTS, ou None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.strip() == "Tabletop Simulator":
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    if not found:
        return None
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        return None
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w < 100 or h < 100:
        return None
    return pt.x, pt.y, w, h


def make_screenshotter(max_width: int = 1920, quality: int = 85):
    def shoot(base: Path) -> Path | None:
        rect = _tts_client_rect()
        with mss.mss() as sct:
            if rect:
                x, y, w, h = rect
                region = {"left": x, "top": y, "width": w, "height": h}
            else:  # TTS introuvable : écran principal
                region = sct.monitors[1]
            raw = sct.grab(region)
        im = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
        out = Path(str(base) + ".jpg")
        im.save(out, "JPEG", quality=quality, optimize=True)
        return out

    return shoot
