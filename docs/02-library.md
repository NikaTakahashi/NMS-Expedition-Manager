# 2 · The Library

The **library** is the program's on-disk store of every generated expedition
file. It lives in `ExpeditionManagerLibrary/` inside the program directory by
default (override with `library_path` in `config.txt`, see
[Configuration & Data](09-config-and-data.md)).

## Size and shape

The library holds **126 files**:

```
22 expeditions × {Original, Redux} × {Defaults, Easy, Hardcore}
```

minus the combinations that don't exist. Concretely, by folder:

| Mode \ Difficulty | Defaults | Easy | Hardcore | Total |
|-------------------|:--------:|:----:|:--------:|:-----:|
| **Originals**     | 22       | 22   | 22       | 66    |
| **Redux**         | 20       | 20   | 20       | 60    |
| **Total**         | 42       | 42   | 42       | **126** |

Redux totals 20 because two expeditions have **no Redux version**
(`e21 Remnant` and `e22 Swarm` are Original-only).

## Directory layout

```
ExpeditionManagerLibrary/
├── manifest.json
├── Originals/
│   ├── Defaults/
│   │   ├── 01_Pioneers/SEASON_DATA_CACHE_S22.JSON
│   │   ├── 02_Beachhead/SEASON_DATA_CACHE_S22.JSON
│   │   └── …  (22 folders)
│   ├── Easy/
│   └── Hardcore/
└── Redux/
    ├── Defaults/
    ├── Easy/
    └── Hardcore/
```

Two naming rules to note:

- The **difficulty** is the *middle* folder, the **mode** (Originals/Redux)
  the top one. So `Originals/Easy/01_Pioneers/…` is "Pioneers, original
  version, Easy preset".
- Each expedition folder is named **`NN_Name`** (e.g. `01_Pioneers`), derived
  from the expedition's human name by replacing every non-alphanumeric
  character with `_`. It is *not* the internal id `e01`. The internal id is
  only used in the manifest key and in the `eNNrNN` version ids.

Every leaf file is named **`SEASON_DATA_CACHE_S22.JSON`** — the historical
S22 name. That name is kept for stability; the *live* game file may be named
for a newer season, and the installer maps between them (see
[Install & Uninstall](04-install-uninstall.md#season-updates)).

## The manifest

`manifest.json` is a flat map with **126 keys**, one per generated file:

```jsonc
{
  "e01/Originals/Defaults": {
    "exp_id": "e01",
    "name": "01: Pioneers",
    "version_id": "e01r00",
    "mode": "Originals",
    "difficulty": "Defaults",
    "sha256": "a5e1e1ff91b39869a1febadbc7cfe8e5da58052b29e8b482455d7d3cabd40cff"
  },
  "e01/Originals/Easy": { … },
  "e01/Redux/Defaults":  { … },
  "e01/Redux/Easy":      { … }
}
```

- **Key format:** `<exp_id>/<Mode>/<Difficulty>` — e.g.
  `e05/Redux/Hardcore`. This is the canonical address of a file.
- **`sha256`** is the hash of the generated JSON *exactly as written to
  disk*. It is the source of truth for "is this file current?" — the sync
  uses it to skip files whose content hasn't changed (see
  [Synchronization](03-sync.md)).
- **`version_id`** (`eNNrNN`) records which catalog version was used
  (the original `r00`, or the latest redux `r01`/`r02`/…).

The manifest is what the **GUI Library tab** and the **CLI `list`** command
read to report download/verification status, and what the installer looks up
to find the file for a chosen `(exp_id, mode, difficulty)`.

## The catalog (where the list of expeditions comes from)

The *list* of expeditions, their names, their versions (original vs redux),
and their per-version/global patch references all come from the upstream
`_data/expeditions.yml` (see [Synchronization](03-sync.md)). `catalog.py`
parses that YAML into `Expedition` objects, each carrying:

- `id` (`e01`), `name` (`01: Pioneers`), `description`, `notice`
- `versions` — a list of `Version`s; `Version.original` is the non-redux
  one, `Version.latest_redux` is the most recent redux (or `None`)
- `exp_patches` — expedition-level patch references

So the library is a *materialization* of the catalog: for each expedition,
for each available mode (Original + Redux if present), for each of the three
difficulties, one generated file.

## Verifying a file

Because every file is addressed by hash, "is my library intact?" is a one-liner:
recompute the SHA-256 of each `SEASON_DATA_CACHE_S22.JSON` and compare it to
the `sha256` in the manifest. A mismatch means the file was edited or
partially written. (A *forced* resync rewrites everything and refreshes the
hashes; a normal sync leaves matching files untouched.)
