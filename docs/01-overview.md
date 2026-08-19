# 1 · Overview

## What the tool is

Expedition Manager is a **local, offline manager** for the community-made
*expeditions* of No Man's Sky. The official
[cwmonkey](https://cwmonkey.github.io/nms-expeditions/) website lets you
customize and download expedition files in the browser; this program brings
the same capability to a standalone desktop app with two interfaces
(identical feature set):

- a **GUI** (Qt6 via PyQt6/PySide6 — native Wayland on Linux) for
  click-through use, and
- a **CLI** for scripting and for machines without a display.

It does three jobs:

1. **Build a library** — generate, for every expedition and every
   difficulty, the exact expedition JSON (see [The Library](02-library.md)
   and [Synchronization](03-sync.md)).
2. **Install** — copy one library file into the game's cache folder, after
   backing up the original (see [Install & Uninstall](04-install-uninstall.md)).
3. **Uninstall** — restore the original file from the backup.

## The core idea: offline + reproducible

Online expeditions require the game to connect to the community servers that
distribute them. These *offline* expeditions replace that: the game reads a
local file in its own cache folder and never phones home for expedition data.

To build that local file, the program does **not** scrape the website.
Instead it **reimplements the website's generator in Python**, using the same
source data the website itself uses (the public
[cwmonkey/nms-expeditions](https://github.com/cwmonkey/nms-expeditions)
repository). Because it follows the same steps, in the same order, with the
same serialization rules, the output is **byte-identical** to what the
website would hand you (see [Synchronization](03-sync.md) for the details of
why byte-identity is hard and how it is achieved).

## The three layers of data

```
 GitHub repo (cwmonkey/nms-expeditions)
        │  sources.py  ── downloads & caches the raw files
        ▼
 data/sources/        ← cached raw inputs (yaml/json patches)
        │  sync.py     ── base + preset + patches, JS-style JSON
        ▼
 ExpeditionManagerLibrary/   ← 126 generated .JSON files + manifest.json
        │  installer.py ── pick one, back up the original, copy it in
        ▼
 <NMS cache>/SEASON_DATA_CACHE_S<N>.json   ← what the game actually reads
```

Each arrow is a distinct module with a single responsibility. You can run
any stage on its own (sync without installing, list the library, etc.), and
no stage is surprising: what you see in the library is deterministic from
the upstream repo, and what you see in the game cache is exactly one library
file (plus your optional customizations).

## Invariants the whole design protects

These are the non-negotiables. If a change breaks any of them, it is a bug:

1. **Byte-identity of stock files.** A library file generated with *no*
   customizations must be bit-for-bit equal to the file the website produces
   for the same expedition/mode/difficulty. (Verified by SHA-256 against the
   upstream generator's expectations, and by cross-checking presets.)
2. **Reversibility.** Every install leaves a backup that, on uninstall,
   returns the cache to its pre-install bytes. Restoring is idempotent.
3. **No silent mutation of user data.** The game cache file is only ever
   touched after a backup is written; old-season files are *moved* to a
   backup, never deleted.
4. **Reproducibility.** Given the same upstream inputs and the same library,
   a sync produces the same hashes; a "no changes" sync downloads nothing.
5. **Forward-safe seasons.** The tool must keep working when the game bumps
   from S22 to S23 (or S40) without a code change (see
   [Install & Uninstall](04-install-uninstall.md#season-updates)).

## Why "offline expeditions" at all?

- **No network in the game.** The game runs fully offline; Steam must be in
  *Offline Mode* so it doesn't overwrite the cache on launch.
- **Replayable.** You can play any expedition, in any order, forever, without
  depending on the community servers being up.
- **Auditable.** The file in your cache is a plain JSON you can diff, hash,
  and re-generate at will.

## Glossary

| Term | Meaning |
|------|---------|
| **Expedition** | One of the 22 community expeditions (`e01`…`e22`). |
| **Original** | The expedition as first published (version `r00`). |
| **Redux** | A later rework of an expedition (`r01`, `r02`, …). Not every expedition has one. |
| **Difficulty / mode preset** | *Defaults*, *Easy*, *Hardcore* — preset bundles of parameter values. |
| **Preset** | The JSON of parameter overrides a difficulty applies (e.g. Hardcore sets *Permadeath*). |
| **Patch** | A data-driven override (removals, appends, substitutions) that the website applies per-version or globally. |
| **Library** | The local folder of 126 generated files + `manifest.json`. |
| **Cache file** | `SEASON_DATA_CACHE_S<N>.json` in the game's cache — the file the game reads. |
| **Sync** | (Re)generating the library from the upstream sources. |
