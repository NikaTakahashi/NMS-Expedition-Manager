"""Runtime customization of expedition parameters (the website's form).

The cwmonkey website shows one input per property of
``_data/customizations.yml`` and pre-fills it with the values of the
selected difficulty preset. Whatever values the user sets are applied
through the SAME mechanism as the presets (they become the
``difficulty_overrides`` of the pipeline), so:

  * a form left untouched  -> file byte-identical to the pre-built library
  * a form with changes    -> the file is generated on the fly from the
                              cached sources (no network needed after the
                              first sync)
"""
from pathlib import Path

import yaml

from .catalog import build_catalog, build_prop_map
from .config import state_dir
from .merge import build_overrides, INT_RE, FLOAT_RE
from .sources import Sources
from .sync import generate, _global_patches, _patches_for

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sources"

#: The "(game default)" entry of the GUI dropdowns (no override for the prop)
DEFAULT_TEXT = "(game default)"

PRESET_FILES = {
    "Easy": "_includes/customizations.easy_mode.json",
    "Hardcore": "_includes/customizations.hard_mode.json",
}


def _sources() -> Sources:
    """Sources rooted at the local cache (network only if a file is missing)."""
    return Sources(DATA_DIR, force=False, quiet=True)


# --------------------------------------------------------------- spec

def load_spec():
    """(groups, prop_map) describing every customizable parameter.

    groups: [{name, parent, props: [{prop, type, subprop, parentprop,
             options, display, description, warning}]}] in the website's
    order; prop_map: the placement map (type/subprop/parentprop).
    """
    src = _sources()
    raw = src.fetch("_data/customizations.yml")
    data = yaml.safe_load(raw) or []
    groups = []
    for section in data:
        parent = section.get("prop")
        props = []
        for cust in section.get("customizations", []):
            # YAML parses 'value: True' as a bool; the website (and the
            # presets) use the strings 'true'/'false' -> normalize.
            options = None
            if cust.get("options"):
                options = []
                for o in cust["options"]:
                    v = o.get("value")
                    if isinstance(v, bool):
                        v = "true" if v else "false"
                    options.append({"value": v, "text": str(o.get("text", v))})
            props.append({
                "prop": cust["prop"],
                "type": cust.get("type", "str"),
                "subprop": cust.get("subprop"),
                "parentprop": parent,
                "options": options,
                "display": cust.get("display"),
                "description": cust.get("description"),
                "warning": cust.get("warning"),
            })
        groups.append({
            "name": section.get("name") or section.get("id") or "?",
            "parent": parent,
            "props": props,
        })
    return groups, build_prop_map(raw)


def spec_props(groups):
    """{prop: prop-entry} for every customizable property."""
    return {p["prop"]: p for g in groups for p in g["props"]}


# --------------------------------------------------------------- presets

def load_preset(difficulty: str) -> dict:
    """Flat prop->value (str) of a difficulty preset ({} for 'Defaults')."""
    rel = PRESET_FILES.get(difficulty)
    if not rel:
        return {}
    data = _sources().fetch_json(rel)
    return {k: v for k, v in data.items()
            if k != "_generatedBy" and isinstance(v, str)}


# --------------------------------------------------------------- input parsing

def parse_custom_spec(text: str) -> dict:
    """Parse 'Prop=Value,Prop2=Value2' (CLI --custom) into a flat dict."""
    out = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(
                f"bad pair '{part}' (expected Prop=Value, e.g. "
                "CarnageMode=true, StartingSuitSlots=24)")
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def validate(flat: dict, prop_map: dict, props_spec: dict) -> list:
    """Return error messages (empty list = OK) for a flat prop->value dict."""
    errs = []
    for prop, value in flat.items():
        info = prop_map.get(prop)
        if info is None:
            known = ", ".join(sorted(props_spec)[:5]) + ", …"
            errs.append(f"unknown parameter '{prop}' (examples: {known})")
            continue
        v = str(value)
        opts = (props_spec.get(prop) or {}).get("options")
        if opts:
            allowed = [str(o["value"]) for o in opts]
            if v not in allowed:
                errs.append(f"{prop}: '{v}' not in {allowed}")
                continue
        t = info["type"]
        if t == "bool" and v not in ("true", "false"):
            errs.append(f"{prop}: expected true/false, got '{v}'")
        elif t == "int" and not INT_RE.match(v):
            errs.append(f"{prop}: expected an integer, got '{v}'")
        elif t == "float" and not FLOAT_RE.match(v):
            errs.append(f"{prop}: expected a decimal number, got '{v}'")
    return errs


# --------------------------------------------------------------- generation

def build_file(exp_id: str, mode: str, difficulty: str, flat: dict,
               out_path=None) -> Path:
    """Generate the customized JSON for (exp, mode, difficulty) and write it.

    `flat` is the FULL set of form values (preset + user changes). It is
    applied at the same pipeline stage as the difficulty preset, so a
    stock preset yields a file identical to the pre-built library one.
    """
    src = _sources()
    catalog = {e.id: e for e in build_catalog(src.fetch("_data/expeditions.yml"))}
    entry = catalog.get(exp_id)
    if entry is None:
        raise ValueError(f"unknown expedition '{exp_id}'")
    version = entry.original if mode == "Originals" else entry.latest_redux
    if version is None:
        raise ValueError(f"{exp_id} has no Redux version")

    prop_map = build_prop_map(src.fetch("_data/customizations.yml"))
    overrides = build_overrides(flat, prop_map)
    base_text = src.fetch(f"_includes/original/{version.json_file}")
    content = generate(base_text, version, difficulty, overrides, src,
                       _global_patches(src),
                       exp_patches=_patches_for(entry, version))

    out = Path(out_path) if out_path else (
        state_dir() / "custom" / f"{exp_id}_{mode}_{difficulty}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return out


def install_source_from_flat(exp_id: str, mode: str, difficulty: str,
                             flat: dict):
    """Decide the installation source for a full form value set.

    Returns (source_file, custom_flat):
      (None, None)            -> stock: use the pre-built library file
      (Path, flat)            -> customized: generate the file and install it
    """
    if not flat:
        return None, None
    if flat == load_preset(difficulty):
        return None, None
    path = build_file(exp_id, mode, difficulty, flat)
    return path, dict(flat)
