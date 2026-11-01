"""Teste l'envoi contre un faux Firestore local : format de la requête, doublons (409), file d'attente, consentement."""
import base64, gzip, json, sys, threading, tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, "app")
from core import Session
import contribution, upload

seen, store = [], {}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path); q = parse_qs(u.query)
        gid = q["documentId"][0]
        seen.append((u.path, gid, q["key"][0]))
        if gid in store:
            self.send_response(409); self.end_headers(); self.wfile.write(b"{}"); return
        store[gid] = body["fields"]
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
cfg = {"firebase": {"project_id": "demo", "api_key": "KEY", "collection": "servoskull_contributions",
                    "endpoint": f"http://127.0.0.1:{srv.server_port}"}}

root = Path(tempfile.mkdtemp())
src = Path("parties/2026-10-29_09h58_RaiJin-vs-Mankdebol")
s = Session.open(src)
import shutil
d = root / "partie1"; d.mkdir()
for n in ("game.json",):
    shutil.copy(src / n, d / n)
shutil.copytree(src / "captures", d / "captures"); shutil.copytree(src / "units", d / "units")
s2 = Session.open(d)
gz = contribution.export(s2)
assert upload.settings({}) is None and upload.settings(cfg)
assert upload.pending(root) == [], "rien n'est envoyé sans accord (pas de marqueur)"
assert upload.send_pending(root, cfg) == 0 and not store
upload.queue(d)
assert upload.pending(root) == [d]
assert upload.send_pending(root, cfg) == 1
assert upload.pending(root) == []
(gid, f), = store.items()
assert seen[0][0] == "/v1/projects/demo/databases/(default)/documents/servoskull_contributions" and seen[0][2] == "KEY"
assert set(f) == {"schema", "app", "month", "mode", "layout", "nsquads", "ncaps", "payload"}, set(f)
back = json.loads(gzip.decompress(base64.b64decode(f["payload"]["stringValue"])))
assert back["id"] == gid and "players" not in back
blob = json.dumps(f).lower()
for w in ("raijin", "mankdebol"):
    assert w not in blob
print("payload Ko:", len(f["payload"]["stringValue"]) // 1024, "| champs:", sorted(f))
# renvoi de la même partie : 409 = « exists », pas d'erreur ni de doublon
assert upload.send(gz, cfg) == "exists" and len(store) == 1
# réseau coupé : l'envoi échoue sans casser, la partie reste en attente
(d / upload.SENT).unlink(); bad = {"firebase": dict(cfg["firebase"], endpoint="http://127.0.0.1:9")}
logs = []
assert upload.send_pending(root, bad, logs.append) == 0 and upload.pending(root) == [d] and logs
print("OK : envoi, doublon, file d'attente, hors ligne")
