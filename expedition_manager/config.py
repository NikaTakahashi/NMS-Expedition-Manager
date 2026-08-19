"""Persistent configuration and state for the application.

Per-user data (config.txt, state.json, backups and the personal
overrides.json) lives in the per-user *state directory* (see state_dir()),
keeping the program directory free of machine-specific files. Files left
in the program directory by older versions are migrated on first run.

The configuration is a plain-text `config.txt`: if it does not exist it is
created automatically with default values (migrating a legacy config.json
if present); if it exists, it is never touched at startup and the user may
edit it by hand.
"""
import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "expedition-manager"
NMS_APP_ID = 275850  # Steam AppID of No Man's Sky

# Program root (directory containing the expedition_manager package)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Standard Steam location (the 'default' option in the interactive menu)
DEFAULT_PREFIX = str(
    Path.home() / ".steam" / "steam" / "steamapps" / "compatdata" / str(NMS_APP_ID) / "pfx"
)

# ---------------------------------------------------------------------------
# Per-user data locations (all under state_dir(); defined before the module
# constants that need them)
# ---------------------------------------------------------------------------

def state_dir() -> Path:
    r"""Per-user state directory (config, state, backups, personal data).

    Windows: %LOCALAPPDATA%\expedition-manager
    macOS:   ~/Library/Application Support/expedition-manager
             (falls back to the legacy XDG location if it already holds state)
    Linux:   $XDG_DATA_HOME/expedition-manager (~/.local/share/...)
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        legacy = (Path(os.environ.get("XDG_DATA_HOME",
                                      str(Path.home() / ".local" / "share")))
                  / APP_NAME)
        if not (base / APP_NAME).exists() and legacy.exists():
            base = legacy.parent
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / APP_NAME


# Persistent, user-editable configuration file (in the state directory)
CONFIG_FILE = state_dir() / "config.txt"

# Optional personal overrides, applied last during sync (in the state dir)
USER_OVERRIDES_FILE = state_dir() / "overrides.json"


def migrate_user_data() -> None:
    """Move per-user files left in the program directory into state_dir().

    Older versions stored config.txt / overrides.json next to the source
    code. They are per-user data and now live with the rest of the user
    state. Idempotent: a file is only moved when it still sits in the
    program directory and no copy exists in the state directory yet.
    """
    d = state_dir()
    for name in ("config.txt", "overrides.json"):
        old = PROJECT_ROOT / name
        new = d / name
        try:
            if old.exists() and not new.exists():
                d.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old), str(new))
        except OSError:
            pass

# Configuration keys, in file-writing order
CONFIG_KEYS = ("proton_prefix", "library_path")

CONFIG_COMMENTS = {
    "proton_prefix": "Path to the NMS Proton prefix (used to locate the cache on Linux)",
    "library_path": "Path of the expedition library",
}

DEFAULT_CONFIG = {
    # Empty by default: standard Steam locations are probed automatically.
    "proton_prefix": "",
    # The library lives inside the program directory by default.
    "library_path": str(PROJECT_ROOT / "ExpeditionManagerLibrary"),
}


# ---------------- config.txt ----------------

def _legacy_config_path() -> Path:
    """Legacy config.json location (XDG), kept for a one-time migration."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / APP_NAME / "config.json"


def _legacy_values() -> dict:
    """Values from the legacy config.json, if it exists (migration to config.txt)."""
    path = _legacy_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: v for k, v in data.items() if k in CONFIG_KEYS and isinstance(v, str)}


def _render_config(values: dict) -> str:
    """Render config.txt text from a key->value dictionary."""
    lines = [
        "# ============================================================",
        "#  Expedition Manager - configuration",
        "#  Edit the values and save the file; the program reads it at startup.",
        "#  (In the interactive menu, 'default' applies the standard Steam path.)",
        "# ============================================================",
        "",
    ]
    for key in CONFIG_KEYS:
        lines.append(f"# {CONFIG_COMMENTS[key]}")
        lines.append(f"{key}={values.get(key, '')}")
        lines.append("")
    return "\n".join(lines)


def _parse_config(text: str) -> dict:
    """Read key=value pairs from config.txt (comments and blank lines ignored)."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in CONFIG_KEYS:
            values[key] = value.strip().strip('"').strip("'")
    return values


def ensure_config_file() -> None:
    """Create config.txt with default values if it does not exist.

    An existing file is never overwritten: if present, the user owns it.
    Files left in the program directory by older versions are migrated
    into the state directory first.
    """
    migrate_user_data()
    if CONFIG_FILE.exists():
        return
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    values = dict(DEFAULT_CONFIG)
    values.update(_legacy_values())  # migrate the legacy config.json, if any
    CONFIG_FILE.write_text(_render_config(values), encoding="utf-8")
    try:
        CONFIG_FILE.chmod(0o644)  # readable/writable by the user
    except OSError:
        pass


def load_config() -> dict:
    """Return the configuration read from config.txt (defaults if missing)."""
    ensure_config_file()
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(_parse_config(CONFIG_FILE.read_text(encoding="utf-8")))
    except OSError:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    """Save the configuration to config.txt.

    The file is rewritten but keys the user added manually are preserved
    (appended at the end of the file).
    """
    existing = {}
    if CONFIG_FILE.exists():
        try:
            for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, _, v = s.partition("=")
                    existing[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass

    merged = dict(DEFAULT_CONFIG)
    merged.update(existing)
    merged.update({k: v for k, v in cfg.items() if isinstance(v, str)})

    text = _render_config(merged)
    extra = {k: v for k, v in merged.items() if k not in CONFIG_KEYS}
    if extra:
        text += "# Keys added by the user\n"
        for k, v in extra.items():
            text += f"{k}={v}\n"
    CONFIG_FILE.write_text(text, encoding="utf-8")


# ---------------- state.json ----------------

def load_state() -> dict:
    path = state_dir() / "state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
