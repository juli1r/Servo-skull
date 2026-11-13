"""Capture d'écran de la fenêtre Tabletop Simulator (Windows), JPEG compressé."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import mss
from PIL import Image


def _is_wayland(env=None) -> bool:
    """XDG_SESSION_TYPE fait autorité quand il est défini (il distingue un Wayland pur d'un X11
    avec XWayland, qui peut laisser WAYLAND_DISPLAY présent sans que la session soit Wayland).
    WAYLAND_DISPLAY ne sert de repli que si XDG_SESSION_TYPE est absent."""
    env = os.environ if env is None else env
    session_type = env.get("XDG_SESSION_TYPE")
    if session_type:
        return session_type == "wayland"
    return "WAYLAND_DISPLAY" in env


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


def _tts_rect_win32():
    """Rectangle écran (x, y, w, h) de la zone de rendu de TTS, ou None."""
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


def _tts_rect_macos():
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    for w in windows or []:
        name = w.get("kCGWindowOwnerName") or w.get("kCGWindowName") or ""
        if name.strip() != "Tabletop Simulator":
            continue
        bounds = w.get("kCGWindowBounds")
        if not bounds:
            return None
        x, y = int(bounds["X"]), int(bounds["Y"])
        w_, h_ = int(bounds["Width"]), int(bounds["Height"])
        if w_ < 100 or h_ < 100:
            return None
        return x, y, w_, h_
    return None


def _tts_rect_x11():
    return None  # implémenté au Task 5


def _tts_client_rect():
    """Rectangle écran (x, y, w, h) de la zone de rendu de TTS, ou None si indétectable."""
    try:
        if sys.platform == "win32":
            return _tts_rect_win32()
        if sys.platform == "darwin":
            return _tts_rect_macos()
        if sys.platform.startswith("linux"):
            if _is_wayland():
                return None
            return _tts_rect_x11()
    except Exception as e:
        print(f"[screenshot] détection fenêtre TTS échouée : {e!r}", file=sys.stderr)
    return None


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
