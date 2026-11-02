"""Servo-Skull — point d'entrée."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from screenshot import enable_dpi_awareness, make_screenshotter  # noqa: E402

DEFAULTS = {
    "replays_dir": "",  # vide = dossier « parties » à côté du programme
    "hotkey": "f8",
    "envoi": "",  # "" = pas encore demandé, "oui" / "non" : envoi des fichiers anonymes (accord séparé du fichier local)
    "firebase": {  # clé web Firebase : publique par nature (c'est l'adresse du dépôt ; les règles Firestore font la sécurité)
        "project_id": "servo-skull-74f0a",
        "api_key": "AIzaSyDR20oqMz2q6qHS_e109pliJnYQhP6NaeU",
        "collection": "servoskull_contributions",
    },
    "contribution": "",  # "" = pas encore demandé, "oui" / "non" : fichier de contribution anonyme en fin de partie
    "watch_enabled": True,
    "watch_interval_s": 0.5,         # le veilleur, dans TTS, regarde tour/phase à ce rythme (sans réseau)
    "watchdog_s": 10.0,
    "watch_timeout_s": 90.0,
    "stale_minutes": 8,               # alerte "phase bloquée" seulement après ce délai sans changement de phase
    "stale_drops": 25,                # ...et seulement si au moins ce nombre de figurines ont été posées entre-temps
    "debug_dump": False,
    "verbose_log": False,
    "auto_capture_after_movement": True,
    "auto_capture": "phases",        # capture auto (légère, sans photo) à chaque fin de phase ; "movement" ou "off"
    "alert_scope": "all",            # "all" = tous les tours, "mine" = seulement les miens
    "fixed_camera": True,
    "photo_on_capture": False,
    "auto_gif": True,                # GIF du plan généré à la fin de chaque partie
    "gif_frame_ms": 5000,            # durée d'affichage de chaque image du GIF
    "gif_last_ms": 8000,       # capture d'écran à chaque F8 (sinon : plan seul, la caméra ne bouge pas)
    "camera_distance": 70,           # à ajuster une fois pour que toute la table rentre
    "camera_pitch": 90,
    "camera_yaw_offset": 0,
    "camera_target_x": 0,
    "camera_target_z": 0,
    "camera_settle_s": 0.9,
    "red_positive_z": True,          # côté Rouge de la table LCT (z positif)
    "overlay_alpha": 1.0,            # < 1 = fenêtre transparente, mais coûteux pour le jeu en dessous
    "last_color": "Red",
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


CFG_PATH = app_dir() / "config.json"


def load_cfg() -> dict:
    cfg = dict(DEFAULTS)
    if CFG_PATH.exists():
        try:
            cfg.update(json.loads(CFG_PATH.read_text(encoding="utf-8")))
        except ValueError:
            pass
    else:
        save_cfg(cfg)
    if cfg.get("overlay_alpha") == 0.94:  # ancienne valeur : la transparence faisait ramer TTS
        cfg["overlay_alpha"] = 1.0
        save_cfg(cfg)
    if cfg.get("poll_interval_s") == 2.0:  # ancienne valeur par défaut, trop fréquente
        cfg["poll_interval_s"] = 3.0
        save_cfg(cfg)
    if not cfg.get("replays_dir"):
        cfg["replays_dir"] = str(app_dir() / "parties")
    Path(cfg["replays_dir"]).mkdir(parents=True, exist_ok=True)
    return cfg


def save_cfg(cfg: dict):
    try:
        CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _ensure_shortcuts():
    """Une seule fois : raccourcis Bureau + menu Démarrer avec l'icône et l'identifiant d'application
    de l'overlay (sinon Windows affiche une icône générique dans la barre des tâches)."""
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    import os
    import subprocess
    start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Servo-Skull.lnk"
    if start_menu.exists():
        return
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(app_dir() / "app" / "raccourcis.ps1"), "-Root", str(app_dir())],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        pass


def main():
    enable_dpi_awareness()
    from controller import Controller
    from overlay import Overlay
    from tts_client import TTSClient, TTSError

    cfg = load_cfg()
    client = TTSClient(log_path=app_dir() / "servo-skull.log")
    client.verbose = bool(cfg.get("verbose_log"))
    from core import VERSION, find_unfinished_session
    client.log(f"Servo-Skull v{VERSION} démarré ({'exe' if getattr(sys, 'frozen', False) else 'lancer.bat'})")
    unfinished = find_unfinished_session(Path(cfg["replays_dir"]))
    start_error = None
    try:
        client.start()
    except TTSError as e:
        start_error = str(e)

    _ensure_shortcuts()
    ui = Overlay(cfg, save_cfg, lambda ui: Controller(cfg, client, make_screenshotter(), ui))
    if start_error:
        ui.emit("error", start_error)
    if unfinished:
        ui.emit("unfinished", unfinished)

    def _check_update():
        import update_check
        info = update_check.check(VERSION)
        if info:
            ui.emit("update", info)
    threading.Thread(target=_check_update, daemon=True).start()

    try:
        import local_api
        local_api.start(Path(cfg["replays_dir"]), ui.request_restore, log=client.log)
    except Exception as e:  # ne doit jamais empêcher de jouer
        client.log(f"Serveur local non démarré : {e}")
    ui.run()
    client.stop()


if __name__ == "__main__":
    main()
