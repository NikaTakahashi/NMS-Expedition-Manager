#!/usr/bin/env bash
# Expedition Manager launcher: creates the venv if missing, installs the
# dependencies, and re-runs the program inside the venv.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 was not found on the system." >&2
    exit 1
fi

# The venv is created with --system-site-packages so that, when the OS
# already ships a Qt6 binding (e.g. `python-pyqt6` on Arch), the GUI can use
# it without downloading a second copy. Packages listed in requirements.txt
# are still installed into the venv and always take import priority.
have_sys_site() {
    grep -q "^include-system-site-packages = true" .venv/pyvenv.cfg 2>/dev/null
}

# 1) Create (or migrate) the venv
if [ ! -f .venv/bin/python ]; then
    echo "Creating virtual environment (.venv)..."
    python3 -m venv --system-site-packages .venv
elif ! have_sys_site; then
    echo "Migrating .venv to --system-site-packages (enables the Qt6 GUI)..."
    rm -rf .venv
    python3 -m venv --system-site-packages .venv
fi

# 2) Install dependencies if missing or requirements.txt changed
REQ_HASH=$(cksum requirements.txt | awk '{print $1}')
if [ ! -f .venv/.deps_hash ] || [ "$(cat .venv/.deps_hash 2>/dev/null)" != "$REQ_HASH" ]; then
    echo "Installing dependencies..."
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install --quiet -r requirements.txt
    echo "$REQ_HASH" > .venv/.deps_hash
fi

# 3) GUI backend check: make sure a Qt6 binding (PyQt6/PySide6) is
#    importable. With --system-site-packages an OS-provided PyQt6 is used
#    as-is; otherwise install PySide6 (LGPL, wheels for all platforms).
if [ "$1" = "gui" ]; then
    if ! .venv/bin/python -c "import PyQt6" 2>/dev/null \
       && ! .venv/bin/python -c "import PySide6" 2>/dev/null; then
        echo "No Qt6 binding found. Installing PySide6 into the venv..."
        .venv/bin/pip install --quiet PySide6
    fi
fi

# 4) GUI runs on native Wayland (xdg-shell) when on a Wayland session;
#    never force X11.
if [ -z "${QT_QPA_PLATFORM:-}" ] && \
   { [ -n "${WAYLAND_DISPLAY:-}" ] || [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; }; then
    export QT_QPA_PLATFORM=wayland
fi

# 5) Re-run inside the venv, passing the arguments through unchanged
exec .venv/bin/python run.py "$@"
