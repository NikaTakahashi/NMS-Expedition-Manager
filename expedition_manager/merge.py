"""JSON merging: Python port of the recursiveFix() algorithm from nms.js in
cwmonkey/nms-expeditions, plus the conversion of preset values.

Directives supported in patches/overrides:
  [[removed]]            -> remove the property / array element
  [[append]]             -> (array) append its elements to the end of the array
  [[ifundefinedorblank]] -> only apply if the current value is missing or '^'
  [[iflessthan]]         -> only apply if the current numeric value < threshold
  [[ifkeyexists]]        -> only apply if another key exists in the object
  [[rename]]             -> {"from": ..., "to": ...} renames a key
  null                   -> leave untouched
"""
import copy
import re
import time

SPECIAL_KEYS = ("[[ifundefinedorblank]]", "[[iflessthan]]", "[[ifkeyexists]]", "[[rename]]")
REMOVED = "[[removed]]"
APPEND = "[[append]]"


def _clean_array(fixer_arr):
    """A copy of a 'fixer' array with directives processed (as the JS does).
    It is applied over an EMPTY array, so every index exceeds the target
    length and entries are appended as-is (nested arrays get cleaned)."""
    target = []
    recursive_fix(target, fixer_arr)
    return target


def recursive_fix(target, fixer):
    """Apply `fixer` onto `target` in place and return target."""
    if isinstance(fixer, list):
        return _fix_array(target, fixer)
    return _fix_dict(target, fixer)


def _fix_array(target, fixer):
    """Exact JS semantics: an array 'fixer' is iterated as a dictionary of
    indices (Object.keys). Indices that exceed the target length are appended
    AS-IS (directives are NOT processed) -- this is the actual behaviour of
    the website and must be reproduced so the generated files match."""
    if not isinstance(target, list):
        # The JS would fail here; replace for safety
        return _clean_array(fixer)

    if fixer and fixer[0] == APPEND:
        for v in fixer[1:]:
            target.append(copy.deepcopy(v))
        return target

    # ORIGINAL length: the JS assigns by index (arr[4]=x on a len-2 array
    # creates holes, it does not append); append/merge must be decided
    # against the initial length.
    orig_len = len(target)
    # Backwards, like the JS (reversed Object.keys)
    for i in range(len(fixer) - 1, -1, -1):
        val = fixer[i]
        if val == REMOVED:
            # JS: target.splice(i, 1) -- a no-op when i >= len
            if i < len(target):
                del target[i]
            continue
        if val is None:
            continue
        if i >= orig_len:
            # Index not present in the target: the JS assigns 'whatever it
            # is' (nested arrays are cleaned, but directives inside dicts
            # are NOT processed). Python pads with None up to the index;
            # JS 'holes' always end up covered because fixer indices are
            # contiguous from 0 to n-1.
            while len(target) <= i:
                target.append(None)
            target[i] = copy.deepcopy(_clean_nested(val))
            continue
        cur = target[i]
        if isinstance(val, (dict, list)) and (cur is None or isinstance(cur, (dict, list))):
            if cur is None:
                target[i] = _clean_nested(val) if isinstance(val, list) else copy.deepcopy(val)
            else:
                target[i] = recursive_fix(cur, val)
        else:
            target[i] = copy.deepcopy(val)
    return target


def _clean_nested(val):
    """Like the JS: nested arrays are 'cleaned' (evaluated), dicts are copied."""
    if isinstance(val, list):
        return _clean_array(val)
    return copy.deepcopy(val)


def _fix_dict(target, fixer):
    if not isinstance(target, dict):
        # The JS would fail here; replace for safety
        return copy.deepcopy(fixer)

    ifkeyexists = fixer.get("[[ifkeyexists]]")
    rename = fixer.get("[[rename]]")
    ifundefined = fixer.get("[[ifundefinedorblank]]")
    iflessthan = fixer.get("[[iflessthan]]")

    # [[rename]] (unless the ifkeyexists condition fails)
    if rename:
        key_ok = True
        if ifkeyexists is not None and ifkeyexists not in target:
            key_ok = False
        if key_ok and rename.get("from") in target:
            target[rename["to"]] = target.pop(rename["from"])

    for prop in reversed(list(fixer.keys())):
        if prop in SPECIAL_KEYS:
            continue
        val = fixer[prop]

        if ifundefined is not None and prop in target and target[prop] != "^":
            continue
        cur = target.get(prop)
        if (iflessthan is not None and cur is not None
                and isinstance(cur, (int, float)) and iflessthan <= cur):
            continue
        if ifkeyexists is not None and ifkeyexists not in target:
            continue

        if val == REMOVED:
            target.pop(prop, None)
        elif val is None:
            continue
        elif prop not in target:
            # Not present in the source: add it in full (arrays cleaned)
            target[prop] = _clean_array(val) if isinstance(val, list) else copy.deepcopy(val)
        elif isinstance(target[prop], (dict, list)) and isinstance(val, (dict, list)):
            target[prop] = recursive_fix(target[prop], val)
        elif isinstance(val, (dict, list)):
            target[prop] = _clean_array(val) if isinstance(val, list) else copy.deepcopy(val)
        else:
            target[prop] = copy.deepcopy(val)
    return target


# ---------------- preset value conversion ----------------

INT_RE = re.compile(r"^(0|([1-9][0-9]*))$")
FLOAT_RE = re.compile(r"^[0-9.]+$")


def convert_value(value, type_):
    """Convert a preset value (str) to the expected type (as the web's updateProps)."""
    if value == "true":
        return True
    if value == "false":
        return False
    if type_ == "seed":
        return [False, value] if value == "0x0" else [True, value]
    if type_ != "str" and INT_RE.match(value):
        return int(value)
    if type_ not in ("ua", "str") and FLOAT_RE.match(value):
        return float(value)
    return value


def filter_prop(name, value):
    """Special handling of EndTimeUTC ('+7 Days' -> absolute UTC timestamp)."""
    if name == "EndTimeUTC" and isinstance(value, str):
        m = re.match(r"^\+([0-9]+) ([a-zA-Z]+)$", value)
        if m:
            count = int(m.group(1)) or 6
            unit = m.group(2)
            days = 7 if unit == "Weeks" else 30 if unit == "Months" else 1
            return round(time.time()) + days * count * 86400
    return value


def build_overrides(preset: dict, prop_map: dict) -> dict:
    """Convert a flat preset (prop->value) into the nested overrides object.

    IMPORTANT: iteration follows the order of customizations.yml (the website
    DOM order), NOT the order of the preset JSON: the JS fills the form
    inputs in that order and the resulting `overrides` object inherits that
    key order, which affects the final file layout.
    """
    overrides = {}
    for prop, info in prop_map.items():
        if prop not in preset:
            continue
        value = preset[prop]
        v = filter_prop(prop, convert_value(value, info["type"]))
        if info["parentprop"]:
            obj = overrides.setdefault(info["parentprop"], {})
        else:
            obj = overrides
        if info["subprop"]:
            obj2 = obj.setdefault(prop, {})
            obj2[info["subprop"]] = v
        else:
            obj[prop] = v
    return overrides


def apply_overrides(base: dict, overrides: dict) -> dict:
    """Return a copy of `base` with `overrides` applied."""
    merged = copy.deepcopy(base)
    recursive_fix(merged, overrides)
    return merged
