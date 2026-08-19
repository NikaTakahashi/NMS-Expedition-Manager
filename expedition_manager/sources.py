"""Download of sources from the cwmonkey/nms-expeditions repository.

Includes retries, a jsDelivr CDN fallback, and a local cache so files are
not re-downloaded unless forced.
"""
import json
import time
from pathlib import Path

import requests

RAW_BASE = "https://raw.githubusercontent.com/cwmonkey/nms-expeditions/refs/heads/main/"
CDN_BASE = "https://cdn.jsdelivr.net/gh/cwmonkey/nms-expeditions@main/"

RETRIES = 3
TIMEOUT = 30


class SourceError(RuntimeError):
    pass


class Sources:
    """Local cache of repository files, with retries and CDN fallback."""

    def __init__(self, cache_dir: Path, force: bool = False, quiet: bool = False,
                 log=None):
        self.cache_dir = Path(cache_dir)
        self.force = force
        self.quiet = quiet
        self._log_cb = log
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "expedition-manager/1.0"
        # The base that worked best on the last download (preferred afterwards)
        self.preferred_base = None

    def _log(self, msg: str) -> None:
        prefix = "  [download] "
        if self._log_cb:
            self._log_cb(prefix + msg)
        elif not self.quiet:
            print(prefix + msg)

    def fetch(self, relpath: str) -> str:
        """Return the textual content of a repository file (relative path)."""
        cache_file = self.cache_dir / relpath.replace("/", "__")
        if cache_file.exists() and not self.force:
            return cache_file.read_text(encoding="utf-8")

        bases = []
        if self.preferred_base:
            bases.append(self.preferred_base)
        for b in (RAW_BASE, CDN_BASE):
            if b not in bases:
                bases.append(b)

        last_err = None
        for base in bases:
            url = base + relpath
            for attempt in range(1, RETRIES + 1):
                try:
                    resp = self.session.get(url, timeout=TIMEOUT)
                    if resp.status_code == 200:
                        text = resp.text
                        cache_file.parent.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(text, encoding="utf-8")
                        self.preferred_base = base
                        return text
                    last_err = SourceError(f"HTTP {resp.status_code} for {url}")
                    # Rate-limited/blocked: no point retrying the same base
                    if resp.status_code in (403, 429):
                        break
                except requests.RequestException as e:
                    last_err = e
                if attempt < RETRIES:
                    wait = 2 ** attempt
                    self._log(f"retry {attempt} in {wait}s...")
                    time.sleep(wait)

        raise SourceError(f"Could not download {relpath}: {last_err}")

    def fetch_json(self, relpath: str):
        return json.loads(self.fetch(relpath))
