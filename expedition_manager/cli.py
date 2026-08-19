"""Command-line interface and interactive menu."""
import argparse
import sys
from pathlib import Path

from . import installer, sync as syncmod
from .catalog import build_catalog
from .config import DEFAULT_PREFIX, load_config, load_state, save_config
from .sources import Sources


try:  # only needed to give an exact hint when the GUI cannot start
    import tkinter  # noqa: F401
    _HAS_TK = True
except ImportError:  # pragma: no cover
    _HAS_TK = False


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _catalog():
    src = Sources(_data_dir() / "sources")
    return build_catalog(src.fetch("_data/expeditions.yml"))


# ---------------- commands ----------------

def cmd_sync(args) -> int:
    downloaded, skipped = syncmod.sync(force=args.force, only_exp=args.exp)
    print(f"\nSynchronization complete: {downloaded} downloaded/updated, "
          f"{skipped} unchanged.")
    return 0


def cmd_gui(args) -> int:
    """Launch the graphical interface.

    Backend priority:
      1. Qt6 (PyQt6 or PySide6)  -> **native Wayland (xdg-shell)** on Linux,
         no X11 involved; native integration on Windows/macOS.
      2. tkinter (stdlib)        -> X11 / XWayland fallback.

    On a Wayland session the Qt6 backend selects the ``wayland`` platform
    plugin automatically (see gui_qt.launch), so no X server is used.
    """
    # --- Backend 1: Qt6 (preferred; native Wayland on Linux) ---
    try:
        from . import gui_qt
    except ImportError as e:
        gui_qt, qt_err = None, e
    else:
        try:
            return gui_qt.launch()
        except Exception as e:
            print(f"Warning: the Qt6 GUI could not start ({e}); "
                  f"falling back to tkinter (X11).")
            # fall through to the tkinter backend below

    # --- Backend 2: tkinter (stdlib, X11/XWayland) ---
    if gui_qt is None:
        print(f"Note: Qt6 (PyQt6/PySide6) is not available ({qt_err}); "
              f"using the tkinter GUI (X11).")
    if not _HAS_TK:
        print("Graphical interface is unavailable: neither Qt6 (PyQt6/PySide6) "
              "nor tkinter is installed.")
        print("  - Install Qt6 bindings (recommended, native Wayland):")
        print("      Arch:            sudo pacman -S python-pyqt6")
        print("      Debian/Ubuntu:   sudo apt install python3-pyqt6")
        print("      any (pip):       pip install PySide6")
        print("  - Or tkinter (X11):  sudo pacman -S tcl tk   /   "
              "sudo apt install python3-tk")
        print("You can still use the command line: "
              "./run.sh <sync|install|uninstall|list|config>")
        return 1
    from .gui import launch
    return launch()


def cmd_install(args) -> int:
    catalog = _catalog()

    exp_id = args.exp
    mode = args.mode
    difficulty = args.difficulty

    if not exp_id:
        print("Available expeditions:")
        for i, e in enumerate(catalog, 1):
            reduxes = [v for v in e.versions if v.redux]
            tag = f" (redux up to {reduxes[-1].id})" if reduxes else ""
            print(f"  {i:2d}) {e.name}{tag}")
        raw = input("Expedition number: ").strip()
        if not raw.isdigit() or not 1 <= int(raw) <= len(catalog):
            print("Invalid selection.")
            return 1
        exp_id = catalog[int(raw) - 1].id

    if not mode:
        raw = input("Version [o]riginal / [r]edx (default o): ").strip().lower()
        mode = "Redux" if raw.startswith("r") else "Originals"

    if not difficulty:
        raw = input("Difficulty [d]efault / [e]asy / [h]ardcore (default d): ").strip().lower()
        if raw.startswith("e"):
            difficulty = "Easy"
        elif raw.startswith("h"):
            difficulty = "Hardcore"
        else:
            difficulty = "Defaults"

    # Validate that the combination exists
    exp = next((e for e in catalog if e.id == exp_id), None)
    if not exp:
        print(f"Expedition {exp_id} does not exist.")
        return 1
    if mode == "Redux" and not exp.latest_redux:
        print(f"{exp.name} has no redux version.")
        return 1

    source_file = None
    custom = None
    if getattr(args, "custom", None):
        from . import customize
        try:
            user = customize.parse_custom_spec(args.custom)
        except ValueError as e:
            print(f"Error: {e}")
            return 1
        flat = dict(customize.load_preset(difficulty))
        flat.update(user)
        groups, prop_map = customize.load_spec()
        errs = customize.validate(flat, prop_map, customize.spec_props(groups))
        if errs:
            for err in errs:
                print(f"  ✗ {err}")
            return 1
        src_file, custom = customize.install_source_from_flat(
            exp_id, mode, difficulty, flat)
        source_file = src_file
        if source_file:
            print(f"  (generated custom file: {source_file})")

    return 0 if installer.install(exp_id, mode, difficulty,
                                  source_file=source_file, custom=custom) else 1


def cmd_uninstall(args) -> int:
    installer.uninstall()
    return 0


def cmd_list(args) -> int:
    cfg = load_config()
    lib = Path(cfg["library_path"]).expanduser()

    print(f"Library: {lib}")
    if not lib.exists():
        print("  (empty - run './run.sh sync' to download)")
    else:
        for mode in ("Originals", "Redux"):
            for difficulty in ("Defaults", "Easy", "Hardcore"):
                base = lib / mode / difficulty
                if not base.exists():
                    continue
                entries = sorted(base.iterdir())
                print(f"\n  {mode}/{difficulty}: {len(entries)} expeditions")
                for e in entries:
                    has_md = (e / "INSTRUCTIONS.md").exists()
                    print(f"    - {e.name}{'  [md OK]' if has_md else '  [NO MD!]'}")

    state = load_state()
    inst = state.get("installed")
    print("\nCurrent installation:")
    if inst:
        print(f"  {inst['exp_id']} ({inst['mode']}/{inst['difficulty']}) -> {state.get('cache_dir')}")
    else:
        print("  (none)")

    print("\nConfig:")
    for k, v in cfg.items():
        print(f"  {k} = {v!r}")
    return 0


def cmd_config(args) -> int:
    cfg = load_config()

    while True:
        print("\nCurrent configuration:")
        for k, v in cfg.items():
            print(f"  {k} = {v!r}")
        print("  1) proton_prefix   (or 'default' for the standard path)")
        print("  2) library_path")
        print("  0) Done")
        try:
            choice = input("Option > ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0

        if choice == "1":
            raw = input(f"Proton prefix path (default: {DEFAULT_PREFIX}): ").strip()
            cfg["proton_prefix"] = "" if not raw else (
                DEFAULT_PREFIX if raw.lower().startswith("d") else raw)
            save_config(cfg)
        elif choice == "2":
            raw = input("Library path: ").strip()
            if raw:
                cfg["library_path"] = raw
                save_config(cfg)
        elif choice == "0":
            return 0


# ---------------- interactive menu ----------------

MENU = """
+====================================+
|           Expedition Manager       |
+====================================+
| 1) Synchronize expeditions         |
| 2) Install expedition              |
| 3) Uninstall expedition            |
| 4) List                            |
| 5) Configure                       |
| 6) Open graphical interface        |
| 0) Quit                            |
+====================================+"""


def main_menu() -> int:
    while True:
        print(MENU)
        try:
            choice = input("Option > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice == "1":
            cmd_sync(argparse.Namespace(force=False, exp=None))
        elif choice == "2":
            cmd_install(argparse.Namespace(exp=None, mode=None, difficulty=None))
        elif choice == "3":
            cmd_uninstall(argparse.Namespace())
        elif choice == "4":
            cmd_list(argparse.Namespace())
        elif choice == "5":
            cmd_config(argparse.Namespace())
        elif choice == "6":
            cmd_gui(argparse.Namespace())
        elif choice == "0":
            return 0
        else:
            print("Invalid option.")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # No arguments -> interactive menu
    if not argv:
        return main_menu()

    parser = argparse.ArgumentParser(
        prog="expedition-manager",
        description="Offline expedition manager for No Man's Sky.",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_sync = sub.add_parser("sync", help="Download/synchronize the expedition library")
    p_sync.add_argument("--force", action="store_true", help="Re-download even if present")
    p_sync.add_argument("--exp", help="Only one expedition (e.g. e01)")

    p_install = sub.add_parser("install", help="Install an expedition into the NMS cache")
    p_install.add_argument("--exp", help="Expedition ID (e.g. e01)")
    p_install.add_argument("--mode", choices=["original", "redux"])
    p_install.add_argument("--difficulty", choices=["default", "easy", "hardcore"])
    p_install.add_argument(
        "--custom",
        help="Custom parameters, e.g. 'CarnageMode=true,StartingSuitSlots=24' "
             "(the website's form; on top of the selected difficulty)")

    sub.add_parser("uninstall", help="Restore the original cache")
    sub.add_parser("list", help="Show library, installation and config")

    sub.add_parser("config", help="Show/edit the configuration")
    sub.add_parser("gui", help=("Open the graphical interface (Qt6, "
                                 "native Wayland on Linux)"))

    args = parser.parse_args(argv)

    if args.cmd == "gui":
        return cmd_gui(args)
    if args.cmd == "sync":
        return cmd_sync(args)
    if args.cmd == "install":
        # Normalize CLI values to folder names
        if args.mode:
            args.mode = "Redux" if args.mode == "redux" else "Originals"
        if args.difficulty:
            args.difficulty = {"easy": "Easy", "hardcore": "Hardcore"}.get(
                args.difficulty, "Defaults")
        return cmd_install(args)
    if args.cmd == "uninstall":
        return cmd_uninstall(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "config":
        return cmd_config(args)

    parser.print_help()
    return 0
