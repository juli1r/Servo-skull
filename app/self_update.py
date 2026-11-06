"""Auto-installation d'une mise à jour (clic sur la bannière de l'overlay).

N'agit JAMAIS en dehors d'un exe figé (PyInstaller) : en lancement depuis les sources
(lancer.bat), apply() refuse tout de suite — on ne touche jamais l'arbre de travail git.

Principe : Servo-Skull.exe (et les DLL de _internal/) sont verrouillés tant que le process
tourne, donc le remplacement ne peut pas se faire depuis l'app elle-même. apply() télécharge et
vérifie le zip, l'extrait dans un dossier de *staging* séparé, puis écrit et lance un petit script
.bat qui attend que l'exe se libère, copie (sans purger) le staging par-dessus le dossier
d'installation, relance l'exe, et se nettoie. config.json, parties/ (parties jouées) et
servo-skull.log vivent dans ce même dossier mais n'existent pas dans le zip source : un
robocopy /E (copie + écrase, jamais /MIR ni /PURGE) ne les touche donc jamais.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

CHUNK = 256 * 1024


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def apply(asset_url: str, asset_size: int | None, on_status: Callable[[str, dict], None]) -> bool:
    """Télécharge, vérifie, prépare et lance l'installation de la mise à jour. Retourne True si le
    script de relais a bien été lancé (l'appelant doit alors fermer proprement l'app), False en
    cas d'échec à n'importe quelle étape (rien d'installé n'est modifié)."""
    if not is_frozen():
        return False
    exe = Path(sys.executable)
    app_dir = exe.parent
    staging_root = Path(tempfile.mkdtemp(prefix="servo-skull-update-"))
    zip_path = staging_root / "update.zip"
    extract_dir = staging_root / "extracted"
    try:
        on_status("downloading", {"pct": 0})
        _download(asset_url, zip_path, asset_size, on_status)
        on_status("installing", {})
        with zipfile.ZipFile(zip_path) as zf:
            if zf.testzip() is not None:
                raise ValueError("zip corrompu")
            zf.extractall(extract_dir)
        # le zip contient un dossier top-level "Servo-Skull" (Compress-Archive -Path dist\Servo-Skull)
        src = extract_dir / "Servo-Skull"
        if not src.is_dir():
            cands = [p for p in extract_dir.iterdir() if p.is_dir()]
            if len(cands) != 1:
                raise ValueError("contenu du zip inattendu")
            src = cands[0]
        bat_path = staging_root / "appliquer_maj.bat"
        bat_path.write_text(_bat_script(src, app_dir, exe), encoding="utf-8")
        subprocess.Popen(
            ["cmd", "/c", str(bat_path)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        return True
    except Exception as e:
        on_status("error", {"error": str(e)})
        shutil.rmtree(staging_root, ignore_errors=True)
        return False


def _download(url: str, dest: Path, total: int | None, on_status: Callable[[str, dict], None]) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Servo-Skull-updater"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        done = 0
        while True:
            chunk = r.read(CHUNK)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                on_status("downloading", {"pct": min(99, round(done * 100 / total))})
    if dest.stat().st_size < 1024:
        raise ValueError("téléchargement incomplet")


def _bat_script(src: Path, app_dir: Path, exe: Path) -> str:
    # attend jusqu'à ~10 s que l'exe précédent se libère avant de copier par-dessus
    return f"""@echo off
setlocal
set TRIES=0
:wait
tasklist /fi "imagename eq {exe.name}" | find /i "{exe.name}" >nul
if %errorlevel%==0 (
  set /a TRIES+=1
  if %TRIES% lss 20 (
    timeout /t 1 /nobreak >nul
    goto wait
  )
)
robocopy "{src}" "{app_dir}" /E /NFL /NDL /NJH /NJS /R:3 /W:1
start "" "{exe}"
rmdir /s /q "{src.parent.parent}"
(goto) 2>nul & del "%~f0"
"""
