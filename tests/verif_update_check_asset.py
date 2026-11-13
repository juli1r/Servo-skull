"""Vérifie que update_check choisit l'asset de la bonne plateforme (windows/macos/linux) parmi
les assets d'une Release GitHub simulée."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import update_check

assets = [
    {"name": "Servo-Skull-26.11.13-windows.zip", "browser_download_url": "u-win", "size": 1},
    {"name": "Servo-Skull-26.11.13-macos.zip", "browser_download_url": "u-mac", "size": 2},
    {"name": "Servo-Skull-26.11.13-linux.zip", "browser_download_url": "u-linux", "size": 3},
]

assert update_check._asset_name_re("win32").match("Servo-Skull-26.11.13-windows.zip")
assert not update_check._asset_name_re("win32").match("Servo-Skull-26.11.13-macos.zip")
assert update_check._asset_name_re("darwin").match("Servo-Skull-26.11.13-macos.zip")
assert update_check._asset_name_re("linux").match("Servo-Skull-26.11.13-linux.zip")

print("OK : update_check sélectionne l'asset de la bonne plateforme")
