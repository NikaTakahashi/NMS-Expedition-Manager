"""Download of sources from the cwmonkey/nms-expeditions repository.

Includes retries, a jsDelivr CDN fallback, and a local cache so files are
not re-downloaded unless forced. File locations are resolved against the
repository's current file list (GitHub tree API), so files that have been
moved within the repo (e.g. the 2026 move of _data/ into _includes/) keep
working automatically instead of silently staying stale or 404-ing.
"""
import json
import time
from pathlib import Path

import requests

RAW_BASE = "https://raw.githubusercontent.com/cwmonkey/nms-expeditions/refs/heads/main/"
CDN_BASE = "https://cdn.jsdelivr.net/gh/cwmonkey/nms-expeditions@main/"
TREE_API = ("https://api.github.com/repos/cwmonkey/nms-expeditions/"
            "git/trees/main?recursive=1")

RETRIES = 3
TIMEOUT = 30
TREE_TTL = 300            # seconds the repo file list is kept on disk
TREE_CACHE = ".tree.json"  # name of the cached file list (in the cache dir)


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
        self._tree = None
        self._tree_loaded = False

    def _load_tree(self):
        """Best-effort file list of the repo main branch: {path: blob-sha}.

        Returns a dict when GitHub is reachable, None otherwise (offline:
        the local cache keeps working exactly as before). The result is
        kept on disk for TREE_TTL seconds so repeated instantiations in a
        short time do not hammer the (rate-limited) GitHub API.
        """
        if self._tree_loaded:
            return self._tree
        self._tree_loaded = True
        self._tree = None
        disk = self.cache_dir / TREE_CACHE
        try:
            if disk.exists() and time.time() - disk.stat().st_mtime < TREE_TTL:
                self._tree = json.loads(
                    disk.read_text(encoding="utf-8")).get("tree")
                return self._tree
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        try:
            resp = self.session.get(
                TREE_API, timeout=TIMEOUT,
                headers={"Accept": "application/vnd.github+json"})
            if resp.status_code == 200:
                self._tree = {i["path"]: i.get("sha")
                              for i in resp.json().get("tree", [])
                              if i.get("type") == "blob"}
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                disk.write_text(json.dumps({"tree": self._tree}),
                                encoding="utf-8")
        except requests.RequestException:
            self._tree = None
        return self._tree

    def _resolve(self, relpath: str) -> str:
        """Current location of a file inside the repository.

        If the known path is still there, it is returned unchanged. If the
        repo has moved it, the unique file with the same name is used. When
        the repo state is unknown (offline) the path is returned as-is so
        the local cache is consulted exactly as before.
        """
        tree = self._load_tree()
        if not tree:
            return relpath
        if relpath in tree:
            return relpath
        base = relpath.rsplit("/", 1)[-1]
        matches = [p for p in tree if p.rsplit("/", 1)[-1] == base]
        if len(matches) == 1:
            return matches[0]
        return relpath

    def _log(self, msg: str) -> None:
        prefix = "  [download] "
        if self._log_cb:
            self._log_cb(prefix + msg)
        elif not self.quiet:
            print(prefix + msg)

    def fetch(self, relpath: str) -> str:
        """Return the textual content of a repository file (relative path).

        `relpath` may name the OLD location of a file that has since been
        moved in the repository; the file is then re-downloaded from its
        current location and the stale cached copy is cleaned up.
        """
        actual = self._resolve(relpath)
        cache_file = self.cache_dir / actual.replace("/", "__")
        if actual != relpath:
            # The file moved: drop the cached copy under its old name so it
            # is never served stale.
            old = self.cache_dir / relpath.replace("/", "__")
            if old.exists():
                try:
                    old.unlink()
                except OSError:
                    pass
        if cache_file.exists() and not self.force:
            return cache_file.read_text(encoding="utf-8")

        # If we know the repo layout and the file is not in it, fail fast
        # with a clear message instead of retrying 404s for minutes.
        tree = self._load_tree()
        if tree is not None and actual not in tree:
            raise SourceError(
                f"File {relpath} was not found in the cwmonkey/nms-expeditions"
                f" repository (it may have been renamed or removed).")

        bases = []
        if self.preferred_base:
            bases.append(self.preferred_base)
        for b in (RAW_BASE, CDN_BASE):
            if b not in bases:
                bases.append(b)

        last_err = None
        for base in bases:
            url = base + actual
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
                    # Rate-limited/blocked/gone: no point retrying the base
                    if resp.status_code in (403, 404, 429):
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
