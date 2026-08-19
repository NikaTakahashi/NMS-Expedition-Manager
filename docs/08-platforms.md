# 8 · Platforms

The program runs on **Windows, macOS, and Linux** with the same GUI and CLI.
All *logic* is platform-independent (pure `pathlib` + stdlib); only a few
**presentation** and **location** details differ per OS.

## Per-platform locations

| | **Windows** | **macOS** | **Linux** |
|---|---|---|---|
| **Game cache** | `%APPDATA%\HelloGames\NMS\*\cache` | `~/Library/Application Support/HelloGames/NMS/cache` | `<prefix>/drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS/*/cache` |
| **State dir** (`state.json`, `backups/`, `custom/`) | `%LOCALAPPDATA%\expedition-manager` | `~/Library/Application Support/expedition-manager` | `$XDG_DATA_HOME/expedition-manager` (~=`~/.local/share/…`) |
| **`config.txt`** | in the state dir | in the state dir | in the state dir |
| **Library** | program dir (default) | program dir (default) | program dir (default) |

Notes:

- **macOS state fallback:** if `~/Library/Application Support/expedition-manager`
  doesn't exist but a legacy `~/.local/share/expedition-manager` does, the
  legacy path is used (backward compatibility).
- **Only the library** stays in the *program directory* (it is generated
  there and gitignored). `config.txt`, the personal `overrides.json`, the
  state and the backups all go to the per-OS user-data (state) location, so
  the program directory holds nothing machine-specific.
- Older versions kept `config.txt` / `overrides.json` in the program
  directory; on the first run after upgrading they are **moved** into the
  state directory automatically.

## How the cache is found

`find_nms_cache_dirs()` branches on the OS:

- **Windows / macOS** — the game stores data natively (no Proton), so it
  probes the standard per-user data folder. Windows may yield **two** caches
  (a per-SteamID dir and a `DefaultUser` one); the installer offers a choice
  when several are found.
- **Linux** — NMS runs under **Proton**, so the cache lives *inside* the
  Wine prefix's fake Windows tree. The prefix comes from `proton_prefix` in
  `config.txt`, else the standard Steam locations are probed. The in-prefix
  path is **lowercase** on a normal install (and may use `Users/SteamUser`
  capitals on Steam Deck); the search handles both cases.

If none is found, the remedy is OS-specific (run the game once to create the
folder; on Linux also set the prefix).

## Launchers (and the "never touch pip" rule)

The user is never asked to run `pip`. Each launcher bootstraps a hidden
virtualenv (`.venv`) on first run:

- **`run.sh` / `run-gui.sh`** (Linux/macOS, bash) — the CLI and the GUI.
- **`run.command` / `run-gui.command`** (macOS) — double-clickable in Finder
  (opens a Terminal automatically).
- **`run.bat` / `run-gui.bat`** (Windows) — double-clickable in Explorer; the
  bootstrap hash check uses PowerShell's `Get-FileHash -Algorithm MD5` (no
  external tools). `.bat` files are saved with **CRLF** line endings.

`requirements.txt` stays minimal: **`requests`** and **`PyYAML`** only. The
GUI's Qt6 dependency is handled *separately* from the core deps:

- **Linux** — the venv is created with `--system-site-packages`, so an
  OS-provided Qt6 binding (e.g. Arch's `python-pyqt6`) is **reused as-is**,
  with no download. If no binding is visible, `run.sh` installs **PySide6**
  into the venv the first time the GUI is requested. On Wayland sessions the
  launcher also exports **`QT_QPA_PLATFORM=wayland`**, forcing the native
  `xdg-shell` client (no X11); `gui_qt.launch()` enforces the same as a
  second line of defence.
- **Windows / macOS** — the venv is isolated, so `run.bat` / `run.sh` install
  **PySide6** into the venv on the first GUI launch (one-time download;
  LGPL-licensed, official wheels for every platform).
- If no Qt6 binding can be used at all, the GUI falls back to **tkinter**
  (X11 on Linux; the Windows/macOS installers ship Tk by default).

## Desktop launchers (Linux) and the app icon

The repository deliberately **does not ship a `.desktop` file**: those are
machine-specific (hardcoded absolute paths), so they don't belong in a
shared repository. If you want a file-manager / app-menu launcher, create
your own `expedition-manager.desktop` (e.g. in
`~/.local/share/applications/`) pointing at `run-gui.sh` with a quoted
`Exec=`/`WorkingDirectory=` and `StartupWMClass=expedition-manager` (the Qt
app's app id, so the taskbar groups the windows under the right icon).

> The application icon is **`assets/ExpeditionManager.ico`** (a 256×256 MS
> icon; the logo used in the READMEs is `assets/Logo.jpeg`). Qt6 loads
> `.ico` natively on **every** platform, so the GUI window always carries
> the right icon. For the Linux file manager / app menu, register the icon
> PNGs in the **hicolor** theme
> (`~/.local/share/icons/hicolor/<size>/apps/expedition-manager.png`)
> — KDE ignores absolute local icon paths in `.desktop` files.

## Per-OS behavior differences (all cosmetic)

| Concern | Linux | Windows / macOS |
|---|---|---|
| Settings tab, *Proton prefix* row | shown (editable) | hidden; replaced by a grey note with the native game path |
| "No cache found" warning | "run the game once under Proton, set the prefix" | "run the game once so it creates its data folder" |
| GUI platform protocol | **Wayland (xdg-shell)** on Wayland sessions; X11 via the `xcb` plugin on Xorg | native Windows / macOS windowing |
| Window icon | `.ico` loaded by Qt + hicolor theme for the file manager | `.ico` loaded by Qt (all platforms) |

## Testing across platforms without the hardware

The non-Linux paths are exercised by *simulation* in the test suite: the
cache-discovery branches are driven with a fake `$HOME`/`APPDATA` and a fake
prefix, and a fake cache is installed/uninstalled end-to-end. On the real
machine, the Linux regression (real Proton prefix, real cache, byte-identical
restore) is what guarantees the shared logic still holds.
