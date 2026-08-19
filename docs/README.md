# Expedition Manager — Documentation

This folder documents **how the program works** — the features, the data
flow, and the reasoning behind the design decisions. It is not a tutorial for
using the game; it is a reference for anyone who wants to understand, modify,
or trust the tool.

> **Using the tool day to day?** You only need the [README](../README.md) and
> the *Guide* section inside it. Start here when you want to know *why* things
> are the way they are, or *what* each moving part does.

---

## Contents

| # | Document | What it covers |
|---|----------|----------------|
| 1 | [Overview](01-overview.md) | What the tool is, the big picture, and the core invariants it protects |
| 2 | [The Library](02-library.md) | The 126-file library, the manifest, and how files are named and laid out |
| 3 | [Synchronization](03-sync.md) | How files are generated to be byte-identical to the official website |
| 4 | [Install & Uninstall](04-install-uninstall.md) | Backups, the live season file, offline mode, and safe restore |
| 5 | [Customization](05-customization.md) | The 67-parameter form, presets, and on-the-fly file generation |
| 6 | [The GUI](06-gui.md) | The three tabs, the worker-thread model, and the queue |
| 7 | [The CLI](07-cli.md) | Every command, flag, and the interactive menu |
| 8 | [Platforms](08-platforms.md) | Windows / macOS / Linux: paths, launchers, and per-OS behavior |
| 9 | [Configuration & Data](09-config-and-data.md) | `config.txt`, `state.json`, caches, and where everything lives |

A **Spanish translation** of all of the above is in [`es/`](es/README.md).

---

## One-paragraph summary

The program is an **offline** client for No Man's Sky expeditions. It
*downloads and reproduces, file by file, the exact JSON that the official
[cwmonkey](https://cwmonkey.github.io/nms-expeditions/) website generates*,
keeps them in a local library, and lets you **install** one of them into the
game's cache folder (backing up the original first) or **uninstall** it
(restoring the original). Everything is reversible, verifiable by SHA-256,
and works without the game ever needing to be online.

The single most important guarantee the whole design protects is this:

> **An unmodified installation is byte-for-byte identical to the file the
> official website would download.**

Every other feature (sync, presets, customization, season handling) is built
to preserve that guarantee.

---

> If this project is useful to you, you can support its development at
> **[ko-fi.com/nikatakahashi](https://ko-fi.com/nikatakahashi)**. ☕
