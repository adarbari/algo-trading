"""TOML config files. Layout under the config root (``ALGOTRADE_CONFIG_DIR``, default ./config)::

site/defaults.toml                         L3 defaults (screening, backtest)
site/<name>.toml                           L3 site settings (kind ``settings``)
site/features/<theme>.toml                 L3 expression features (kind ``features``)
site/presets/strategies/<id>.toml          L3 shared strategy / screener configs
site/presets/selections/<id>.toml          L3 shared selections
users/<user>/strategies/<id>.toml          L4 (git-ignored locally)
users/<user>/selections/<id>.toml
users/<user>/features/<theme>.toml         L4 expression features (always virtual)
site/presets/screeners/<id>/v<N>.toml      L3 rule-screen preset versions: immutable (hash
                                           lock: architecture/preset_versions.toml); latest = max N
users/<user>/screeners/<id>/v<N>.toml      L4 finalised rule screen: immutable; latest = max N
users/<user>/screeners/<id>/draft.toml     L4 the Builder's working copy (never loaded to run)
users/<user>/screeners/<id>/schedule.toml  L4 the schedule switch (``schedule = "nightly"``)

Writes go through ``storage/configs/writer.py`` (``FileConfigWriter``) only (ADR 0029).
"""

import csv
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.storage.configs.store import KINDS, screen_document, split_version

SITE = "site"
SCREENERS = "screeners"
DRAFT = "draft.toml"
SCHEDULE = "schedule.toml"
_ID_NAME = re.compile(r"[a-z0-9_-]{1,64}")  # core.model.ids: other names are not screens
_VERSION_FILE = re.compile(r"v([1-9][0-9]{0,8})\.toml")


def version_file(version: int) -> str:
    return f"v{version}.toml"


def read_toml(path: Path) -> dict[str, Any] | None:
    """The document at ``path``; ``None`` when there is no file."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"{path}: invalid TOML: {exc}") from exc


class FileConfigStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, scope: str, kind: str, name: str) -> Path:
        if kind not in KINDS:
            raise ConfigurationError(f"unknown config kind {kind!r}")
        if scope == SITE:
            if kind == "defaults":
                return self.root / SITE / "defaults.toml"
            if kind == "settings":
                return self.root / SITE / f"{validate_id(kind, name)}.toml"
            if kind == "features":
                return self.root / SITE / "features" / f"{validate_id(kind, name)}.toml"
            return self.root / SITE / "presets" / kind / f"{validate_id(kind, name)}.toml"
        user = validate_id("user", scope)
        return self.root / "users" / user / kind / f"{validate_id(kind, name)}.toml"

    def screen_dir(self, scope: str, name: str) -> Path:
        """A rule screen's folder of versions: ``site/presets/screeners/<name>/`` (a preset)
        or ``users/<user>/screeners/<name>/`` (a user's screen, with its draft)."""
        name = validate_id("screener", name)
        if scope == SITE:
            return self.root / SITE / "presets" / SCREENERS / name
        return self.root / "users" / validate_id("user", scope) / SCREENERS / name

    def screen_versions(self, scope: str, name: str) -> list[int]:
        """The finalised versions of the screen ``name`` in ``scope``, ascending."""
        directory = self.screen_dir(scope, name)
        if not directory.is_dir():
            return []
        found = (_VERSION_FILE.fullmatch(p.name) for p in directory.iterdir() if p.is_file())
        return sorted(int(m.group(1)) for m in found if m)

    def screen_schedule(self, user: str, name: str) -> str | None:
        if user == SITE:
            return None
        doc = read_toml(self.screen_dir(user, name) / SCHEDULE) or {}
        value = doc.get("schedule")
        return value if isinstance(value, str) else None

    def _screen(self, scope: str, name: str) -> Mapping[str, Any] | None:
        """``name`` (latest version) or ``name@N`` (that version); a user's latest carries
        their schedule switch, a pinned version or a site preset its own."""
        name, pinned = split_version(name)
        versions = self.screen_versions(scope, name)
        version = pinned if pinned is not None else (versions[-1] if versions else None)
        if version is None or version not in versions:
            return None
        document = read_toml(self.screen_dir(scope, name) / version_file(version)) or {}
        if scope == SITE or pinned is not None:
            return document
        return screen_document(document, self.screen_schedule(scope, name))

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        if kind in ("defaults", "settings") and scope != SITE:
            return None
        if kind == SCREENERS:
            return self._screen(scope, name)
        return read_toml(self._path(scope, kind, name))

    def names(self, scope: str, kind: str) -> list[str]:
        if kind == "settings":
            if scope != SITE:
                return []
            return sorted(p.stem for p in (self.root / SITE).glob("*.toml") if p.stem != "defaults")
        if kind == "defaults":
            return ["defaults"] if scope == SITE and self._path(SITE, kind, "x").exists() else []
        if kind == SCREENERS:
            base = self.screen_dir(scope, "x").parent
            if not base.is_dir():
                return []
            ids = (p.name for p in base.iterdir() if p.is_dir() and _ID_NAME.fullmatch(p.name))
            return sorted(n for n in ids if self.screen_versions(scope, n))
        directory = self._path(scope, kind, "x").parent
        return sorted(p.stem for p in directory.glob("*.toml")) if directory.exists() else []

    def users(self) -> list[str]:
        base = self.root / "users"
        return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []

    def overrides(self, name: str) -> list[dict[str, str]]:
        path = self.root / SITE / "overrides" / f"{validate_id('override', name)}.csv"
        if not path.exists():
            return []
        with path.open(newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values())]
        return [
            {k: (v or "").strip() for k, v in r.items()}
            for r in rows
            if not r[next(iter(r))].startswith("#")
        ]


class MemoryConfigStore:
    """Dict-backed store for tests: ``{(scope, kind, name): document}`` + override rows."""

    def __init__(
        self,
        documents: Mapping[tuple[str, str, str], Mapping[str, Any]],
        overrides: Mapping[str, list[dict[str, str]]] | None = None,
    ) -> None:
        self._docs = dict(documents)
        self._overrides = dict(overrides or {})

    def overrides(self, name: str) -> list[dict[str, str]]:
        return list(self._overrides.get(name, []))

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        """Rule screens may be keyed ``<id>@<N>`` (versions): ``<id>`` is the latest."""
        if kind == SCREENERS and (scope, kind, name) not in self._docs:
            base, pinned = split_version(name)
            versions = self._screen_versions(scope, base)
            if pinned is None and versions:
                return self._docs[(scope, kind, f"{base}@{versions[-1]}")]
        return self._docs.get((scope, kind, name))

    def _screen_versions(self, scope: str, name: str) -> list[int]:
        keys = (n for (s, k, n) in self._docs if (s, k) == (scope, SCREENERS))
        return sorted(v for b, v in map(split_version, keys) if b == name and v is not None)

    def names(self, scope: str, kind: str) -> list[str]:
        names = {n for (s, k, n) in self._docs if s == scope and k == kind}
        return sorted({split_version(n)[0] for n in names} if kind == SCREENERS else names)

    def users(self) -> list[str]:
        return sorted({s for (s, _, _) in self._docs if s != SITE})
