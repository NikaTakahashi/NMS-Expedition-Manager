# 7 · The CLI

The command line has **two modes**:

- **Interactive menu** — run with *no* arguments (`./run.sh`).
- **Subcommands** — run with an argument (`./run.sh sync`, `./run.sh install …`).

Both wrap the same functions, so anything you can do in the menu you can do as
a one-liner, and vice-versa.

## Launching

Per-platform launchers (each auto-creates a virtualenv and installs
`requirements.txt` on first run — the user never touches pip):

| OS      | CLI                                  | GUI                                  |
|---------|--------------------------------------|--------------------------------------|
| Linux   | `./run.sh`                           | `./run.sh gui` or `./run-gui.sh`     |
| macOS   | `./run.sh` or double-click `run.command` | `./run.sh gui` or `run-gui.command` |
| Windows | double-click `run.bat` (or `run.bat` in a terminal) | double-click `run-gui.bat` |

## Interactive menu

```
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
+====================================+
Option >
```

Option **2** (install) is fully guided when run from the menu: it lists the
22 expeditions for you to pick a number, then asks

- **Version** `[o]riginal / [r]edx` (default `o`);
- **Difficulty** `[d]efault / [e]asy / [h]ardcore` (default `d`).

(From the menu you can't pass `--custom`; use the subcommand form for that.)

## Subcommands

### `sync`
```
./run.sh sync [--force] [--exp eNN]
```
- (no flags) — download/refresh whatever's missing or changed.
- `--force` — re-download all raw sources and rewrite all 126 files.
- `--exp eNN` — only that expedition's combinations.

Output ends with `Synchronization complete: N downloaded/updated, M unchanged.`

### `install`
```
./run.sh install [--exp eNN] [--mode original|redux]
                 [--difficulty default|easy|hardcore]
                 [--custom "Prop=Value,Prop2=Value2,…"]
```
- Any omitted of `--exp / --mode / --difficulty` is **asked interactively**
  (with the same `[o]riginal/[r]edx` and `[d]efault/[e]asy/[h]ardcore`
  prompts as the menu).
- `--mode` and `--difficulty` are lowercased here and normalized to the
  folder names (`Originals`/`Redux`, `Defaults`/`Easy`/`Hardcore`).
- `--custom` — the website's form, on the command line. Parsed and
  **validated** (unknown params / bad types / bad options → error + list of
  valid examples, exit 1, no files touched). See
  [Customization](05-customization.md).

Examples:
```
./run.sh install --exp e14 --mode original --difficulty hardcore
./run.sh install --exp e01 --difficulty easy --custom "CarnageMode=true,StartingSuitSlots=24"
./run.sh install                    # fully guided
```

### `uninstall`
```
./run.sh uninstall
```
Restores the original cache file from the last backup and clears the
installation state. Safe to run when nothing is installed (no-op).

### `list`
```
./run.sh list
```
Prints the library path, a per-`Mode/Difficulty` listing (with a marker for
each expedition that has its `INSTRUCTIONS.md`), the current installation, and
the active configuration.

### `config`
```
./run.sh config
```
Interactive editor for `config.txt`: shows the current values, then lets you
set `proton_prefix` (type `default` for the standard Steam path) or
`library_path`.

### `gui`
```
./run.sh gui
```
Opens the GUI. Backend priority:
1. **Qt6** (`gui_qt.py`, PyQt6 or PySide6) — native Wayland (xdg-shell) on
   Linux, no X11; on a Wayland session the launcher/`launch()` set
   `QT_QPA_PLATFORM=wayland`.
2. **tkinter** (`gui.py`) — X11/XWayland fallback, used only if no Qt6
   binding is importable.

If neither is available it prints the exact install hint for your distro
(`pacman -S python-pyqt6`, `apt install python3-pyqt6`, `pip install PySide6`,
or tkinter hints) and notes that the CLI still works. Both imports are lazy,
so headless machines never break the CLI.

## Exit codes

Commands return `0` on success and non-zero on failure (e.g. a failed install,
a validation error in `--custom`, an unknown expedition, or a missing combo).
This makes the CLI scriptable:

```bash
./run.sh sync || exit 1
./run.sh install --exp e05 --mode redux --difficulty easy
```

## Where the state comes from

The CLI reads/writes the same `state.json` and `config.txt` as the GUI
(see [Configuration & Data](09-config-and-data.md)), so the two interfaces are
interchangeable — install in the GUI, uninstall from the terminal, etc.
