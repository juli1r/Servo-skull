#!/usr/bin/env bash
# Servo-Skull — lanceur Linux.
# Première fois : prépare un environnement Python 3.14 privé (.venv) puis lance l'overlay.
# Les fois suivantes : lance directement.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
# pynput est installé sans ses dépendances : il réclame « evdev », à compiler (gcc), qui ne sert
# qu'au mode uinput. Servo-Skull utilise le mode X11 de pynput (python-xlib), pas besoin d'evdev.
REQS="pillow>=11 mss>=10 python-xlib six"
PYNPUT="pynput>=1.8"
STAMP="$VENV/.servo-skull-deps"

say() { printf '\033[1;33m[Servo-Skull]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[Servo-Skull]\033[0m %s\n' "$*" >&2; exit 1; }

has_tk() { "$1" -c 'import tkinter; tkinter.Tcl()' >/dev/null 2>&1; }

make_venv() {
    # 1) Un python3.14 du système, avec Tkinter
    if command -v python3.14 >/dev/null 2>&1 && has_tk python3.14; then
        say "Python 3.14 du système trouvé, création de l'environnement…"
        python3.14 -m venv "$VENV"
        "$PY" -m pip install -q --upgrade pip
        "$PY" -m pip install -q $REQS
        "$PY" -m pip install -q --no-deps "$PYNPUT"
    # 2) Sinon uv (télécharge un Python 3.14 autonome, Tkinter inclus, sans toucher au système)
    elif command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
        if command -v python3.14 >/dev/null 2>&1; then
            say "python3.14 est installé mais sans Tkinter (paquet python3.14-tk / python3-tkinter)."
            say "J'utilise le Python de uv à la place : ça marche, mais les polices de l'overlay seront moins lisses."
        fi
        UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
        say "Préparation de Python 3.14 avec uv (une seule fois, ~30 Mo)…"
        "$UV" python install 3.14
        "$UV" venv -q -p 3.14 --managed-python "$VENV"
        "$UV" pip install -q -p "$PY" $REQS
        "$UV" pip install -q -p "$PY" --no-deps "$PYNPUT"
    else
        die "Il faut Python 3.14 (avec Tkinter) ou l'outil « uv ».
   Le plus simple : installe uv puis relance ce script :
     curl -LsSf https://astral.sh/uv/install.sh | sh
   (ou : pipx install uv / sudo dnf install uv / sudo pacman -S uv)"
    fi
    echo "$REQS $PYNPUT" > "$STAMP"
}

if [ ! -x "$PY" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$REQS $PYNPUT" ]; then
    rm -rf "$VENV"
    make_venv
    say "Environnement prêt."
fi

[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] || die "Aucun affichage graphique détecté (DISPLAY / WAYLAND_DISPLAY)."

exec "$PY" "$ROOT/app/servo_skull_linux.py" "$@"
