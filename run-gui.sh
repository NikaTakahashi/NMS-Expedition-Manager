#!/usr/bin/env bash
# Expedition Manager — GUI launcher.
# Thin wrapper over run.sh: it reuses the venv bootstrap (venv creation,
# dependency install) and simply adds the `gui` subcommand.
set -e
cd "$(dirname "$0")"
exec ./run.sh gui
