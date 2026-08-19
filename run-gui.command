#!/usr/bin/env bash
# Expedition Manager — GUI launcher for macOS (double-click me in Finder).
# Thin wrapper over run.sh: reuses the venv bootstrap and adds the "gui"
# subcommand.
cd "$(dirname "$0")"
exec ./run.sh gui
