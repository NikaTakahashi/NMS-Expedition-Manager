# 5 · Customization

Beyond the three stock difficulties (Defaults / Easy / Hardcore), an
expedition can be tuned parameter by parameter — exactly what the official
website's form does. This program reproduces that form and the same
"apply my values on top of the difficulty" behavior, in both the GUI and the
CLI.

## The parameter space

The set of tunable parameters is defined upstream in
`_data/customizations.yml`: **67 parameters** in two groups.

- **General** (46) — gameplay rules: survival mode, carnage mode, resources,
  faction (e.g. the Swarm / community-team setting), end date, etc.
- **Difficulty Minimums** (21) — floor values for difficulty scaling.

Each parameter has a `type` (bool / int / float / str / seed / enum), an
optional `options` list (for dropdowns), a `display` name, a `description`,
and sometimes a `warning`. Some are *nested* (a `subprop` under a `parent`
section), which matters because the value must land in the right place in the
JSON — the generator uses the prop map for that.

## Presets

- **Defaults** = *no* overrides (the stock file).
- **Easy** and **Hardcore** = a fixed bundle of **25** parameter values each
  (fetched from the upstream preset JSONs). Hardcore is what the website calls
  *Permadeath* (it sets `DifficultySettingPreset = "Permadeath"` — placed by
  the prop map in the correct section of the JSON — plus the start-system
  protections `BlockStormsAtStart` and `BlockAggressiveSentinelsInStartSystem`,
  the Hard Mode game preset, and the difficulty minimums).

A preset is just a flat map of `prop → value`. A user's customization is also
a flat map. The only difference between "install Easy" and "install Easy with
my tweaks" is **which flat map gets applied** at the preset stage of the
pipeline.

## How a customized file is built

The key design decision: **user values are applied at the *same* stage as the
difficulty preset** — i.e. as `difficulty_overrides` in the generator. So a
customized file goes through the *same* pipeline as a stock one; only the
override map differs:

```
base JSON
  → apply (preset ∪ user-values)      ← same stage, merged map
  → apply version patches
  → apply global patches
  → serialize (JS-style)
```

A direct consequence: **if the user changes nothing, the applied map equals
the plain preset, and the output is byte-identical to the pre-built library
file.** Customization is a pure superset of the stock behavior — it can never
change what a no-change install produces.

`customize.install_source_from_flat(exp_id, mode, difficulty, flat)` is the
decision point:

- **`flat == preset`** (no user changes) → returns `None`: use the pre-built
  library file (fast, hash-verified).
- **`flat != preset`** (user tweaked something) → **generate** the file on
  the fly from the cached sources, write it to
  `<state_dir>/custom/<expid>_<Mode>_<Difficulty>.json`, and return that path.
  No network is needed (sources are already cached), and no entry is added to
  the library — the custom file lives in the state dir.

## In the GUI

The **Customization** frame on the Install tab is the website's form, 1:1:

- One **dropdown per parameter** (67 total), grouped under *General* and
  *Difficulty Minimums*.
  - Params with `options` → readonly dropdown of the option texts.
  - Bool params → `true` / `false`.
  - Numbers / seeds → editable text.
  - The value *`(game default)`* means "leave it untouched".
- **Load selected mode** — refills the whole form with the current
  difficulty's preset. **Reset all** — sets every param back to
  `(game default)`.
- **Click a parameter** → its description (and ⚠ warning, if any) is shown in
  the help line below.
- **State line** — counts how many parameters differ from the mode's preset:
  - `0 changed` → "No changes — the pre-built file will be installed".
  - `N changed` → "N parameter(s) changed vs \<mode\> — the file will be
    generated at install time".
- Changing **difficulty / version / expedition** auto-reloads the form with
  that mode's preset (so the form always reflects the selected difficulty).

When you install with changes, the full resulting value set is **saved with
the installation** in `state.json` (`installed.custom`), so reopening the GUI
restores the exact form values you installed with.

## In the CLI

The same capability is available without the GUI:

```
./run.sh install --exp e01 --difficulty easy \
    --custom "CarnageMode=true,StartingSuitSlots=24"
```

`--custom` takes a `Prop=Value,Prop2=Value2,…` string. It is parsed
(`parse_custom_spec`), **validated** against the spec (unknown params, bad
types, out-of-range options are rejected with a helpful message listing valid
examples), merged on top of the difficulty preset, and the file is generated
as in the GUI. This makes the customization **scriptable and repeatable** —
the exact same command reproduces the same file.

## Relationship to `overrides.json`

Don't confuse the two:

| | `--custom` / GUI form | `overrides.json` |
|---|---|---|
| Scope | **One installation** (one expedition/mode/difficulty) | **The whole library** (any combination) |
| Where it's stored | `state.json` (`installed.custom`) | a file in the program directory |
| Applied at | the preset stage, for that one file | the *last* stage, for matching combos, at sync time |
| Changes library hashes? | No (custom file is separate) | Yes (personalized files no longer match the stock hash) |
| For | "I want *this* playthrough tweaked" | "I want *my* house-rules baked into the library" |

`overrides.json` uses the same override language (removals/appends/…) as the
upstream patches and is applied after everything else, so it can encode
anything the per-install form cannot (e.g. a global setting across all
expeditions).

## Safety

- Custom files are only ever **generated**; the library's pre-built files are
  never modified by customization.
- Generation uses the *same* byte-identical serializer, so a custom file is a
  faithful expedition file — it's the game's normal JSON plus your values.
- A bad `--custom` string **fails fast** (validation error, non-zero exit) and
  touches no file.
