"""Orchestration sans interface : lecture périodique, captures, alertes, récap.
L'overlay (overlay.py) ne fait que l'afficher et lui transmettre les clics."""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import recap
import contribution
import cogitator_export
import live_share
import toast
import upload
import lua_scripts as L
from core import Session, TurnTracker, normalize_state, turn_label, is_final_phase_end
from tts_client import TTSClient, TTSError, TTSUnavailable


def _toast_text(meta: dict) -> str:
    key = tuple(meta["turnKey"]) if meta.get("turnKey") else None
    label = turn_label(key) if key else "Capture"
    vp = meta.get("vp") or {}
    if vp.get("Red") is not None or vp.get("Blue") is not None:
        label += f" · {vp.get('Red', '–')}-{vp.get('Blue', '–')}"
    return label


class Controller:
    def __init__(self, cfg: dict, client: TTSClient, screenshotter=None, ui_hooks=None):
        """screenshotter(path_sans_extension) -> Path | None
        ui_hooks : objet optionnel avec hide()/show() (masquer l'overlay pendant la photo)
                   et emit(event, payload) (mise à jour de l'interface)."""
        self.cfg = cfg
        self.client = client
        self.shoot = screenshotter
        self.ui = ui_hooks
        self.session: Session | None = None
        self.tracker: TurnTracker | None = None
        self.state: dict | None = None
        self.mode = "unknown"  # host / guest
        self.live_code: str | None = None  # non None = partage live actif pour cette partie (voir start_live)
        self._last_snap = None
        self.pending_alert = None
        self._lock = threading.Lock()  # une capture à la fois
        self._stop = threading.Event()
        self._thread = None
        client.on_game_saved = self.on_game_saved
        client.on_custom = self._on_custom
        self._events: "queue.Queue[dict]" = queue.Queue()
        self._last_beat = 0.0
        self._beats = 0
        threading.Thread(target=self._event_worker, daemon=True).start()

    # ----------------------------------------------------------------- utils
    def emit(self, ev, payload=None):
        if self.ui:
            try:
                self.ui.emit(ev, payload)
            except Exception:
                pass

    def start_live(self) -> str | None:
        """Active le partage live pour la partie en cours (bouton overlay) ; retourne le lien à
        copier, ou None si Firestore n'est pas configuré. Idempotent : un second clic réutilise le
        même code plutôt que d'en générer un nouveau."""
        if not live_share.settings(self.cfg):
            return None
        if not self.live_code:
            self.live_code = live_share.new_code()
            if self.session:
                threading.Thread(target=live_share.push, args=(self.session, self.cfg, self.live_code),
                                 daemon=True).start()
        return live_share.viewer_url(self.live_code)

    def probe(self) -> str:
        """Détermine le mode : hôte (TTS répond au Lua) ou invité."""
        try:
            self.state = normalize_state(self.client.run_lua(L.poll_install(), timeout=5))
            self.mode = "host"
        except (TTSUnavailable, TTSError):
            self.state = None
            self.mode = "guest"
        return self.mode

    # --------------------------------------------------------------- session
    def start_session(self, my_color: str):
        mode = self.probe()
        players = (self.state or {}).get("players") or {}
        self._last_snap = None
        self.live_code = None  # le partage live ne survit pas d'une partie à l'autre, même reprise
        resumed = self._find_resumable(my_color, mode, players)
        self.tracker = TurnTracker(my_color, self.cfg.get("alert_scope", "all"))
        if resumed:
            folder, seq, color = resumed
            self.session = Session.open(folder)
            self.session.game["finished"] = False
            for c, n in players.items():
                self.session.game["players"].setdefault(c, n)
            self.tracker.restore(seq, color)
            self.emit("info", f"Partie en cours reprise : {folder.name}")
        else:
            self.session = Session(Path(self.cfg["replays_dir"]), my_color, mode, players,
                                   red_positive_z=self.cfg.get("red_positive_z", True))
        if self.state:
            self.tracker.update(self.state)
            self._apply_rounds(self.state)
            self._save_seq()
        self.pending_alert = None
        recap.build(self.session)
        self.emit("session", {"mode": mode, "dir": str(self.session.dir)})
        self.emit("state", self.state)
        if mode == "host" and self.cfg.get("debug_dump"):
            threading.Thread(target=self.dump_table, daemon=True).start()
        self._start_polling()  # en invité : retente la connexion toutes les quelques secondes
        return self.session

    def _apply_rounds(self, st: dict):
        """Le round affiché et enregistré est celui compté par l'outil (le compteur du mod se décale)."""
        k = self.tracker.cur_key if self.tracker else None
        if k and st and st.get("inGame"):
            st["modRound"] = st.get("round")
            st["round"] = k[0]
        self._save_seq()

    def _save_seq(self):
        t, s = self.tracker, self.session
        if not (t and s and t.seq and t.cur_color):
            return
        cur = {"seq": t.seq, "color": t.cur_color}
        if s.game.get("turnSeq") != cur:
            s.game["turnSeq"] = cur
            s._save_game()

    def _find_resumable(self, my_color: str, mode: str, players: dict):
        """Relance de l'outil EN COURS de partie : on reprend la session de cette partie au lieu d'en ouvrir une
        nouvelle (sinon l'avant-partie et les premiers tours restent dans l'ancien dossier)."""
        st = self.state
        if mode != "host" or not st or not st.get("inGame") or not self.cfg.get("resume_session", True):
            return None
        import json as _j
        import time as _t
        root = Path(self.cfg["replays_dir"])
        try:
            folders = sorted([d for d in root.iterdir() if (d / "game.json").exists()], reverse=True)[:4]
        except OSError:
            return None
        for d in folders:
            try:
                g = _j.loads((d / "game.json").read_text(encoding="utf-8"))
                age = _t.time() - (d / "game.json").stat().st_mtime
            except (OSError, ValueError):
                continue
            if g.get("mode") != "host" or g.get("myColor") != my_color or age > 3 * 3600:
                continue
            gp = g.get("players") or {}
            if any(gp.get(c) not in (None, n) for c, n in players.items()):
                continue                          # autres joueurs : autre partie
            caps = [c for c in (g.get("captures") or []) if c.get("turnKey")]
            seq = (g.get("turnSeq") or {}).get("seq")
            color = (g.get("turnSeq") or {}).get("color")
            if not caps and not seq:
                continue
            if not seq:                           # ancienne session sans numéro de tour : on le déduit des captures
                first = caps[0]["turnKey"][1]
                lr, lc = caps[-1]["turnKey"]
                seq, color = 2 * (lr - 1) + (1 if lc == first else 2), lc
            if (g.get("turnSeq") or {}).get("seq", seq) > 2 * (int(st.get("round") or 1)) + 1:
                continue                          # la partie du dossier est plus avancée que celle de TTS : autre partie
            if st.get("turn") and color and st["turn"] != color:
                seq, color = seq + 1, st["turn"]
            return d, seq, color
        return None

    def dump_table(self):
        """Écrit l'inventaire de la table et les scripts dans debug/ (pour adapter l'outil au mod)."""
        import json as _j
        d = Path(self.cfg.get("debug_dir") or (Path(self.cfg["replays_dir"]).parent / "debug"))
        d.mkdir(parents=True, exist_ok=True)
        try:
            objs = self.client.run_lua(L.inspect(), timeout=20)
            (d / "objets.json").write_text(_j.dumps(objs, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            (d / "erreur.txt").write_text(str(e), encoding="utf-8")
        try:
            self.client.last_scripts = None
            self.client._send({"messageID": 0})
            for _ in range(80):
                if self.client.last_scripts:
                    break
                time.sleep(0.1)
            if self.client.last_scripts:
                (d / "scripts.json").write_text(_j.dumps(self.client.last_scripts, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------- sauvegardes TTS par tour
    def on_game_saved(self, save_path: str):
        """TTS vient d'écrire une sauvegarde (auto ou manuelle) : on en garde une copie
        rangée au tour en cours, avant qu'elle soit écrasée par la suivante."""
        s = self.session
        if not s:
            return
        try:
            meta = s.keep_tts_save(Path(save_path), self.state)
        except Exception as e:
            self.emit("error", f"Copie de la sauvegarde TTS impossible : {e}")
            return
        if meta:
            recap.build(s)
            self.emit("saved", meta)

    def export_saves_to_tts(self, session: Session) -> Path | None:
        """Copie les sauvegardes de la partie dans Saves\\Servo-Skull\\<partie> pour les charger depuis TTS."""
        return session.export_tts_saves()

    def stop_watch(self):
        """À la fermeture : arrête le veilleur dans TTS (sinon il continuerait d'essayer de nous joindre)."""
        self._stop.set()
        try:
            self.client.run_lua(L.watch_stop(), timeout=1)
        except Exception:
            pass

    def finish_session(self) -> Path | None:
        self._stop.set()
        try:
            self.client.run_lua(L.watch_stop(), timeout=1)
        except Exception:
            pass
        if not self.session:
            return None
        self.session.finish()
        out = recap.build(self.session)
        try:
            cogitator_export.export(self.session)
        except Exception as e:
            try:
                (self.session.dir / "cogitator-export-erreur.txt").write_text(str(e), encoding="utf-8")
            except OSError:
                pass
        sess = self.session
        self.session = None

        def make_gif():  # fil non « daemon » : le programme attend la fin du GIF avant de se fermer
            try:
                import gif_render
                gif_render.render(recap.collect(sess), sess.dir / "evolution-du-plan.gif",
                                  frame_ms=int(self.cfg.get("gif_frame_ms", 5000)),
                                  last_ms=int(self.cfg.get("gif_last_ms", 8000)))
            except Exception as e:
                try:
                    (sess.dir / "gif-erreur.txt").write_text(str(e), encoding="utf-8")
                except OSError:
                    pass
        if self.cfg.get("auto_gif", True):
            threading.Thread(target=make_gif, daemon=False).start()

        def make_contribution():  # fichier local seulement si accepté ; envoi seulement si accepté à part
            try:
                contribution.export(sess)
            except Exception as e:
                try:
                    (sess.dir / "contribution-erreur.txt").write_text(str(e), encoding="utf-8")
                except OSError:
                    pass
                return
            if not upload.settings(self.cfg):
                return
            if self.cfg.get("envoi") == "oui":
                upload.queue(sess.dir)
                upload.send_pending(sess.dir.parent, self.cfg, self.client.log)
            elif self.cfg.get("envoi") != "non":
                self.emit("ask_send", {"dir": str(sess.dir)})
        if self.cfg.get("contribution") == "oui":
            threading.Thread(target=make_contribution, daemon=False).start()
        return out

    def send_game(self, folder: str):
        """Envoie une partie dont l'utilisateur vient d'accepter l'envoi (en arrière-plan)."""
        d = Path(folder)

        def work():
            try:
                upload.queue(d)
                upload.send_pending(d.parent, self.cfg, self.client.log)
            except Exception as e:
                self.client.log(f"Envoi impossible : {e}")
        threading.Thread(target=work, daemon=False).start()

    # ------------------------------------------------------------- polling
    def _start_polling(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _read_state(self, full: bool, timeout: float = 3) -> dict:
        r = self.client.run_lua(L.poll_fast(full), timeout=timeout)
        if isinstance(r, dict) and r.get("undef"):  # partie rechargée : on réinstalle
            r = self.client.run_lua(L.poll_install(), timeout=timeout)
        if not (isinstance(r, dict) and r.get("full")) and isinstance(self.state, dict):
            # lecture légère : on garde score / PC / joueurs de la dernière lecture complète
            for k in ("vp", "cp", "players", "sheet", "scoresheetDesc", "score"):
                if k in self.state and k not in r:
                    r[k] = self.state[k]
        return normalize_state(r)

    # Le veilleur Lua tourne DANS TTS et nous prévient seulement quand le tour ou la phase
    # change (+ un signe de vie par minute). Ici, on se contente de vérifier qu'il est vivant.
    def _on_custom(self, msg: dict):
        if msg.get("servoSkull"):
            self._last_beat = time.monotonic()
            self._beats += 1
            if msg.get("stale"):
                self._on_stale(msg)
                return
            self._events.put(msg)

    def _on_stale(self, msg: dict):
        """Aucun mouvement ni jet de dés depuis longtemps : la partie semble en pause, on prévient l'hôte.
        Seulement si la partie est réellement en cours (sinon le minuteur tourne dès la connexion, avant
        même « Start Game », et prévient pour rien)."""
        if not (self.state or {}).get("inGame"):
            return
        import json as _json
        try:
            info = _json.loads(msg.get("json") or "{}")
        except ValueError:
            info = {}
        self._stale_alert = True
        self.client.log(f"[inactivité] {info}")
        self.emit("alert", {"text": f"Aucun mouvement ni jet de dés depuis {info.get('minutes', '?')} min : "
                                    "la partie est en pause ?"})

    def _event_worker(self):
        import json as _json
        while True:
            msg = self._events.get()
            st = msg.get("state")
            if st is None and isinstance(msg.get("json"), str):
                try:
                    st = _json.loads(msg["json"])
                except ValueError:
                    st = None
            if not isinstance(st, dict) or not self.session:
                continue
            self._pending_drops = st.pop("drops", None)
            perf = st.pop("perf", None)
            if perf:
                self.client.log(f"[perf] veilleur {perf}")
            if not st.get("full") and isinstance(self.state, dict):
                for k in ("vp", "cp", "players", "sheet", "scoresheetDesc", "score"):
                    if k in self.state and k not in st:
                        st[k] = self.state[k]
            if self.session.mode != "host":
                self._promote_to_host(st)
            try:
                self.tick(st)
            except Exception as e:
                self.emit("error", f"Traitement de l'état : {e}")

    def _install_watch(self) -> dict:
        st = self.client.run_lua(L.watch_install(self.cfg.get("watch_interval_s", 2.0),
                                                  stale_s=int(self.cfg.get("stale_minutes", 7) * 60)), timeout=5)
        self._last_beat = time.monotonic()
        return st

    def _poll_loop(self):
        """Installe le veilleur une fois. Réinstallation seulement si on l'a déjà entendu puis
        perdu (partie rechargée) — jamais en boucle s'il n'a jamais parlé."""
        heard_once = False
        installs = 0
        if not self.cfg.get("watch_enabled", True):
            return
        try:
            st = self._install_watch()
            installs = 1
            if self.session and self.session.mode != "host":
                self._promote_to_host(st)
            self.tick(st)
        except TTSError:
            pass
        while not self._stop.wait(self.cfg.get("watchdog_s", 10.0)):
            if not self.session:
                return
            if self._beats > 0:
                heard_once = True
            silent = time.monotonic() - self._last_beat
            if self.session.mode == "host" and (silent < self.cfg.get("watch_timeout_s", 90.0) or not heard_once):
                if not heard_once and installs == 1 and silent > 30:
                    self.emit("error", "Le veilleur ne répond pas : pas d'alerte de tour ni de capture auto. F8 fonctionne. Lance le Diagnostic après la partie.")
                    installs = 2
                continue
            if installs >= 5:
                continue
            try:
                st = self._install_watch()
                installs += 1
            except TTSError:
                continue
            if self.session.mode != "host":
                self._promote_to_host(st)
            self.tick(st)

    def _promote_to_host(self, st: dict):
        """TTS répond enfin : on passe en mode hôte sans perdre les captures déjà faites."""
        self.mode = self.session.mode = "host"
        self.session.game["mode"] = "host"
        for c, n in (st.get("players") or {}).items():
            self.session.game["players"].setdefault(c, n)
        self.session._save_game()
        self.tracker.prev = None
        self.emit("session", {"mode": "host", "dir": str(self.session.dir), "promoted": True})

    def retry_connection(self):
        """Bouton « Réessayer » : force un essai immédiat."""
        if not self.session:
            return self.probe()
        try:
            st = normalize_state(self.client.run_lua(L.poll(), timeout=5))
        except TTSError:
            return "guest"
        if self.session.mode != "host":
            self._promote_to_host(st)
        self.tick(st)
        return "host"

    def toggle_mode(self) -> str:
        """Bouton « basculer hôte/invité » : corrige une détection automatique erronée sans
        relancer la partie. N'affecte jamais les captures déjà enregistrées — seulement
        l'étiquetage des captures à venir."""
        if not self.session:
            return self.mode
        new_mode = "guest" if self.mode == "host" else "host"
        self.mode = self.session.mode = new_mode
        self.session.game["mode"] = new_mode
        self.session._save_game()
        return new_mode

    def tick(self, st: dict):
        """Traite une lecture (appelé par la boucle, ou directement par les tests)."""
        st = normalize_state(st)
        events = self.tracker.update(st)
        self._apply_rounds(st)
        self.state = st
        self.emit("state", st)
        burst = False   # plusieurs phases d'un coup (passées trop vite) : une seule lecture de la table
        if getattr(self, "_stale_alert", False) and any(e[0] in ("phase_ended", "turn_changed") for e in events):
            self._stale_alert = False
            self.emit("alert_clear", None)
        for ev in events:
            kind = ev[0]
            mode = self.cfg.get("auto_capture", "phases")  # "phases", "movement" ou "off"
            if kind == "phase_ended" and mode == "phases":
                drops, self._pending_drops = getattr(self, "_pending_drops", None), None
                self.capture(kind="auto_phase", turn_key=ev[1], silent=True, ended_phase=ev[2], light=True,
                             drops=drops, reuse=burst)
                burst = True
            elif kind == "movement_ended" and mode == "movement" and self.cfg.get("auto_capture_after_movement", True):
                self.capture(kind="auto_move", turn_key=ev[1], silent=True, light=True)
            elif kind == "game_started" and not any(m["kind"] == "auto_deploy" for m in self.session.game["captures"]):
                self.capture(kind="auto_deploy", turn_key=ev[1], silent=True)
            elif kind == "missed_turn" and mode != "phases":
                self.pending_alert = ev[1]
                self.emit("alert", {"key": ev[1], "text": f"{turn_label(ev[1])} passé sans capture"})
            elif kind == "phase_ended" and is_final_phase_end(ev[1], ev[2], self.tracker.seq):
                self.emit("finish_suggest", {"round": ev[1][0]})

    # -------------------------------------------------------------- capture
    def capture(self, kind="manual", intent="", note="", turn_key=None, silent=False, photo=None,
                ended_phase=None, light=False, drops=None, reuse=False) -> dict | None:
        if not self.session:
            return None
        if turn_key is None and self.tracker and self.tracker.cur_key:
            turn_key = self.tracker.cur_key
        with self._lock:
            snap = None
            if self.session.mode == "host":
                if reuse and self._last_snap is not None:
                    import copy
                    snap = copy.deepcopy(self._last_snap)   # phase passée trop vite : même table, pas de nouvelle lecture
                else:
                    t_cap = time.monotonic()
                    try:
                        # 120 s : avec 10 s, un TTS chargé répondait après le délai et le résultat était jeté
                        snap = self.client.run_lua(L.capture(self.session.known_unit_guids(), self.session.my_color,
                                                              light=light and self.session.has_full_capture()), timeout=120)
                    except TTSError as e:
                        self.emit("error", f"Lecture de la table impossible : {e}")
                    if isinstance(snap, dict):  # mesures : où va le temps (Lua dans TTS ou aller-retour)
                        perf = snap.pop("perf", None)
                        self.client.log(f"[perf] capture {kind} {'légère' if light else 'complète'} "
                                        f"aller-retour={int((time.monotonic() - t_cap) * 1000)} ms ; TTS={perf}")
                    if snap:
                        import copy
                        self._last_snap = copy.deepcopy({k: v for k, v in snap.items() if k != "unitJson"})
            shot = None
            # photo : seulement pour les captures manuelles (bouger la caméra en pleine
            # phase de tir serait pénible ; les captures auto sont rendues en plan 2D)
            if photo is None:
                photo = self.cfg.get("photo_on_capture", False)
            if not silent and self.shoot and (photo or self.session.mode != "host"):
                if self.session.mode == "host" and self.cfg.get("fixed_camera", True):
                    try:
                        self.apply_camera(self.session.my_color)
                        time.sleep(self.cfg.get("camera_settle_s", 0.9))
                    except TTSError:
                        pass
                if self.ui:
                    self.ui.hide()
                try:
                    tmp = self.session.dir / "captures" / f"_tmp_{int(time.time()*1000)}"
                    shot = self.shoot(tmp)
                finally:
                    if self.ui:
                        self.ui.show()
            meta = self.session.add_capture(snap, kind, intent, note, shot,
                                            turn_key=turn_key, ended_phase=ended_phase, drops=drops)
            key = tuple(meta["turnKey"]) if meta.get("turnKey") else None
            if kind in ("manual", "catchup") and self.tracker:
                self.tracker.mark_captured(key)
                if self.pending_alert and key == tuple(self.pending_alert):
                    self.pending_alert = None
                    self.emit("alert_clear", None)
            recap.build(self.session)
            if len(self.session.game["captures"]) == 1:
                self._check_layout()
            if self.live_code:
                threading.Thread(target=live_share.push, args=(self.session, self.cfg, self.live_code),
                                 daemon=True).start()
            if self.cfg.get("toast_on_capture", False):
                try:
                    toast.show("Servo-Skull", _toast_text(meta))
                except Exception:
                    pass
            self.emit("captured", meta)
            return meta

    def undo_last_capture(self) -> dict | None:
        """Annule la dernière capture de la partie en cours (bouton overlay). Idempotent :
        sans capture à annuler, ne fait rien."""
        if not self.session:
            return None
        meta = self.session.remove_last_capture()
        if meta:
            recap.build(self.session)
            if self.live_code:
                threading.Thread(target=live_share.push, args=(self.session, self.cfg, self.live_code),
                                 daemon=True).start()
        return meta

    def _check_layout(self):
        """Prévient en tout début de partie si les décors ne collent pas au layout officiel de
        l'Event Companion (comparaison faite à chaque capture, jamais remontée sinon)."""
        try:
            data = recap.collect(self.session)
        except Exception:
            return
        has_terrain = any(len(t) > 6 and t[6] for c in data["captures"] for t in (c.get("terrain") or []))
        if not has_terrain:
            return
        fit = data.get("layoutFit")
        # une fois le layout identifié (carte de déploiement lue dans TTS), le récap utilise toujours les
        # dimensions EXACTES de l'Event Companion pour ces décors, quelle que soit la position réelle sur
        # la table — donc rien à signaler dans ce cas, même si le recouvrement mesuré est faible.
        if fit is None:
            self.emit("layout_warn", {"text": "Table non reconnue parmi les 45 layouts officiels de l'Event Companion "
                                               "— plan approximatif dans le récap, pas les dimensions officielles."})
        elif fit.get("rejected"):
            self.emit("layout_warn", {"text": f"Décors proches du layout {fit['layout']} (p.{fit['page']}) mais identité "
                                               "non confirmée — plan approximatif dans le récap, pas les dimensions officielles."})

    def catch_up(self, intent="", note=""):
        """Rattrapage du tour signalé par l'alerte : la table actuelle = fin de ce tour."""
        key = self.pending_alert
        if not key:
            return self.capture("manual", intent, note)
        return self.capture("catchup", intent, note, turn_key=tuple(key))

    def dismiss_alert(self):
        if self.pending_alert and self.tracker:
            self.tracker.mark_captured(tuple(self.pending_alert))
        self.pending_alert = None
        self.emit("alert_clear", None)

    # ------------------------------------------------------------- caméra
    def apply_camera(self, color: str, **override):
        """Place TA caméra sur la vue fixe enregistrée (ou sur les valeurs passées)."""
        c = {k: self.cfg.get(k, d) for k, d in (("camera_distance", 70), ("camera_pitch", 90),
                                               ("camera_yaw_offset", 0), ("camera_target_x", 0),
                                               ("camera_target_z", 0))}
        c.update(override)
        return self.client.run_lua(L.camera(color, c["camera_distance"], c["camera_pitch"],
                                            c["camera_yaw_offset"], c["camera_target_x"],
                                            c["camera_target_z"]))

    # ---------------------------------------------------------- restauration
    def restore(self, session: Session, cid: str) -> dict:
        snap = session.load_snapshot(cid)
        if not snap:
            raise ValueError("Cette capture n'a pas de positions (mode invité).")
        units = [{"guid": o["guid"], "pos": o["pos"], "rot": o["rot"], "name": o["name"]}
                 for o in snap["objects"] if o.get("unit")]
        spawn = session.spawn_json([u["guid"] for u in units])
        return self.client.run_lua(L.restore(units, spawn), timeout=20)
