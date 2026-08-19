# 6 · The GUI

The GUI is a **Qt6** app. It uses **PyQt6** when available (Arch's
`python-pyqt6` is reused directly through the venv) and **PySide6**
otherwise (`run.sh` installs it into the venv automatically) — both bindings
share the same Qt6 API, and the code (`gui_qt.py`) works with either. On
**Linux it runs on native Wayland (xdg-shell)**: the launchers set
`QT_QPA_PLATFORM=wayland` on Wayland sessions (and `gui_qt.launch()` enforces
it as a second line of defence), so the window is a real `xdg-shell` client
with **no X11 involved**. On Windows/macOS it uses the native platform
integration. A tkinter fallback (`gui.py`, X11) is kept for systems where no
Qt6 binding can be installed at all.

It has **three tabs** plus a log panel and a status bar, and it shares 100%
of its logic with the CLI (same `sync`, `installer`, `customize`, `config`
modules), so nothing the GUI can do is missing from the CLI, and vice-versa.

## Window layout

```
┌────────────────────────────────────────────────────────┐
│  [ Library | Install | Settings ]                      │
├────────────────────────────────────────────────────────┤
│                                                        │
│                        ( tab body )                    │
│                                                        │
├────────────────────────────────────────────────────────┤
│  Sync strip  [ Sync all ] [ Force resync ]  progress  │
├────────────────────────────────────────────────────────┤
│  Log panel (colorized: info / ok / error)             │
├────────────────────────────────────────────────────────┤
│  Status bar (short one-line state)                    │
└────────────────────────────────────────────────────────┘
```

- **Library / Install** scroll vertically if the window is too short (the
  Install tab, with the 67-row customization form, is the tall one).
- The **log panel** mirrors everything the CLI would print, color-coded.
- The **status bar** shows the last high-level state.

## The tabs

### Library
- A **table** of all 22 expeditions: id, name, available modes
  (Original / Redux, with Redux dimmed when absent, e.g. e21/e22), and a
  **download status** per difficulty (e.g. `D ✔ E ✔ H ✔`).
- Click a row to inspect; the view is read-only (downloading happens on the
  Sync strip, so the Library tab never blocks the UI).
- It is **not** a scrollable-canvas tab: the table (a `Treeview`) has its own
  internal scrollbar, so the tab body doesn't double-scroll.

### Install
Top to bottom:
1. **Expedition** dropdown (`eNN — Name`).
2. **Version** — Original / Redux (the Redux button is disabled when the
   expedition has no Redux).
3. **Difficulty** — Defaults / Easy / Hardcore. Changing any of (1–3)
   re-derives the *Downloaded ✓ / not downloaded* status line **and** reloads
   the customization form with the selected difficulty's preset.
4. **Customization** — the 67-parameter form (see
   [Customization](05-customization.md)).
5. The **download status line**: green *Downloaded ✓* if the exact
   `(exp, mode, difficulty)` file is in the library, otherwise a grey hint and
   the primary button becomes **Download first** (fetch just that combination)
   before it turns into **Install**. *Customized* files don't need this (they
   are generated from the cached sources).
6. **NMS cache folder** — auto-detected and pre-filled; **Re-detect** rescans;
   a red line warns if none is found (with the platform-specific remedy).
7. **Current installation** — what's installed, the target cache, the backup
   path, and (if applicable) how many customization values are saved.
8. **Install** / **Uninstall** — both ask for confirmation; the install dialog
   restates the ⚠ *put Steam in offline mode* warning.

### Settings
- **Proton prefix** (Linux only) — the prefix path used to find the cache; on
  Windows/macOS this row is replaced by a grey note showing the native game
  path (there is no Proton there).
- **Library path** — where the 126-file library lives (defaults to the
  program directory).
- **Restore defaults** button.
- Saving writes `config.txt` (see [Configuration & Data](09-config-and-data.md)).

## Threading model (why the UI never freezes)

The GUI thread is single-threaded, but network downloads, file generation,
and disk copies are slow. The GUI uses a strict **worker-thread + queue**
pattern:

```
main thread (Qt)                worker thread (background)
─────────────────               ─────────────────────────
  user clicks Install  ──────▶  runs sync / generate / install
  QTimer(100 ms) poller ◀─────  q.put(("log", level, msg))
  renders widgets from the queue
```

Rules that keep it safe:
- **Only the GUI thread touches widgets.** The worker never calls any Qt API;
  it only pushes messages onto a `queue.Queue`.
- **One worker at a time.** A second action while one is running is ignored
  (the busy state is surfaced in the log).
- **Polling, not callbacks.** A `QTimer` started at 100 ms drains the queue;
  the timer is **stopped in `closeEvent`** so closing the window can't leave
  a dangling callback. (Workers are daemon threads: they die with the
  process.)
- **Long jobs report progress** (sync) through the same queue, updating the
  progress bar without blocking.

## Startup behavior

On launch the app:
1. Loads the catalog and the current library status (fast, local).
2. **Auto-detects NMS cache folders** (a quick local scan) and pre-fills the
   Install tab's cache combo.
3. If an expedition is currently installed, **pre-selects** it (expedition,
   version, difficulty) and **restores the saved customization values** into
   the form.
4. Uses the platform's native widget style (Breeze/Windows/macOS) and loads
   the window icon from `assets/ExpeditionManager.ico`.
5. Starts the queue poller and installs the clean-close handler.

## Platform-awareness in the GUI

`gui_qt.py` computes `IS_LINUX` / `IS_WINDOWS` / `IS_MACOS` once and uses them
only for **presentation** (which settings row to show, which warning text,
icon/theme fallbacks) and for selecting the **Wayland** platform plugin on
Wayland sessions. All *logic* is shared. See [Platforms](08-platforms.md).
