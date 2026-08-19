"""Expedition catalog: parsing of expeditions.yml and customizations.yml."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yaml


@dataclass
class Version:
    id: str                 # e.g. e01r00
    json_file: str          # e.g. E01_PIONEERS_ORIGINAL_SEASON_DATA_CACHE.JSON
    date: int               # timestamp of the original release date
    redux: bool = False
    notice: str = ""
    patches: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return "Redux" if self.redux else "Original"

    @property
    def date_str(self) -> str:
        if not self.date:
            return "unknown"
        return datetime.fromtimestamp(self.date, tz=timezone.utc).strftime("%b %Y")


@dataclass
class Expedition:
    id: str                 # e.g. e01
    name: str               # e.g. '01: Pioneers'
    description: str = ""
    notice: str = ""
    versions: list = field(default_factory=list)
    exp_patches: list = field(default_factory=list)   # expedition-level patches

    @property
    def original(self) -> Version:
        """The original (r00) version."""
        for v in self.versions:
            if not v.redux:
                return v
        return self.versions[0]

    @property
    def latest_redux(self):
        """The most recent redux version (the one the website recommends), or None."""
        reduxes = [v for v in self.versions if v.redux]
        return reduxes[-1] if reduxes else None

    @property
    def folder_name(self) -> str:
        """A filesystem-safe folder name, e.g. '01_Pioneers'."""
        return re.sub(r"[^A-Za-z0-9]+", "_", self.name).strip("_")


def build_catalog(raw_yaml: str) -> list:
    """Parse expeditions.yml and return the list of Expedition objects."""
    data = yaml.safe_load(raw_yaml)
    expeditions = []
    for exp in data:
        versions = [
            Version(
                id=v["id"],
                json_file=v["json"],
                date=int(v.get("date", 0)),
                redux=bool(v.get("redux")),
                notice=(v.get("notice") or "").strip(),
                patches=v.get("patches") or [],
            )
            for v in exp.get("versions", [])
        ]
        expeditions.append(
            Expedition(
                id=exp["id"],
                name=exp["name"],
                description=exp.get("description", ""),
                notice=(exp.get("notice") or "").strip(),
                versions=versions,
                exp_patches=exp.get("patches") or [],
            )
        )
    return expeditions


def build_prop_map(raw_yaml: str) -> dict:
    """Map of prop -> {type, subprop, parentprop} built from customizations.yml.

    Required to place preset values at the correct position of the JSON
    (some props are nested under a section or subproperty).
    """
    data = yaml.safe_load(raw_yaml)
    prop_map = {}
    for section in data:
        parent = section.get("prop")
        for cust in section.get("customizations", []):
            prop_map[cust["prop"]] = {
                "type": cust.get("type", "str"),
                "subprop": cust.get("subprop"),
                "parentprop": parent,
            }
    return prop_map


def build_glyph_map(raw_yaml: str) -> dict:
    """Map of glyph name -> hex character (NMS glyphs are 0-9A-F)."""
    data = yaml.safe_load(raw_yaml)
    glyphs = {}
    for name, html in (data or {}).items():
        m = re.search(r'glyph">([0-9A-Fa-f])<', str(html))
        if m:
            glyphs[name] = m.group(1).upper()
    return glyphs


def glyphs_to_hex(text: str, glyph_map: dict) -> str:
    """Convert glyph sequences like ':eclipse:bird:...:' to their hex values.

    The whole sequence is parsed at once (single regex pass) so that replacing
    one glyph does not destroy the ':' shared with its neighbours.
    """
    if not glyph_map:
        return text
    names = "|".join(re.escape(n) for n in sorted(glyph_map, key=len, reverse=True))
    # Full sequence: ':name' followed by zero or more ':name'
    seq_re = re.compile(r":(?:" + names + r")(?::(?:" + names + r"))*")

    def conv(m):
        tokens = [t for t in m.group(0).split(":") if t]
        try:
            return "`" + "".join(glyph_map[t] for t in tokens) + "`"
        except KeyError:
            return m.group(0)

    return seq_re.sub(conv, text)
