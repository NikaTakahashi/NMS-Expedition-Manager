# 4 · Install & Uninstall

This is the part that touches the **game**. Everything here is designed so
that the only irreversible thing is *you choosing to play an expedition*;
the files themselves are always recoverable.

## The target: the live season file

The game reads its expedition from a single file in its per-user cache
folder, named **`SEASON_DATA_CACHE_S<N>.json`** where `<N>` is the current
season number (this library was generated for **S22**; the number only ever
goes up). The program never hard-codes which `<N>` is live — it detects it.

- `season_files(cache)` — lists every `SEASON_DATA_CACHE_S<N>.json` present
  (case-insensitive), keyed by `<N>`.
- `current_cache_file(cache)` — the file the game **currently reads**: the
  one with the **highest** `<N>` (seasons only increase, so the newest
  number wins). If none match, it falls back to the historical S22 name.

On Linux the file frequently lives in **lowercase**
(`season_data_cache_s22.json`) even though the program's canonical name is
uppercase; `_resolve_cache_file()` matches any case so backups/restores always
hit the file the game actually uses on case-sensitive filesystems.

## Where the cache is found (per platform)

`find_nms_cache_dirs()` probes the OS-specific locations (see
[Platforms](08-platforms.md) for the full table):

- **Windows:** `%APPDATA%\HelloGames\NMS\*\cache`
- **macOS:** `~/Library/Application Support/HelloGames/NMS/cache`
- **Linux:** `<proton_prefix>/drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS/*/cache`
  (the prefix comes from `config.txt` or the standard Steam locations)

If **several** cache folders are found and you're in interactive mode, you're
asked to pick one. If none is found, you're told to run the game once (which
creates the folder) and, on Linux, to set the prefix.

## Install — step by step

`installer.install(exp_id, mode, difficulty, …)`:

1. **Resolve the source file.** Normally the library file for
   `(exp_id, mode, difficulty)` via the manifest. If a `source_file` is
   passed (the customization flow), that file is used instead.
2. **Resolve the target** live season file in the chosen cache.
3. **Archive old-season files.** Any `SEASON_DATA_CACHE_S<N>.json` that is
   *not* the current one is **moved** (not deleted) to the backups folder,
   suffixed `_archived`. This keeps the cache as clean as a hand-cleanup,
   without losing anything.
4. **Back up the current file.** If the live file exists, it's copied to
   `backups/<name>_<timestamp>`.
5. **Copy the source in** as the live file.
6. **Record state** in `state.json`: which expedition/mode/difficulty is
   installed, the cache dir, the target file, and the backup path.

The timestamped backup means *repeatedly* installing different expeditions
never destroys an earlier original: every install leaves a dated copy.

## Uninstall — restore

`installer.uninstall()`:

1. Read the recorded state. If nothing is installed, it's a no-op.
2. **Restore the live file** from its backup.
   - If the recorded file still exists → copy the backup over it.
   - If the game has moved to a **newer season** (the recorded file no longer
     exists and a higher `<N>` is now live) → the old file is already dead to
     the game, so there's *nothing* to restore on the live file; it prints a
     note and does **not** touch the new season's file.
   - If no backup existed (file was created by the install, not overwriting
     an original) → the file is simply removed.
3. **Clear the installation state** (backups are kept on disk).

Restore is **idempotent**: running uninstall with no install does nothing and
errors nothing.

## Backups live in the state dir

Backups are stored under the per-platform **state directory** (not in the
program folder, not in the game folder):

```
<state_dir>/
├── state.json
├── custom/                 # generated customization files (see Customization)
└── backups/
    ├── SEASON_DATA_CACHE_S22.json_20260101_120000
    └── season_data_cache_s22.json_20260102_083000_archived
```

This keeps user data out of the program directory (which you might
re-download/replace) and out of the game's tree.

## ⚠ Put Steam in Offline Mode

The single most common failure mode is **not** a program bug: if Steam is
online, launching NMS can let Steam (or the game's online expedition check)
**revert the cache file**, wiping the installed expedition. Before playing,
set Steam to **Offline Mode**. The install dialog always reminds you.

## Season updates

Because the live file is resolved as "highest season number present" and the
library file name is a stable constant, **a season bump (S22 → S23, or S40)
requires no code change**:

- **Install** targets whatever the highest `S<N>` file is, and archives the
  older ones.
- **Uninstall** is aware that the recorded file may no longer be the live
  one, and won't clobber a newer season's file.
- The library file keeps its historical `…_S22.JSON` name; the installer
  maps it onto whatever the live name currently is.

So after a game update, the flow is: launch the game once (creates the new
`S23` file), then install as usual — the old `S22` file is archived and the
expedition lands on the live `S23` file.

## Failure modes & safety

- **No cache found** → the install is aborted *before* any file is touched.
- **Source missing** (combination not in library) → aborted with "run sync".
- **Interrupted copy** → the backup from step 4 already exists, so you can
  restore; the worst case is a re-install.
- **Nothing is deleted**, only moved into `backups/`.
