"""Overlay : petite fenêtre toujours au premier plan, au-dessus de TTS."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import upload
from core import COLOR_FR, PHASE_FR, VERSION, Session, phase_label, turn_label

# Design system Cogitator
BG = "#080b10"        # bg0
PANEL = "#10141e"     # bg1 : champs, panneaux
RAISED = "#1a2235"    # bg2 : survol
BORDER = "#2a3348"
INK = "#dde3f0"       # t1
MUTE = "#8e95a8"      # t2
FAINT = "#6b7590"     # t3
CORAL = "#ff6b47"     # action principale
CYAN = "#38bdf8"      # interactif / sélection
RED = "#f87171"       # camp Rouge
BLUE = "#378add"      # camp Bleu
AMBER = "#fbbf24"     # avertissement
GREEN = "#34d399"
ALERT = "#3a1d12"     # fond de l'alerte (coral sombre)
ON_ACCENT = "#080b10"

# polices : Barlow Condensed / IBM Plex Mono si installées, sinon équivalents Windows
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI Semibold", 10)
FONT_BIG = ("Segoe UI", 15, "bold")
FONT_H = ("Segoe UI", 11, "bold")   # titres / boutons condensés
FONT_MONO = ("Consolas", 8)


def _setup_fonts(root):
    global FONT, FONT_B, FONT_BIG, FONT_H, FONT_MONO
    from tkinter import font as tkfont
    fam = set(tkfont.families(root))
    cond = next((f for f in ("Barlow Condensed SemiBold", "Barlow Condensed", "Bahnschrift SemiBold Condensed",
                             "Bahnschrift Condensed", "Bahnschrift") if f in fam), "Segoe UI")
    mono = next((f for f in ("IBM Plex Mono", "Share Tech Mono", "Consolas") if f in fam), "Courier New")
    body = next((f for f in ("Barlow", "Segoe UI") if f in fam), "TkDefaultFont")
    FONT = (body, 10)
    FONT_B = (body, 10, "bold")
    FONT_H = (cond, 12, "bold")
    FONT_BIG = (cond, 24, "bold")
    FONT_MONO = (mono, 8)


def _icon_path() -> Path | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for p in (base / "assets", Path(__file__).resolve().parent / "assets"):
        if (p / "servo-skull.ico").exists():
            return p
    return None


def beep():
    if sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass


class Overlay:
    def __init__(self, cfg: dict, save_cfg, controller_factory):
        self.cfg, self.save_cfg = cfg, save_cfg
        self.q: "queue.Queue[tuple]" = queue.Queue()
        if sys.platform == "win32":
            try:  # sinon Windows regroupe la fenêtre sous l'icône de Python
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Servo-Skull.Overlay")
            except Exception:
                pass
        self.root = tk.Tk()
        self.root.title("Servo-Skull")
        self._TKEY = "#ff00fe"  # couleur-clé : rendue transparente, donc jamais utilisée ailleurs
        self.root.configure(bg=self._TKEY)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)  # pas de barre de titre Windows : on dessine notre propre coquille
        if sys.platform == "win32":
            try:
                self.root.wm_attributes("-transparentcolor", self._TKEY)
            except tk.TclError:
                pass
        _setup_fonts(self.root)
        ip = _icon_path()
        self._badge_src = None
        if ip:
            try:
                if sys.platform == "win32":
                    self.root.iconbitmap(default=str(ip / "servo-skull.ico"))
                self._icon_img = tk.PhotoImage(file=str(ip / "servo-skull-256.png"))
                self.root.iconphoto(True, self._icon_img)
            except tk.TclError:
                pass
            if sys.platform == "win32":
                self.root.after(200, lambda: self._win_icon(ip / "servo-skull.ico"))
            try:
                from PIL import Image as _PILImage
                self._badge_src = _PILImage.open(str(ip / "servo-skull-256.png")).convert("RGBA")
            except Exception:
                self._badge_src = None
        if cfg.get("overlay_alpha", 1.0) < 1.0:  # désactivé par défaut : coûteux pour le jeu en dessous
            self.root.attributes("-alpha", cfg["overlay_alpha"])
        self.root.resizable(False, False)
        if cfg.get("overlay_geometry"):
            self.root.geometry(cfg["overlay_geometry"])
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.bind("<Map>", self._on_map)
        self.ctl = controller_factory(self)
        self.busy = False
        self._build_start()
        self.root.after(80, self._drain)
        self._hotkey_listener = None
        self._install_hotkey()

    def _win_icon(self, ico: Path):
        """Force l'icône (petite + grande) via l'API Windows : c'est la grande que la barre des tâches affiche."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            for size, which in ((16, 0), (32, 1), (48, 1)):  # ICON_SMALL=0, ICON_BIG=1
                h = user32.LoadImageW(None, str(ico), 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    user32.SendMessageW(hwnd, 0x80, which, h)  # WM_SETICON
        except Exception:
            pass

    # -------------------------------------------------------- coquille sans bordure
    def _make_draggable(self, widget, on_click=None):
        """Pas de barre de titre : on déplace la fenêtre en glissant ce widget.
        Un clic sans glissement (< 4 px) déclenche `on_click` au lieu de déplacer."""
        st = {"moved": False}
        def press(e):
            st["x0"], st["y0"] = e.x_root, e.y_root
            st["wx"], st["wy"] = self.root.winfo_x(), self.root.winfo_y()
            st["moved"] = False
        def drag(e):
            dx, dy = e.x_root - st["x0"], e.y_root - st["y0"]
            if abs(dx) > 4 or abs(dy) > 4:
                st["moved"] = True
            self.root.geometry(f"+{st['wx'] + dx}+{st['wy'] + dy}")
        def release(e):
            if not st["moved"] and on_click:
                on_click()
        widget.bind("<ButtonPress-1>", press)
        widget.bind("<B1-Motion>", drag)
        widget.bind("<ButtonRelease-1>", release)

    def _make_draggable_deep(self, widget, on_click=None):
        """Comme _make_draggable, mais sur tout un bloc (Frame + Labels enfants) : sinon le glisser ne
        marche que sur les quelques pixels de fond exposés entre les éléments empaquetés."""
        if isinstance(widget, (tk.Button, tk.Entry, tk.Text)):
            return
        self._make_draggable(widget, on_click=on_click)
        for child in widget.winfo_children():
            self._make_draggable_deep(child, on_click=on_click)

    def _popup_menu(self, widget, *items):
        """Menu clic-droit : remplace les contrôles de la barre de titre absente (dont Quitter)."""
        m = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=INK, activebackground=RAISED,
                   activeforeground=INK, bd=0, relief="flat")
        for label, cmd in items:
            if label is None:
                m.add_separator()
            else:
                m.add_command(label=label, command=cmd)
        widget.bind("<Button-3>", lambda e: m.tk_popup(e.x_root, e.y_root))
        return m

    def _relayout(self):
        """Réajuste la taille de la fenêtre au contenu réellement affiché (replié ou déplié)."""
        self.root.update_idletasks()
        self.root.geometry("")

    def _render_badge(self, target, status_color, notify=False, size=60):
        """Icône Servo-Skull : disque + anneau de statut (+ pastille si notification).
        Utilisée pour l'icône flottante (repliée) comme pour la mini-icône de l'en-tête (dépliée)."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return
        ring = max(2, round(size * 0.07))
        img = Image.new("RGB", (size, size), self._TKEY)
        draw = ImageDraw.Draw(img)
        draw.ellipse((ring + 1, ring + 1, size - ring - 1, size - ring - 1), fill=PANEL)
        draw.ellipse((ring // 2, ring // 2, size - ring // 2, size - ring // 2), outline=status_color, width=ring)
        if self._badge_src is not None:
            isz = int(size * 0.62)
            icon = self._badge_src.resize((isz, isz), Image.LANCZOS)
            img.paste(icon, ((size - isz) // 2, (size - isz) // 2), icon)
        if notify:
            d = max(8, size // 4)
            x0, y0 = size - d - 1, 1
            draw.ellipse((x0, y0, x0 + d, y0 + d), fill=CORAL, outline=PANEL, width=2)
        img_ref = ImageTk.PhotoImage(img)
        if target is getattr(self, "badge", None):
            self._badge_img = img_ref
        else:
            self._badge_mini_img = img_ref
        target.config(image=img_ref)

    def _badge_status(self):
        """Résume l'état en une couleur : vert = connecté sans souci, ambre = quelque chose à voir, gris = invité."""
        if hasattr(self, "alert") and self.alert.winfo_exists() and self.alert.winfo_ismapped():
            return AMBER, True
        if getattr(self, "_update_info", None) or getattr(self, "_unfinished_info", None) or getattr(self, "_layout_info", None):
            return AMBER, True
        if getattr(self, "mode", None) == "host":
            return GREEN, False
        if getattr(self, "mode", None) == "guest":
            return AMBER, False
        return MUTE, False

    def _update_badge(self):
        color, notify = self._badge_status()
        if hasattr(self, "badge") and self.badge.winfo_exists():
            self._render_badge(self.badge, color, notify, 60)
        if hasattr(self, "badge_mini") and self.badge_mini.winfo_exists():
            self._render_badge(self.badge_mini, color, notify, 26)

    def _round_corners(self, container, radius=14, bg=PANEL):
        """Masque les 4 coins d'un Frame rectangulaire pour lui donner l'air d'une carte arrondie
        (Tkinter n'a pas de forme arrondie native) : un petit carré transparent-sauf-le-quart-de-cercle
        posé par-dessus chaque coin, dans la couleur de fond de la carte."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return
        img = Image.new("RGB", (radius, radius), self._TKEY)
        ImageDraw.Draw(img).ellipse((0, 0, radius * 2, radius * 2), fill=bg)
        imgs = (img, img.transpose(Image.FLIP_LEFT_RIGHT),
                img.transpose(Image.FLIP_TOP_BOTTOM), img.transpose(Image.ROTATE_180))
        self._corner_imgs = tuple(ImageTk.PhotoImage(i) for i in imgs)
        placements = (dict(x=0, y=0), dict(relx=1, y=0, anchor="ne"),
                     dict(x=0, rely=1, anchor="sw"), dict(relx=1, rely=1, anchor="se"))
        for image, place_kw in zip(self._corner_imgs, placements):
            tk.Label(container, image=image, bg=self._TKEY, bd=0, highlightthickness=0).place(**place_kw)

    # ---------------------------------------------------- hooks contrôleur
    def emit(self, ev, payload=None):
        self.q.put((ev, payload))

    def hide(self):
        done = threading.Event()
        def _away():
            self._home = self.root.geometry().split("+", 1)[-1]
            self.root.geometry("+-20000+-20000")  # hors écran : pas de transparence, pas de vol du focus
            done.set()
        self.root.after(0, _away)
        done.wait(1.0)
        time.sleep(0.15)

    def show(self):
        self.root.after(0, lambda: self.root.geometry("+" + getattr(self, "_home", "40+40")))

    # -------------------------------------------------------------- écrans
    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _btn(self, parent, text, cmd, bg=None, fg=None, font=None, kind="ghost", padx=11, pady=5, **kw):
        """kind : primary (coral), ghost (contour discret), danger."""
        styles = {"primary": (CORAL, ON_ACCENT, "#ff8566"), "ghost": (PANEL, MUTE, RAISED),
                  "danger": (PANEL, RED, RAISED), "side": (bg or PANEL, fg or INK, bg or RAISED)}
        b0, f0, act = styles.get(kind, styles["ghost"])
        b = tk.Button(parent, text=text.upper() if kind != "side" else text, command=cmd,
                      bg=bg or b0, fg=fg or f0, activebackground=act, activeforeground=INK if kind == "ghost" else (fg or f0),
                      relief="flat", bd=0, padx=padx, pady=pady,
                      font=font or (FONT_H if kind in ("primary", "side") else (FONT_H[0], 10, "bold")), cursor="hand2",
                      highlightthickness=1, highlightbackground=BORDER, **kw)
        if kind == "ghost":
            b.bind("<Enter>", lambda e: b.config(fg=INK, bg=RAISED))
            b.bind("<Leave>", lambda e: b.config(fg=f0, bg=b0))
        return b

    def _label(self, parent, text, bg=BG):
        """Libellé de champ façon Cogitator : mono, petit, espacé."""
        return tk.Label(parent, text=text.upper(), bg=bg, fg=FAINT, font=FONT_MONO, anchor="w")

    def _field(self, parent, multiline=False):
        box = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        if multiline:
            w = tk.Text(box, bg=PANEL, fg=INK, insertbackground=CYAN, relief="flat", font=FONT, height=3,
                        width=38, wrap="word", padx=8, pady=6, highlightthickness=0)
        else:
            w = tk.Entry(box, bg=PANEL, fg=INK, insertbackground=CYAN, relief="flat", font=FONT, width=38,
                         highlightthickness=0)
        w.pack(fill="x", ipady=0 if multiline else 5, padx=0)
        w.bind("<FocusIn>", lambda e: box.config(bg=CYAN))
        w.bind("<FocusOut>", lambda e: box.config(bg=BORDER))
        return box, w

    def _window_controls(self, parent):
        """Réduire / fermer : il n'y a plus de barre de titre Windows pour les fournir.
        Mêmes boutons discrets (_btn ghost) que le reste de l'appli, pas de croix rouge criarde."""
        self._btn(parent, "✕", self.quit, font=(FONT_H[0], 10), padx=5, pady=1).pack(side="right")
        self._btn(parent, "–", self._minimize, font=(FONT_H[0], 10), padx=5, pady=1).pack(side="right", padx=(0, 2))

    def _minimize(self):
        """Réduit dans la barre des tâches. Astuce nécessaire : une fenêtre overrideredirect n'a pas
        d'icône dans la barre des tâches, donc on redonne temporairement sa bordure avant de réduire ;
        _on_map la retire dès que la fenêtre reparaît (clic sur l'icône de la barre des tâches)."""
        self.root.overrideredirect(False)
        self.root.iconify()

    def _on_map(self, _e=None):
        if self.root.state() == "normal" and self.root.overrideredirect() == 0:
            self.root.overrideredirect(True)

    def _header(self, parent, right_text="", right_color=MUTE):
        """Fait aussi office de barre de titre (il n'y en a plus de Windows) : on la glisse pour
        déplacer la fenêtre, et les boutons de droite donnent réduire / fermer."""
        h = tk.Frame(parent, bg=PANEL, padx=14, pady=8, cursor="fleur")
        h.pack(fill="x")
        title = tk.Label(h, text="SERVO-SKULL", bg=PANEL, fg=CORAL, font=FONT_H)
        title.pack(side="left")
        self._window_controls(h)
        if right_text:
            tk.Label(h, text=right_text.upper(), bg=PANEL, fg=right_color, font=FONT_MONO).pack(side="right", padx=(0, 10))
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")
        self._make_draggable_deep(h)
        self._popup_menu(h, ("Quitter", self.quit))
        self._popup_menu(title, ("Quitter", self.quit))
        return h

    def _update_label(self, parent, bg=BG):
        lbl = tk.Label(parent, text="", bg=bg, fg=CYAN, font=FONT, cursor="hand2",
                       wraplength=330, justify="left", padx=10, pady=4)
        lbl.bind("<Button-1>", lambda e: self._open_update())
        self.lbl_update = lbl
        self._apply_update_banner()

    def _apply_update_banner(self):
        info = getattr(self, "_update_info", None)
        if info and hasattr(self, "lbl_update") and self.lbl_update.winfo_exists():
            self.lbl_update.config(text=f"↑ Servo-Skull v{info['version']} disponible — clique pour la page de téléchargement")
            self.lbl_update.pack(fill="x")

    def _open_update(self):
        info = getattr(self, "_update_info", None)
        if info:
            webbrowser.open(info["url"])

    def _unfinished_label(self, parent, bg=BG):
        lbl = tk.Label(parent, text="", bg=bg, fg=AMBER, font=FONT, cursor="hand2",
                       wraplength=330, justify="left", padx=10, pady=4)
        lbl.bind("<Button-1>", lambda e: self._dismiss_unfinished())
        self.lbl_unfinished = lbl
        self._apply_unfinished_banner()

    def _apply_unfinished_banner(self):
        info = getattr(self, "_unfinished_info", None)
        if info and hasattr(self, "lbl_unfinished") and self.lbl_unfinished.winfo_exists():
            self.lbl_unfinished.config(
                text=f"⚠ La partie « {info['name']} » ne s'est pas terminée normalement "
                     f"({info['captures']} capture(s) enregistrée(s)) — son score/film peut être incomplet. "
                     "Clique pour masquer.")
            self.lbl_unfinished.pack(fill="x")

    def _dismiss_unfinished(self):
        self._unfinished_info = None
        if hasattr(self, "lbl_unfinished") and self.lbl_unfinished.winfo_exists():
            self.lbl_unfinished.pack_forget()

    def _layout_label(self, parent, bg=BG):
        lbl = tk.Label(parent, text="", bg=bg, fg=AMBER, font=FONT, cursor="hand2",
                       wraplength=330, justify="left", padx=10, pady=4)
        lbl.bind("<Button-1>", lambda e: self._dismiss_layout())
        self.lbl_layout = lbl
        self._apply_layout_banner()

    def _apply_layout_banner(self):
        info = getattr(self, "_layout_info", None)
        if info and hasattr(self, "lbl_layout") and self.lbl_layout.winfo_exists():
            self.lbl_layout.config(text=f"⚠ {info['text']} Clique pour masquer.")
            self.lbl_layout.pack(fill="x")

    def _dismiss_layout(self):
        self._layout_info = None
        if hasattr(self, "lbl_layout") and self.lbl_layout.winfo_exists():
            self.lbl_layout.pack_forget()

    def _build_start(self):
        self._clear()
        self._header(self.root, f"nouvelle partie · v{VERSION}")
        self._update_label(self.root)
        self._unfinished_label(self.root)
        f = tk.Frame(self.root, bg=BG, padx=14, pady=14)
        f.pack(fill="both")
        tk.Label(f, text="Quelle couleur joues-tu ?", bg=BG, fg=INK, font=FONT_H).pack(anchor="w")
        tk.Label(f, text="Lance d'abord ta partie LCT dans TTS, en hôte.", bg=BG, fg=MUTE, font=FONT).pack(anchor="w", pady=(2, 10))
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x")
        last = self.cfg.get("last_color", "Red")
        for c, col in (("Red", RED), ("Blue", BLUE)):
            b = self._btn(row, ("● " if c == last else "") + COLOR_FR[c].upper(), lambda c=c: self._start(c),
                          bg=col, fg=ON_ACCENT, kind="side", width=11)
            b.pack(side="left", padx=(0, 8), ipady=4)
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        self._btn(f, "Restaurer un tour…", self._restore_dialog).pack(anchor="w")
        self.start_msg = tk.Label(f, text="", bg=BG, fg=MUTE, font=FONT, wraplength=300, justify="left")
        self.start_msg.pack(anchor="w", pady=(8, 0))
        self._relayout()

    def _start(self, color):
        self.cfg["last_color"] = color
        self.save_cfg(self.cfg)
        self.start_msg.config(text="Connexion à TTS…")
        self.root.update_idletasks()
        def work():
            try:
                self.ctl.start_session(color)
            except Exception as e:
                self.emit("error", f"Démarrage impossible : {e}")
        threading.Thread(target=work, daemon=True).start()

    def _build_main(self, mode):
        """Icône flottante par défaut ; un clic la transforme en carte (round · phase · score · note · captures) —
        jamais les deux formes à la fois."""
        self._clear()
        me = self.ctl.session.my_color
        self.mode = mode
        self.badge = tk.Label(self.root, bg=self._TKEY, bd=0, highlightthickness=0, cursor="hand2")
        self.badge.pack(anchor="w")
        self._make_draggable(self.badge, on_click=self._toggle_shell)
        self._popup_menu(self.badge,
                         ("Déplier/replier", self._toggle_shell),
                         ("Film de la partie", self._open_film),
                         (None, None),
                         ("Quitter", self.quit))
        self._shell_open = False
        self.shell = tk.Frame(self.root, bg=PANEL)

        bar = tk.Frame(self.shell, bg=PANEL, padx=10, pady=6, cursor="hand2")
        bar.pack(fill="x")
        top = tk.Frame(bar, bg=PANEL)
        top.pack(fill="x")
        self._window_controls(top)
        row = tk.Frame(bar, bg=PANEL)
        row.pack(fill="x", pady=(2, 0))
        self.badge_mini = tk.Label(row, bg=PANEL, bd=0, highlightthickness=0, cursor="hand2")
        self.badge_mini.pack(side="left")
        info = tk.Frame(row, bg=PANEL)
        info.pack(side="left", padx=(8, 0))
        self.lbl_turn = tk.Label(info, text="EN ATTENTE", bg=PANEL, fg=MUTE, font=FONT_MONO, anchor="w")
        self.lbl_turn.pack(anchor="w")
        self.lbl_count = tk.Label(info, text="0 capture", bg=PANEL, fg=FAINT, font=FONT_MONO, anchor="w")
        self.lbl_count.pack(anchor="w")
        score = tk.Frame(row, bg=PANEL)
        score.pack(side="right")
        self.sc = {}
        for c, col in (("Red", RED), ("Blue", BLUE)):
            hidden = tk.Label(row)  # nom du joueur : affiché seulement dans l'infobulle de la barre
            v = tk.Label(score, text="–", bg=PANEL, fg=col, font=(FONT_H[0], 20, "bold"))
            self.sc[c] = (hidden, v)
        self.sc["Red"][1].pack(side="left")
        tk.Label(score, text="–", bg=PANEL, fg=FAINT, font=FONT).pack(side="left", padx=3)
        self.sc["Blue"][1].pack(side="left")
        self._make_draggable_deep(bar, on_click=self._toggle_shell)
        tk.Frame(self.shell, bg=BORDER, height=1).pack(fill="x")

        self._update_label(self.shell, bg=PANEL)
        self._unfinished_label(self.shell, bg=PANEL)
        self._layout_label(self.shell, bg=PANEL)
        # ligne d'état : visible seulement s'il y a quelque chose d'important à dire
        self.lbl_status = tk.Label(self.shell, text="", fg=MUTE, bg=PANEL, font=FONT, anchor="w", wraplength=300,
                                   justify="left", padx=12)
        self.alert = tk.Frame(self.shell, bg=ALERT, padx=10, pady=6, highlightthickness=1, highlightbackground=CORAL)
        self.alert_lbl = tk.Label(self.alert, text="", bg=ALERT, fg=INK, font=FONT_B, wraplength=280, justify="left")
        self.alert_lbl.pack(anchor="w")
        ar = tk.Frame(self.alert, bg=ALERT)
        ar.pack(anchor="w", pady=(6, 0))
        self._btn(ar, "Rattraper", self._catch_up, kind="primary").pack(side="left")
        self._btn(ar, "Ignorer", self._dismiss).pack(side="left", padx=6)
        self.alert_anchor = tk.Frame(self.shell, bg=PANEL)
        self.alert_anchor.pack(fill="x")

        f = tk.Frame(self.shell, bg=PANEL, padx=12, pady=10)
        f.pack(fill="x")
        tk.Label(f, text="Tout est capturé automatiquement à chaque fin de phase.\nRien à faire : ajoute une note seulement si tu veux.",
                 bg=PANEL, fg=FAINT, font=FONT, justify="left").pack(anchor="w")
        self._label(f, "Note (facultatif)", bg=PANEL).pack(fill="x", pady=(10, 3))
        box, self.e_note = self._field(f, multiline=True)
        box.pack(fill="x")
        self.guest = None
        if mode == "guest":
            g = tk.Frame(f, bg=PANEL)
            g.pack(fill="x", pady=(6, 0))
            tk.Label(g, text="TTS ne répond pas : pas de lecture de la table.", fg=AMBER, bg=PANEL, font=FONT,
                     justify="left").grid(row=0, column=0, columnspan=6, sticky="w")
            self.guest = {}
            for col, (k, lab, w) in enumerate((("round", "Round", 3), ("me", "Moi", 4), ("opp", "Adv.", 4))):
                tk.Label(g, text=lab.upper(), fg=FAINT, bg=PANEL, font=FONT_MONO).grid(row=1, column=col * 2, sticky="w", padx=(0, 4), pady=(6, 0))
                e = tk.Entry(g, bg=RAISED, fg=INK, insertbackground=CYAN, relief="flat", font=FONT, width=w,
                             highlightthickness=1, highlightbackground=BORDER, highlightcolor=CYAN)
                e.grid(row=1, column=col * 2 + 1, sticky="w", padx=(0, 10))
                self.guest[k] = e
            gb = tk.Frame(g, bg=PANEL)
            gb.grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
            self._btn(gb, "Reconnecter", self._retry).pack(side="left")
            self._btn(gb, "Diagnostic", self._diagnose).pack(side="left", padx=6)
        hk = self.cfg.get("hotkey", "f8").upper()
        self.b_cap = self._btn(f, f"Capturer avec cette note   [{hk}]", self._capture, kind="primary")
        self.b_cap.pack(fill="x", pady=(10, 4), ipady=3)
        # réglages (capture d'écran, fichier anonyme, envoi) : réglés une fois, pas à revoir à chaque partie
        self.v_photo = tk.BooleanVar(value=bool(self.cfg.get("photo_on_capture", False)))
        self.v_contrib = tk.BooleanVar(value=self.cfg.get("contribution") == "oui")
        self.v_envoi = tk.BooleanVar(value=self.cfg.get("envoi") == "oui")
        tk.Frame(self.shell, bg=BORDER, height=1).pack(fill="x")
        bot = tk.Frame(self.shell, bg=PANEL, padx=10, pady=7)
        bot.pack(fill="x")
        self._btn(bot, "🎬", self._open_film, font=(FONT_H[0], 13)).pack(side="left")
        if mode == "host":
            self._btn(bot, "🎥", self._camera_dialog, font=(FONT_H[0], 13)).pack(side="left", padx=(4, 0))
            self._btn(bot, "⚕", self._diagnose, font=(FONT_H[0], 13)).pack(side="left", padx=(4, 0))
        self._btn(bot, "↺", self._restore_dialog, font=(FONT_H[0], 13)).pack(side="left", padx=(4, 0))
        gear = self._btn(bot, "⚙", lambda: self._open_settings_menu(gear), font=(FONT_H[0], 13))
        gear.pack(side="left", padx=(4, 0))
        self._btn(bot, "Terminer", self._finish, kind="danger").pack(side="right")

        self._round_corners(self.shell)
        self.n_caps = 0
        self._update_badge()
        self._relayout()

    def _toggle_shell(self):
        """Clic sur l'icône (repliée ou dans l'en-tête de la carte) : l'une remplace l'autre, jamais les deux ensemble."""
        self._shell_open = not self._shell_open
        if self._shell_open:
            self.badge.pack_forget()
            self.shell.pack(fill="x")
        else:
            self.shell.pack_forget()
            self.badge.pack(anchor="w")
        self._relayout()

    # ------------------------------------------------------------ actions
    def _open_settings_menu(self, anchor):
        """Réglages (capture d'écran, fichier anonyme, envoi) : dans un menu à part, pas affichés en
        permanence — on les règle une fois, pas besoin de les revoir à chaque partie."""
        def _toggle(key, var, on="oui", off="non"):
            self.cfg[key] = (on if var.get() else off) if key != "photo_on_capture" else var.get()
            self.save_cfg(self.cfg)
        m = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=INK, activebackground=RAISED,
                   activeforeground=INK, selectcolor=INK, bd=0, relief="flat")
        if self.mode == "host":
            m.add_checkbutton(label="Capture d'écran (bouge ta caméra)", variable=self.v_photo,
                              command=lambda: _toggle("photo_on_capture", self.v_photo))
        m.add_checkbutton(label="Fichier anonyme pour les stats (rien n'est envoyé)", variable=self.v_contrib,
                          command=lambda: _toggle("contribution", self.v_contrib))
        if upload.settings(self.cfg):
            m.add_checkbutton(label="Envoyer ce fichier anonyme à la fin de chaque partie", variable=self.v_envoi,
                              command=lambda: _toggle("envoi", self.v_envoi))
        m.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())

    def _texts(self, clear=True):
        note = self.e_note.get("1.0", "end").strip()
        if clear:
            self.e_note.delete("1.0", "end")
        return note

    def _guest_score(self):
        if not self.guest:
            return None
        me = self.ctl.session.my_color
        opp = "Blue" if me == "Red" else "Red"

        def num(e):
            try:
                return int(e.get())
            except ValueError:
                return None
        return {"round": num(self.guest["round"]), "vp": {me: num(self.guest["me"]), opp: num(self.guest["opp"])}}

    def _run(self, fn, *a, **kw):
        if self.busy:
            return
        self.busy = True
        self.b_cap.config(state="disabled", text="CAPTURE…")

        def work():
            try:
                fn(*a, **kw)
            except Exception as e:
                self.emit("error", str(e))
            finally:
                self.emit("idle", None)
        threading.Thread(target=work, daemon=True).start()

    def _capture(self):
        if not getattr(self.ctl, "session", None) or not hasattr(self, "b_cap") or not self.b_cap.winfo_exists():
            return
        note = self._texts()
        self._run(self.ctl.capture, "manual", "", note, manual_score=self._guest_score())

    def _catch_up(self):
        note = self._texts()
        self._run(self.ctl.catch_up, "", note)

    def _dismiss(self):
        self.ctl.dismiss_alert()

    def _open_film(self):
        if self.ctl.session:
            import film
            webbrowser.open((film.build(self.ctl.session)).resolve().as_uri())

    def _finish(self):
        if not messagebox.askyesno("Terminer la partie", "Terminer cette partie et ouvrir le film ?", parent=self.root):
            return
        out = self.ctl.finish_session()
        if out:
            webbrowser.open(out.resolve().as_uri())
        self._build_start()

    def _retry(self):
        def work():
            if self.ctl.retry_connection() != "host":
                self.emit("error", "Toujours pas de réponse de TTS. Clique « Diagnostic » pour savoir pourquoi.")
        threading.Thread(target=work, daemon=True).start()

    def _diagnose(self):
        def work():
            res = self.ctl.client.diagnose()
            self.emit("diag", res)
        self._status("Diagnostic en cours…")
        threading.Thread(target=work, daemon=True).start()

    def _show_diag(self, res):
        lines = [("✓ " if ok else "✗ ") + txt for ok, txt in res]
        log = self.ctl.client.log_path
        if log:
            lines.append(f"\nJournal détaillé : {log}")
        messagebox.showinfo("Diagnostic de connexion à TTS", "\n\n".join(lines), parent=self.root)
        self._status("Diagnostic terminé." if all(ok for ok, _ in res) else "Diagnostic : voir la fenêtre.")

    def _camera_dialog(self):
        """Réglage de la vue fixe : chaque curseur bouge ta caméra TTS en direct."""
        if not self.ctl.session or self.ctl.session.mode != "host":
            return
        color = self.ctl.session.my_color
        win = tk.Toplevel(self.root, bg=BG, padx=14, pady=10)
        win.title("Régler la vue fixe")
        win.attributes("-topmost", True)
        tk.Label(win, text="Bouge les curseurs : ta caméra TTS suit en direct.\n"
                           "Quand toute la table est bien cadrée, clique Enregistrer.",
                 bg=BG, fg=MUTE, font=FONT, justify="left").pack(anchor="w", pady=(0, 6))
        specs = (("camera_distance", "Hauteur (zoom)", 20, 200, 1),
                 ("camera_pitch", "Inclinaison (90 = pile au-dessus)", 45, 90, 1),
                 ("camera_yaw_offset", "Rotation", -180, 180, 5),
                 ("camera_target_x", "Décalage gauche / droite", -20, 20, 0.5),
                 ("camera_target_z", "Décalage haut / bas", -20, 20, 0.5))
        vars_ = {}
        pending = {"id": None}

        def push():
            pending["id"] = None
            vals = {k: v.get() for k, v in vars_.items()}
            threading.Thread(target=lambda: self._safe(self.ctl.apply_camera, color, **vals), daemon=True).start()

        def changed(_=None):
            if pending["id"]:
                win.after_cancel(pending["id"])
            pending["id"] = win.after(150, push)  # évite d'inonder TTS pendant le glissement

        for key, label, lo, hi, step in specs:
            tk.Label(win, text=label, bg=BG, fg=INK, font=FONT).pack(anchor="w")
            v = tk.DoubleVar(value=self.cfg.get(key, {"camera_distance": 70, "camera_pitch": 90}.get(key, 0)))
            tk.Scale(win, variable=v, from_=lo, to=hi, resolution=step, orient="horizontal", length=320,
                     bg=BG, fg=INK, troughcolor=PANEL, highlightthickness=0, command=changed).pack(anchor="w")
            vars_[key] = v
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", pady=(8, 0))

        def reset():
            for k, v in vars_.items():
                v.set({"camera_distance": 70, "camera_pitch": 90}.get(k, 0))
            changed()

        def save():
            for k, v in vars_.items():
                self.cfg[k] = round(v.get(), 2)
            self.save_cfg(self.cfg)
            self._status("✓ Vue fixe enregistrée : chaque capture reprendra exactement ce cadrage.", "#8fd18f")
            win.destroy()
        self._btn(row, "Valeurs par défaut", reset).pack(side="left")
        self._btn(row, "Enregistrer", save, kind="primary").pack(side="right")
        push()

    def _safe(self, fn, *a, **kw):
        try:
            fn(*a, **kw)
        except Exception as e:
            self.emit("error", f"Caméra : {e}")

    def request_restore(self, folder, cid):
        """Appelée par le film (serveur local) : demande de restaurer une capture. Rien ne bouge sans ton accord ici."""
        try:
            s = Session.open(Path(folder))
            m = next((c for c in s.game["captures"] if c["id"] == cid and c.get("data")), None)
        except Exception:
            m = None
        if not m:
            self.emit("error", "Rejouer : capture introuvable ou sans positions.")
            return

        def ask():
            self.root.deiconify()
            self.root.lift()
            ok = messagebox.askyesno("Rejouer ce moment",
                                     f"Le film demande de remettre la table dans l'état :\n« {m['label']} »\n\n"
                                     "Les figurines de la table ouverte dans TTS vont être déplacées.\n"
                                     "À faire sur une partie chargée pour l'analyse, pas en plein match.",
                                     parent=self.root, icon="warning")
            if not ok:
                return

            def work():
                try:
                    r = self.ctl.restore(s, cid)
                    self.emit("info", f"Moment rejoué : {r.get('moved', 0)} déplacées, {r.get('spawned', 0)} recréées, "
                                      f"{r.get('parked', 0)} rangées hors table.")
                except Exception as e:
                    self.emit("error", f"Restauration impossible : {e}")
            threading.Thread(target=work, daemon=True).start()
        self.emit("call", ask)  # exécuté par le fil Tk (_drain)

    def _restore_dialog(self):
        root_dir = Path(self.cfg["replays_dir"])
        folder = filedialog.askdirectory(parent=self.root, initialdir=str(root_dir),
                                         title="Choisis le dossier de la partie à restaurer")
        if not folder:
            return
        try:
            s = Session.open(Path(folder))
        except Exception:
            messagebox.showerror("Restaurer", "Ce dossier n'est pas une partie enregistrée.", parent=self.root)
            return
        caps = [m for m in s.game["captures"] if m.get("data")]
        saves = s.game.get("ttsSaves") or []
        if not caps and not saves:
            messagebox.showinfo("Restaurer", "Aucune capture ni sauvegarde TTS dans cette partie.", parent=self.root)
            return
        win = tk.Toplevel(self.root, bg=BG, padx=12, pady=10)
        win.title("Restaurer un tour")
        win.attributes("-topmost", True)
        tk.Label(win, text="Remet les figurines dans l'état de la capture choisie.\n"
                           "À faire sur une partie chargée exprès pour l'analyse, pas en plein match.",
                 bg=BG, fg=AMBER, font=FONT, justify="left").pack(anchor="w")
        lb = tk.Listbox(win, bg=PANEL, fg=INK, selectbackground="#3a3f48", relief="flat", font=FONT,
                        width=58, height=max(1, min(16, len(caps))))
        for m in caps:
            lb.insert("end", f"{m['id']}  {m['label']}" + (f"  — {m['intent'][:30]}" if m.get("intent") else ""))
        lb.pack(fill="both", pady=8)
        lb.selection_set("end")

        def go():
            sel = lb.curselection()
            if not sel or not caps:
                return
            m = caps[sel[0]]
            if not messagebox.askyesno("Restaurer", f"Restaurer « {m['label']} » sur la table ouverte dans TTS ?\n\n"
                                       "Les figurines vont être déplacées.", parent=win):
                return
            win.destroy()

            def work():
                try:
                    r = self.ctl.restore(s, m["id"])
                    self.emit("info", f"Restauré : {r.get('moved', 0)} déplacées, {r.get('spawned', 0)} recréées, "
                                      f"{r.get('parked', 0)} rangées hors table.")
                except Exception as e:
                    self.emit("error", f"Restauration impossible : {e}")
            threading.Thread(target=work, daemon=True).start()
        self._btn(win, "Restaurer ce tour", go, kind="primary").pack(anchor="e")

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", pady=12)
        self._label(win, f"Sauvegardes TTS de la partie · {len(saves)}").pack(fill="x")
        tk.Label(win, text="Vraies sauvegardes TTS, une par moment de la partie. Les rendre disponibles\n"
                           "dans le menu de TTS : Jeux › Sauvegarder & charger › dossier Servo-Skull.",
                 bg=BG, fg=MUTE, font=FONT, justify="left").pack(anchor="w", pady=(4, 8))

        def export():
            out = self.ctl.export_saves_to_tts(s)
            if out:
                messagebox.showinfo("Sauvegardes TTS", f"{len(saves)} sauvegarde(s) copiée(s) dans :\n{out}\n\n"
                                    "Dans TTS : Jeux › Sauvegarder & charger › Servo-Skull.", parent=win)
            else:
                messagebox.showinfo("Sauvegardes TTS", "Aucune sauvegarde TTS gardée pour cette partie.", parent=win)
        b = self._btn(win, "Mettre dans TTS", export)
        b.pack(anchor="e")
        if not saves:
            b.config(state="disabled")
        if not caps:
            lb.delete(0, "end")
            lb.insert("end", "(aucune capture avec positions)")

    # ----------------------------------------------------------- événements
    def _drain(self):
        try:
            while True:
                ev, p = self.q.get_nowait()
                self._on(ev, p)
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def _status(self, txt, color=MUTE):
        if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
            self.lbl_status.config(text=txt, fg=color)
            if txt and color not in (MUTE, FAINT):
                self.lbl_status.pack(fill="x", pady=(4, 4), before=self.alert_anchor)
                if hasattr(self, "_status_job"):
                    self.root.after_cancel(self._status_job)
                self._status_job = self.root.after(8000, lambda: self.lbl_status.winfo_exists() and self.lbl_status.pack_forget())
        elif hasattr(self, "start_msg") and self.start_msg.winfo_exists():
            self.start_msg.config(text=txt, fg=color)

    def _on(self, ev, p):
        if ev == "call":
            p()
            return
        if ev == "diag":
            self._show_diag(p)
        elif ev == "session":
            self._build_main(p["mode"])
            if p.get("promoted"):
                self._status("✓ TTS répond : mode hôte activé (caméra, positions, alertes).", "#8fd18f")
                return
            if p["mode"] == "guest":
                self._status("TTS ne répond pas au script : mode invité (capture d'écran seule).", AMBER)
            else:
                self._status("Connecté · capture automatique à chaque fin de phase.", GREEN)
        elif ev == "state" and p and hasattr(self, "lbl_turn") and self.lbl_turn.winfo_exists():
            ph = phase_label(p.get("phaseName"))
            key = (p.get("round"), p.get("turn"))
            if not p.get("inGame"):
                txt, col = "Pas lancée", MUTE
            else:
                me = self.ctl.session.my_color if self.ctl.session else None
                txt = f"R{key[0] or '?'} · " + ("moi" if key[1] == me else "adv.") + (f" · {ph}" if ph else "")
                col = (RED if key[1] == "Red" else BLUE) if key[1] else MUTE
            self.lbl_turn.config(text=txt.upper(), fg=col)
            vp, pl = p.get("vp") or {}, p.get("players") or {}
            me = self.ctl.session.my_color if self.ctl.session else None
            for c in ("Red", "Blue"):
                if c in getattr(self, "sc", {}) and self.sc[c][1].winfo_exists():
                    who = (pl.get(c) or COLOR_FR[c]).upper() + (" · MOI" if c == me else "")
                    self.sc[c][0].config(text=who)
                    self.sc[c][1].config(text=str(vp.get(c, "–")) if vp.get(c) is not None else "–")
        elif ev == "update":
            self._update_info = p
            self._apply_update_banner()
            self._update_badge()
            self._relayout()
        elif ev == "unfinished":
            self._unfinished_info = p
            self._apply_unfinished_banner()
            self._update_badge()
            self._relayout()
        elif ev == "layout_warn":
            self._layout_info = p
            self._apply_layout_banner()
            self._update_badge()
            self._relayout()
        elif ev == "alert" and hasattr(self, "alert"):
            self.alert_lbl.config(text=f"⚠  {p['text']}")
            self.alert.pack(fill="x", padx=8, pady=(6, 6), before=self.alert_anchor)
            beep()
            self._update_badge()
            self._relayout()
        elif ev == "alert_clear" and hasattr(self, "alert") and self.alert.winfo_exists():
            self.alert.pack_forget()
            self._update_badge()
            self._relayout()
        elif ev == "captured":
            if hasattr(self, "lbl_count") and self.lbl_count.winfo_exists() and self.ctl.session:
                n = len(self.ctl.session.game["captures"])
                self.lbl_count.config(text=f"{n} capture" + ("" if n == 1 else "s"))
            if p["kind"] in ("manual", "catchup"):
                self._status(f"✓ Capturé : {p['label']}", "#8fd18f")
            else:
                self._status(f"↻ Capture auto : {p['label']}")
        elif ev == "idle" and hasattr(self, "b_cap") and self.b_cap.winfo_exists():
            self.busy = False
            self.b_cap.config(state="normal", text=f"CAPTURER AVEC CETTE NOTE   [{self.cfg.get('hotkey', 'f8').upper()}]")
        elif ev == "error":
            self._status(f"⚠ {p}", "#ff8a80")
        elif ev == "saved":
            self._status(f"Sauvegarde TTS gardée : {p['label']}", MUTE)
        elif ev == "info":
            self._status(p, "#8fd18f")
        elif ev == "lost":
            self._status("⚠ TTS ne répond plus (partie fermée ?). Les captures reprennent dès qu'il répond.", AMBER)
        elif ev == "hotkey":
            self._capture()
        elif ev == "ask_send":
            self._ask_send(p["dir"])

    # -------------------------------------------------------------- divers
    def _install_hotkey(self):
        """Raccourci global via RegisterHotKey (Windows) : aucun crochet clavier, aucun coût
        pour les autres programmes. L'ancien crochet (pynput) faisait passer chaque touche
        et chaque mouvement de TTS par Python."""
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes
        key = self.cfg.get("hotkey", "f8").lower().replace(" ", "")
        mods, vk = 0x4000, None  # MOD_NOREPEAT
        for part in key.split("+"):
            if part in ("ctrl", "control"):
                mods |= 0x2
            elif part == "alt":
                mods |= 0x1
            elif part == "shift":
                mods |= 0x4
            elif part in ("win", "cmd"):
                mods |= 0x8
            elif part.startswith("f") and part[1:].isdigit():
                vk = 0x70 + int(part[1:]) - 1
            elif len(part) == 1:
                vk = ord(part.upper())
        if vk is None:
            return
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

        def loop():
            self._hotkey_tid = kernel32.GetCurrentThreadId()
            if not user32.RegisterHotKey(None, 1, mods, vk):
                self.emit("error", f"Raccourci {key.upper()} déjà pris par un autre programme : change « hotkey » dans config.json.")
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:  # WM_HOTKEY
                    self.emit("hotkey")
            user32.UnregisterHotKey(None, 1)
        threading.Thread(target=loop, daemon=True).start()

    def quit(self):
        try:
            self.cfg["overlay_geometry"] = f"+{self.root.winfo_x()}+{self.root.winfo_y()}"
            self.save_cfg(self.cfg)
        except Exception:
            pass
        if getattr(self, "_hotkey_tid", None) and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._hotkey_tid, 0x0012, 0, 0)  # WM_QUIT
        # la fenêtre disparaît tout de suite ; le rangement (arrêt du veilleur dans TTS,
        # génération du film) se termine ensuite, sans faire attendre
        self.root.withdraw()
        self.root.update()
        if self.ctl.session and self.ctl.session.game["captures"]:
            self.ctl.finish_session()
        else:
            self.ctl.stop_watch()
        self.root.destroy()

    def _ask_send(self, folder):
        """Fin de partie : accord séparé pour ENVOYER le fichier anonyme. Trois choix de même poids."""
        try:
            f = Path(folder) / "contribution.json"
            info = json.loads(f.read_text(encoding="utf-8"))
            ko = max(1, (Path(folder) / "contribution.json.gz").stat().st_size // 1024)
            detail = f"{len(info.get('squads', []))} unités · {len(info.get('caps', []))} captures · {ko} Ko"
        except Exception:
            f, detail = None, ""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=12)
        win.title("Envoyer cette partie ? (facultatif)")
        win.attributes("-topmost", True)

        def choose(v):
            if v in ("une", "toutes"):
                if v == "toutes":
                    self.cfg["envoi"] = "oui"
                    self.save_cfg(self.cfg)
                    if hasattr(self, "v_envoi"):
                        self.v_envoi.set(True)
                self._safe(self.ctl.send_game, folder)
            else:
                self.cfg["envoi"] = "non"
                self.save_cfg(self.cfg)
                if hasattr(self, "v_envoi"):
                    self.v_envoi.set(False)
            win.destroy()
        txt = ("Le fichier anonyme de ta partie est prêt (" + detail + ").\n"
               "Veux-tu l'envoyer pour les statistiques de la communauté ? Il ne contient aucun pseudo, aucune capture\n"
               "d'écran, rien sur ton PC. Tu peux l'ouvrir avant de décider. Un identifiant au hasard permet\n"
               "de faire supprimer la partie sur demande. Détails : CONFIDENTIALITE.md.")
        tk.Label(win, text=txt, bg=BG, fg=INK, font=FONT, justify="left").pack(anchor="w", pady=(0, 10))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x")
        self._btn(row, "Envoyer cette partie", lambda: choose("une"), kind="primary").pack(side="left", ipadx=6)
        self._btn(row, "Envoyer celle-ci et les suivantes", lambda: choose("toutes"), kind="primary").pack(side="left", padx=8, ipadx=6)
        self._btn(row, "Ne pas envoyer", lambda: choose("non"), kind="primary").pack(side="left", ipadx=6)
        if f:
            def open_file():
                try:
                    if sys.platform == "win32":
                        os.startfile(str(f))
                    else:
                        webbrowser.open(f.resolve().as_uri())
                except Exception:
                    pass
            self._btn(win, "Voir le fichier", open_file).pack(anchor="w", pady=(8, 0))
        win.protocol("WM_DELETE_WINDOW", lambda: win.destroy())  # fermer = pas d'envoi, on redemandera à la prochaine partie

    def _consent_dialog(self):
        """Premier lancement : demande séparée, jamais liée à l'usage du logiciel. Aucun choix n'est mis en avant ni présélectionné."""
        win = tk.Toplevel(self.root, bg=BG, padx=16, pady=12)
        win.title("Statistiques anonymes (facultatif)")
        win.attributes("-topmost", True)
        win.transient(self.root)

        def choose(v):
            self.cfg["contribution"] = v
            self.save_cfg(self.cfg)
            if hasattr(self, "v_contrib"):
                self.v_contrib.set(v == "oui")
            win.destroy()
        txt = ("Ton aide permet de savoir ce qui se joue vraiment sur TTS et d'améliorer les outils pour tous.\n"
               "Servo-Skull fonctionne exactement pareil que tu acceptes ou non.\n\n"
               "Si tu acceptes, à la fin de chaque partie, un petit fichier ANONYME est créé dans le dossier de la\n"
               "partie : composition des armées, mission, plan de table, positions et scores.\n"
               "Les pseudos sont remplacés par « Joueur A » et « Joueur B » ; aucune capture d'écran, aucun nom\n"
               "de dossier, aucun identifiant de ton PC. Tu peux ouvrir le fichier (contribution.json) pour le lire.\n\n"
               "RIEN n'est envoyé automatiquement. Si un envoi existe un jour, il te sera proposé à part,\n"
               "avec ton accord avant chaque partage. Tu peux changer d'avis à tout moment avec la case à cocher\n"
               "de l'écran de partie. Détails : CONFIDENTIALITE.md.")
        tk.Label(win, text=txt, bg=BG, fg=INK, font=FONT, justify="left").pack(anchor="w", pady=(0, 10))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x")
        # les deux choix ont le même poids visuel (consentement libre : refuser est aussi simple qu'accepter)
        self._btn(row, "J'accepte", lambda: choose("oui"), kind="primary").pack(side="left", ipadx=8)
        self._btn(row, "Non merci", lambda: choose("non"), kind="primary").pack(side="left", padx=8, ipadx=8)
        win.protocol("WM_DELETE_WINDOW", lambda: choose("non"))

    def run(self):
        if self.cfg.get("contribution") not in ("oui", "non"):
            self.root.after(600, self._consent_dialog)
        self.root.mainloop()
