"""Installation and uninstallation of expeditions into the NMS cache."""
import json
import os
import platform
import re
import shutil
from datetime import datetime
from pathlib import Path

from .config import load_config, load_state, save_state, state_dir

# The season the library was generated for. The game names its cache file
# SEASON_DATA_CACHE_S<N>.json and <N> increases with every season update;
# install/uninstall resolve the *current* season dynamically (see
# season_files / current_cache_file), so a future S23+ needs no code change.
CACHE_FILE = "SEASON_DATA_CACHE_S22.JSON"
SEASON_FILE_RE = re.compile(r"^season_data_cache_s(\d+)\.json$", re.IGNORECASE)


def season_files(cache_dir: Path) -> dict:
    """All SEASON_DATA_CACHE_S<N>.json files in cache_dir, by season number.

    Case-insensitive (the Proton prefix may use a different case on a
    case-sensitive filesystem)."""
    out = {}
    try:
        for f in cache_dir.iterdir():
            m = SEASON_FILE_RE.match(f.name)
            if f.is_file() and m:
                out[int(m.group(1))] = f
    except OSError:
        pass
    return out


def current_cache_file(cache_dir: Path) -> Path:
    """The season file the game currently reads.

    Season numbers only increase, so the highest-numbered file present is
    the current one (after a season bump the old file stays on disk but is
    no longer read by the game). Falls back to the historical S22 name in
    any case, then to the default path.
    """
    files = season_files(cache_dir)
    if files:
        return files[max(files)]
    direct = cache_dir / CACHE_FILE
    try:
        for f in cache_dir.iterdir():
            if f.is_file() and f.name.lower() == CACHE_FILE.lower():
                return f
    except OSError:
        pass
    return direct


def find_nms_cache_dirs() -> list:
    """Find NMS cache folders according to the OS. Returns a list of Paths."""
    found = []
    system = platform.system()

    if system == "Windows":
        appdata = Path(os.environ.get("APPDATA", ""))
        nms = appdata / "HelloGames" / "NMS"
        if nms.exists():
            for cache in sorted(nms.glob("*/cache")):
                found.append(cache)
    elif system == "Darwin":
        c = Path.home() / "Library" / "Application Support" / "HelloGames" / "NMS" / "cache"
        if c.exists():
            found.append(c)
    else:  # Linux (Proton): the cache lives inside the prefix
        cfg = load_config()
        candidates = []
        p = (cfg.get("proton_prefix") or "").strip()
        if p:
            candidates.append(Path(p).expanduser())
        for base_home in (Path.home() / ".steam" / "steam", Path.home() / ".local" / "share" / "Steam"):
            candidates.append(base_home / "steamapps" / "compatdata" / "275850" / "pfx")

        seen = set()
        for prefix in candidates:
            if not prefix.exists() or str(prefix) in seen:
                continue
            seen.add(str(prefix))
            # On Linux the path is lowercase; on Steam Deck it may use capitals
            for users_dir in ("users/steamuser", "Users/SteamUser"):
                base = (prefix / "drive_c" / users_dir / "AppData" / "Roaming"
                        / "HelloGames" / "NMS")
                if not base.exists():
                    continue
                for cache in sorted(base.glob("*/cache")):
                    found.append(cache)
    return found


def _resolve_cache_file(cache_dir: Path) -> Path:
    """The expedition file inside cache_dir, resolved case-insensitively.

    The game is started through Proton (case-insensitive by default), but on
    case-sensitive Linux filesystems it may use a different case than the
    official download name — matching any case so backups/restores always
    target the file the game actually uses.
    """
    direct = cache_dir / CACHE_FILE
    if direct.exists():
        return direct
    try:
        for f in cache_dir.iterdir():
            if f.is_file() and f.name.lower() == CACHE_FILE.lower():
                return f
    except OSError:
        pass
    return direct


def _source_file(exp_id: str, mode: str, difficulty: str, lib: Path):
    """Locate the downloaded JSON in the library for that combination."""
    manifest_path = lib / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    entry = manifest.get(f"{exp_id}/{mode}/{difficulty}")
    if not entry:
        return None
    folder = lib / mode / difficulty / re.sub(r"[^A-Za-z0-9]+", "_", entry["name"]).strip("_")
    f = folder / CACHE_FILE
    return f if f.exists() else None


def install(exp_id: str, mode: str, difficulty: str, interactive: bool = True,
            cache_dir: str = None, source_file: str = None,
            custom: dict = None) -> bool:
    """Install the downloaded expedition into the NMS cache.

    `cache_dir` lets the caller (e.g. the GUI) pick the cache folder
    explicitly; when None, auto-detection and interactive selection apply.
    `source_file` overrides the library file (custom-generated file).
    `custom` (flat prop->value dict) is recorded in the state so the GUI
    can re-populate its customization form.
    """
    cfg = load_config()
    lib = Path(cfg["library_path"]).expanduser()

    if source_file:
        source = Path(source_file)
        if not source.exists():
            print(f"Error: custom file not found: {source}")
            return False
    else:
        source = _source_file(exp_id, mode, difficulty, lib)
        if not source:
            print(f"Error: {exp_id} ({mode}/{difficulty}) is not downloaded. "
                  f"Run first: ./run.sh sync")
            return False

    if cache_dir:
        caches = [Path(cache_dir).expanduser()]
    else:
        caches = find_nms_cache_dirs()
    if not caches:
        system = platform.system()
        print("No NMS cache folder was found.")
        if system == "Linux":
            print("  - Run the game once with Proton to create the prefix, and set")
            print("    the prefix path with './run.sh config'.")
        else:
            where = ("%APPDATA%\\HelloGames\\NMS" if system == "Windows"
                     else "~/Library/Application Support/HelloGames/NMS")
            print(f"  - Run the game once so it creates its data folder ({where}).")
        return False

    def _has_cache_file(c: Path) -> bool:
        return _resolve_cache_file(c).exists()

    if len(caches) > 1 and interactive:
        print("Several NMS cache folders were found:")
        for i, c in enumerate(caches):
            print(f"  {i}) {c}")
        cache = caches[0]
        while True:
            try:
                raw = input("Choose a folder (0 is the default): ").strip() or "0"
            except EOFError:
                break
            if raw.isdigit() and int(raw) < len(caches):
                cache = caches[int(raw)]
                break
    else:
        # Prefer the one that already contains the expedition file
        cache = next((c for c in caches if _has_cache_file(c)), caches[0])

    # Resolve the file the game CURRENTLY reads (highest season present).
    target = current_cache_file(cache)

    # Back up the original file before overwriting it
    backups = state_dir() / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # A season file from an older season is dead to the game once it moved
    # on: archive it (moved, not deleted) so the cache only keeps the live
    # season, as the user would do by hand.
    for n, f in sorted(season_files(cache).items()):
        if f != target:
            dest = backups / f"{f.name}_{ts}_archived"
            shutil.move(str(f), dest)
            print(f"Old season file archived: {f.name} -> {dest}")

    backup_path = None
    if target.exists():
        backup_path = backups / f"{target.name}_{ts}"
        shutil.copy2(target, backup_path)

    shutil.copy2(source, target)
    print(f"Expedition copied to: {target}")

    state = load_state()
    state["installed"] = {"exp_id": exp_id, "mode": mode, "difficulty": difficulty}
    if custom:
        state["installed"]["custom"] = {str(k): v for k, v in custom.items()}
    state["cache_dir"] = str(cache)
    state["target_cache"] = str(target)
    if backup_path:
        state["backup_cache"] = str(backup_path)

    save_state(state)

    print("\nInstallation complete. Start NMS in OFFLINE mode and play the expedition.")
    return True


def uninstall(interactive: bool = True) -> bool:
    """Restore the original cache."""
    state = load_state()
    if not state.get("installed"):
        print("No expedition is currently installed (empty state).")
        return True

    # 1) Restore the cache
    cache_dir = state.get("cache_dir")
    backup = state.get("backup_cache")
    target = state.get("target_cache") or (str(_resolve_cache_file(Path(cache_dir)))
                                           if cache_dir else "")
    if cache_dir:
        cache_dir = Path(cache_dir)
        target_path = Path(target)
        if cache_dir.exists():
            seasons = season_files(cache_dir)
            m = SEASON_FILE_RE.match(target_path.name)
            rec_season = int(m.group(1)) if m else None
            if target_path.exists():
                if backup and Path(backup).exists():
                    shutil.copy2(backup, target_path)
                    print(f"Original cache restored at {target_path}")
                else:
                    target_path.unlink()
                    print("Expedition file removed (there was no backup of the original).")
            elif (rec_season is not None and seasons
                  and max(seasons) > rec_season):
                # The game moved to a newer season: the recorded file is
                # already dead (the game no longer reads it), so there is
                # nothing to restore on the live S<N> file — it must not be
                # touched.
                print(f"Note: the game now uses S{max(seasons)}; the old "
                      f"S{rec_season} file is no longer read by the game, "
                      "nothing to restore.")
            elif backup and Path(backup).exists():
                shutil.copy2(backup, target_path)
                print(f"Original cache restored at {target_path} (recreated).")

    # 2) Clean up the installation state (backups are kept)
    for k in ("installed", "cache_dir", "backup_cache", "target_cache"):
        state.pop(k, None)
    save_state(state)

    print("Uninstallation complete.")
    return True
