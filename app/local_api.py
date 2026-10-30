"""Petit serveur local (127.0.0.1) pour que le film.html puisse demander « rejouer ce moment dans TTS ».

Sécurité : n'écoute que sur la boucle locale, n'accepte que les pages ouvertes depuis un fichier (Origin « null »)
ou sans Origin, ne touche qu'aux dossiers de parties, et NE FAIT RIEN sans confirmation dans l'overlay."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 39997


def start(root_dir: Path, on_restore, log=print, port: int = PORT):
    """on_restore(folder: Path, capture_id: str) -> None : appelée dans un thread, doit demander confirmation."""
    root = Path(root_dir).resolve()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _origin_ok(self) -> bool:
            return self.headers.get("Origin") in (None, "", "null")

        def _send(self, code: int, body: dict | None = None):
            data = json.dumps(body or {}).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "null" if self.headers.get("Origin") == "null" else "*")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204 if self._origin_ok() else 403)

        def do_GET(self):
            if not self._origin_ok():
                return self._send(403, {"error": "origin"})
            if self.path.split("?")[0] == "/ping":
                return self._send(200, {"app": "servo-skull"})
            self._send(404)

        def do_POST(self):
            if not self._origin_ok():
                return self._send(403, {"error": "origin"})
            if self.path.split("?")[0] != "/restore":
                return self._send(404)
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 4096)
                req = json.loads(self.rfile.read(n).decode("utf-8"))
                folder = (root / str(req["folder"])).resolve()
                cid = str(req["id"])
                if folder.parent != root or not (folder / "game.json").exists():
                    return self._send(400, {"error": "partie inconnue"})
            except (ValueError, KeyError, OSError):
                return self._send(400, {"error": "requête invalide"})
            threading.Thread(target=on_restore, args=(folder, cid), daemon=True).start()
            self._send(202, {"status": "pending", "msg": "Confirme dans la fenêtre Servo-Skull."})

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    except OSError as e:
        log(f"Serveur local indisponible (port {port}) : {e}")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"Serveur local prêt sur 127.0.0.1:{port}")
    return srv
