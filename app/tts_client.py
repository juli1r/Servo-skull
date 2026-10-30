"""Client de l'API externe de Tabletop Simulator.

TTS écoute sur le port 39999 ; il renvoie ses messages en se connectant
au port 39998 (c'est nous qui écoutons sur ce port).

On n'utilise que :
  - envoi  messageID 3 : exécuter du Lua dans le contexte Global
  - retour messageID 5 : valeur renvoyée par le script
  - retour messageID 3 : erreur Lua
  - retour messageID 1 : une nouvelle partie a été chargée

Rien n'est installé dans la table : le Lua est exécuté à la demande
et ne laisse aucune trace dans la sauvegarde.

Robustesse :
  - écoute en IPv4 ET IPv6 (TTS peut se connecter via « localhost » = ::1)
  - lecture incrémentale : un message est traité dès qu'il est complet,
    même si TTS garde la connexion ouverte
  - journal du trafic dans servo-skull.log pour le diagnostic
"""
from __future__ import annotations

import itertools
import json
import queue
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

TTS_PORT = 39999
LISTEN_PORT = 39998


class TTSError(Exception):
    pass


class TTSUnavailable(TTSError):
    """TTS ne répond pas (pas lancé, ou on n'est pas l'hôte)."""


class TTSClient:
    def __init__(self, tts_port: int = TTS_PORT, listen_port: int = LISTEN_PORT,
                 log_path: Path | None = None):
        self.tts_port = tts_port
        self.listen_port = listen_port
        self._returns: "queue.Queue[dict]" = queue.Queue()
        self._lock = threading.Lock()  # une requête à la fois (pas d'ID de corrélation natif)
        self._rid = itertools.count(1)
        self._last_error: str | None = None
        self._servers: list[socket.socket] = []
        self._stop = threading.Event()
        self.on_game_loaded = None  # callback()
        self.on_game_saved = None   # callback(chemin_de_la_sauvegarde)
        self.on_custom = None       # callback(table envoyée par sendExternalMessage)
        self.log_path = log_path
        self.verbose = False
        self.stats = {"sent": 0, "send_fail": 0, "received": 0, "last_received": None,
                      "listening": [], "last_send_error": None}

    # ---------------------------------------------------------------- journal
    def log(self, msg: str):
        if not self.log_path:
            return
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
        except OSError:
            pass

    # ---------------------------------------------------------------- écoute
    def start(self):
        errors = []
        for fam, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            try:
                srv = socket.socket(fam, socket.SOCK_STREAM)
                if sys.platform == "win32":
                    # exclusif : si un autre programme écoute déjà ce port, on veut le savoir
                    srv.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
                else:
                    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind((host, self.listen_port))
                srv.listen(16)
                srv.settimeout(0.5)
            except OSError as e:
                errors.append(f"{host}: {e}")
                continue
            self._servers.append(srv)
            self.stats["listening"].append(host)
            threading.Thread(target=self._accept_loop, args=(srv,), daemon=True).start()
        self.log(f"écoute sur {self.stats['listening']} port {self.listen_port} ; erreurs : {errors}")
        if "127.0.0.1" not in self.stats["listening"]:
            raise TTSError(
                f"Le port {self.listen_port} est déjà utilisé. Un autre outil connecté à TTS "
                "(extension VSCode/Atom, autre instance de Servo-Skull) est sans doute ouvert : ferme-le."
            )

    def stop(self):
        self._stop.set()
        for s in self._servers:
            try:
                s.close()
            except OSError:
                pass

    def _accept_loop(self, srv):
        while not self._stop.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._read_conn, args=(conn, addr), daemon=True).start()

    @staticmethod
    def _decode(raw: bytes) -> str:
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) > 3 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00"):
            try:
                return raw.decode("utf-16")
            except UnicodeDecodeError:
                pass
        return raw.decode("utf-8", errors="replace")

    def _read_conn(self, conn: socket.socket, addr=None):
        raw = b""
        dec = json.JSONDecoder()
        handled = 0  # caractères déjà traités
        conn.settimeout(30)
        try:
            while True:
                b = conn.recv(65536)
                if not b:
                    break
                if not raw:
                    self.stats["connections"] = self.stats.get("connections", 0) + 1
                    if self.verbose:
                        self.log(f"<- données reçues ({addr}) ; début : {b[:120]!r}")
                raw += b
                text = self._decode(raw)
                # traite chaque message dès qu'il est complet (TTS peut garder la connexion ouverte)
                while True:
                    i = text.find("{", handled)
                    if i < 0:
                        break
                    try:
                        obj, end = dec.raw_decode(text, i)
                    except ValueError:
                        break
                    handled = end
                    if isinstance(obj, dict):
                        self._dispatch(obj)
        except OSError as e:
            self.log(f"<- lecture interrompue : {e}")
        finally:
            conn.close()
            if raw and handled == 0:
                self.log(f"<- DONNÉES NON COMPRISES ({len(raw)} octets) : {raw[:300]!r}")
                self.stats["unreadable"] = self.stats.get("unreadable", 0) + 1

    def _dispatch(self, msg: dict):
        mid = msg.get("messageID")
        if mid == -1:  # auto-test du diagnostic
            self.log("<- auto-test local reçu")
            return
        self.stats["received"] += 1
        self.stats["last_received"] = mid
        preview = json.dumps(msg, ensure_ascii=False)
        if self.verbose or mid != 5:
            self.log(f"<- id={mid} {preview[:300]}")
        if mid == 5:
            self._returns.put(msg)
        elif mid == 3:
            self._last_error = str(msg.get("error") or msg)
        elif mid == 4 and isinstance(msg.get("customMessage"), dict):
            cm = msg["customMessage"]
            if cm.get("servoSkullProbe"):
                self.probes = getattr(self, "probes", []) + [cm["servoSkullProbe"]]
            elif self.on_custom:
                self.on_custom(cm)
        elif mid == 6 and self.on_game_saved and msg.get("savePath"):
            threading.Thread(target=self.on_game_saved, args=(msg["savePath"],), daemon=True).start()
        elif mid == 1:
            self.last_scripts = msg.get("scriptStates")
            if self.on_game_loaded:
                try:
                    self.on_game_loaded()
                except Exception:
                    pass

    # ------------------------------------------------------------ exécution
    def run_lua(self, body: str, timeout: float = 5.0):
        """Exécute `body` (corps de fonction Lua qui fait `return <table>`)
        dans Global et renvoie la valeur décodée."""
        with self._lock:
            rid = f"r{next(self._rid)}"
            script = (
                "local __ok, __res = pcall(function()\n" + body + "\nend)\n"
                f'if __ok then return JSON.encode({{rid="{rid}", ok=true, data=__res}}) '
                f'else return JSON.encode({{rid="{rid}", ok=false, err=tostring(__res)}}) end'
            )
            while not self._returns.empty():
                self._returns.get_nowait()
            self._last_error = None
            self._send({"messageID": 3, "guid": "-1", "script": script, "returnID": next(self._rid)})
            deadline = time.monotonic() + timeout
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    if self._last_error:
                        raise TTSError(f"Erreur Lua : {self._last_error}")
                    raise TTSUnavailable("TTS n'a pas répondu (pas lancé, ou tu n'es pas l'hôte).")
                try:
                    msg = self._returns.get(timeout=min(left, 0.2))
                except queue.Empty:
                    continue
                val = msg.get("returnValue")
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except ValueError:
                        continue
                if not isinstance(val, dict) or val.get("rid") != rid:
                    continue
                if not val.get("ok"):
                    raise TTSError(f"Erreur Lua : {val.get('err')}")
                return val.get("data")

    def _send(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        last = None
        for host in ("127.0.0.1", "::1"):
            try:
                s = socket.create_connection((host, self.tts_port), timeout=2)
                try:
                    s.sendall(data)
                    # on signale la fin du message SANS fermer : certaines versions de TTS
                    # répondent sur cette même connexion plutôt que sur le port 39998
                    s.shutdown(socket.SHUT_WR)
                except OSError:
                    s.close()
                    raise
                threading.Thread(target=self._read_conn, args=(s, "même connexion"), daemon=True).start()
                self.stats["sent"] += 1
                if self.verbose or len(data) > 2000:
                    self.log(f"-> {host}:{self.tts_port} id={payload.get('messageID')} ({len(data)} octets)")
                return
            except OSError as e:
                last = last or e
        self.stats["send_fail"] += 1
        self.stats["last_send_error"] = str(last)
        self.log(f"-> ÉCHEC envoi : {last}")
        raise TTSUnavailable("Impossible de joindre TTS sur le port 39999. TTS est-il lancé ?") from last

    # ------------------------------------------------------------ diagnostic
    @staticmethod
    def port_owners(port: int) -> list[str]:
        """Windows : quels programmes écoutent sur ce port (netstat + tasklist)."""
        if sys.platform != "win32":
            return []
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            ns = ""
            for proto in ("TCP", "TCPv6"):
                r = subprocess.run(["netstat", "-ano", "-p", proto], capture_output=True,
                                   timeout=8, creationflags=flags).stdout
                ns += r.decode("cp850", errors="replace")
        except Exception:
            return []
        pids = set()
        for line in ns.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") and ("LISTEN" in parts[3].upper() or "COUTE" in parts[3].upper()):
                pids.add(parts[4])
        out = []
        for pid in sorted(pids):
            name = "?"
            try:
                tl = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                                    timeout=8, creationflags=flags).stdout.decode("cp850", errors="replace").strip()
                if tl.startswith('"'):
                    name = tl.split('","')[0].strip('"')
            except Exception:
                pass
            out.append(f"{name} (PID {pid})")
        return out

    def diagnose(self) -> list[tuple[bool, str]]:
        """Teste chaque maillon et renvoie [(ok, explication)]."""
        out = []
        owners = self.port_owners(self.listen_port)
        if owners:
            import os
            mine = [o for o in owners if f"PID {os.getpid()})" in o]
            others = [o for o in owners if o not in mine]
            out.append((not others, f"Programmes qui écoutent le port {self.listen_port} : {', '.join(owners)}"
                        + (" — un AUTRE programme intercepte les réponses de TTS : ferme-le."
                           if others else " (uniquement Servo-Skull : OK)")))
        tts = self.port_owners(self.tts_port)
        if tts:
            out.append((any("tabletop" in t.lower() for t in tts),
                        f"Programme qui écoute le port {self.tts_port} : {', '.join(tts)}"))
        # l'écoute est-elle joignable ? (pare-feu local, etc.)
        try:
            with socket.create_connection(("127.0.0.1", self.listen_port), timeout=2) as s:
                s.sendall(b'{"messageID": -1}')
            out.append((True, f"Port {self.listen_port} joignable en local."))
        except OSError as e:
            out.append((False, f"Port {self.listen_port} injoignable en local : {e}"))
        out.append(("127.0.0.1" in self.stats["listening"],
                    f"Écoute du port {self.listen_port} (retours de TTS) : "
                    + (", ".join(self.stats["listening"]) or "IMPOSSIBLE (port pris par un autre outil ?)")))
        try:
            self._send({"messageID": 3, "guid": "-1", "script": "return 1", "returnID": 0})
            out.append((True, f"Envoi vers TTS (port {self.tts_port}) : OK, TTS écoute bien."))
        except TTSUnavailable:
            out.append((False, f"Envoi vers TTS (port {self.tts_port}) : refusé ({self.stats['last_send_error']}). "
                               "TTS n'est pas lancé, ou aucune partie n'est chargée."))
            return out
        before = self.stats["received"]
        conns = self.stats.get("connections", 0)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 4 and self.stats["received"] == before:
            time.sleep(0.1)
        if self.stats["received"] == before:
            if self.stats.get("connections", 0) > conns and self.stats.get("unreadable", 0):
                out.append((False, "TTS se connecte bien en retour, mais ses données ne sont pas comprises "
                                   "(voir « DONNÉES NON COMPRISES » dans le journal) : envoie le journal à Claude."))
                return out
            out.append((False, "Réponse à l'exécution Lua : aucune en 4 s, TTS ne s'est même pas connecté en retour."))
            # 2e essai indépendant du Lua : demander la liste des scripts (messageID 0 -> réponse 1)
            try:
                self._send({"messageID": 0})
                t0 = time.monotonic()
                while time.monotonic() - t0 < 6 and self.stats["received"] == before \
                        and self.stats.get("connections", 0) == conns:
                    time.sleep(0.1)
            except TTSUnavailable:
                pass
            # 3e essai : un simple print -> TTS renvoie le texte (message 2) si le Lua s'exécute
            before2 = self.stats["received"]
            try:
                self._send({"messageID": 3, "guid": "-1", "script": 'print("servo-skull-test")', "returnID": 0})
                t0 = time.monotonic()
                while time.monotonic() - t0 < 4 and self.stats["received"] == before2:
                    time.sleep(0.1)
                out.append((self.stats["received"] > before2,
                            "Test print() : " + ("TTS exécute bien le Lua (sortie reçue) mais ne renvoie pas la valeur."
                                                 if self.stats["received"] > before2 else "aucune sortie, le Lua n'est pas exécuté.")))
            except TTSUnavailable:
                pass
            if self.stats["received"] > before:
                out.append((False, f"Par contre TTS répond à la demande de scripts (message {self.stats['last_received']}) : "
                                   "le retour fonctionne, c'est l'exécution du Lua qui échoue. "
                                   "Une partie avec la table LCT est-elle bien chargée ?"))
            elif self.stats.get("connections", 0) > conns:
                out.append((False, "TTS se connecte en retour mais ses données ne sont pas comprises : envoie le journal à Claude."))
            else:
                out.append((False, "TTS ne se connecte jamais en retour vers le port 39998, même pour la demande de scripts. "
                                   "Cause la plus probable : antivirus / pare-feu qui bloque Tabletop Simulator en sortie locale."))
            return out
        out.append((True, f"Réponse de TTS reçue (message {self.stats['last_received']})."))
        # le veilleur peut-il nous parler ? (sendExternalMessage direct et via minuteur)
        try:
            import lua_scripts as _L
            self.probes = []
            info = self.run_lua(_L.watch_probe()) or {}
            t0 = time.monotonic()
            while time.monotonic() - t0 < 3 and len(self.probes) < 2:
                time.sleep(0.1)
            out.append(("direct" in self.probes and "timer" in self.probes,
                        f"Messages de TTS vers l'outil : direct={'oui' if 'direct' in self.probes else 'NON'}, "
                        f"minuteur={'oui' if 'timer' in self.probes else 'NON'} ; veilleurs actifs : {info.get('timers')}"
                        + (f" ; dernière erreur : {info.get('err')}" if info.get("err") else "")))
        except TTSError as e:
            out.append((False, f"Test des messages : {e}"))
        try:
            v = self.run_lua("return {gv = Global.getVar('startMenu_GUID')}")
            if v and v.get("gv"):
                out.append((True, "Exécution Lua : OK, table LCT reconnue."))
            else:
                out.append((False, "Exécution Lua : OK, mais la table chargée n'est pas une table LCT/Hutber reconnue."))
        except TTSError as e:
            out.append((False, f"Exécution Lua : {e}"))
        return out
