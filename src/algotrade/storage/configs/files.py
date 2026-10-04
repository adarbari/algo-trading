"""TOML config files. Layout under the config root (``ALGOTRADE_CONFIG_DIR``, default ./config)::

site/defaults.toml                         L3 defaults (screening, backtest)
site/<name>.toml                           L3 site settings (kind ``settings``)
site/features/<theme>.toml                 L3 expression features (kind ``features``)
site/presets/strategies/<id>.toml          L3 shared strategy / screener configs
site/presets/selections/<id>.toml          L3 shared selections
users/<user>/strategies/<id>.toml          L4 (git-ignored locally)
users/<user>/selections/<id>.toml
users/<user>/features/<theme>.toml         L4 expression features (always virtual)
site/presets/screeners/<id>.toml           L3 rule-screen presets (carry ``version = N``)
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
from algotrade.storage.configs.store import KINDS, screen_document

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

    def screen_dir(self, user: str, name: str) -> Path:
        """``users/<user>/screeners/<name>/``: a user's rule screen (drafts, versions)."""
        if user == SITE:
            raise ConfigurationError("site presets are not versioned user screens")
        user = validate_id("user", user)
        return self.root / "users" / user / SCREENERS / validate_id("screener", name)

    def screen_versions(self, user: str, name: str) -> list[int]:
        """The finalised versions of ``user``'s screen ``name``, ascending."""
        directory = self.screen_dir(user, name)
        if not directory.is_dir():
            return []
        found = (_VERSION_FILE.fullmatch(p.name) for p in directory.iterdir() if p.is_file())
        return sorted(int(m.group(1)) for m in found if m)

    def screen_schedule(self, user: str, name: str) -> str | None:
        doc = read_toml(self.screen_dir(user, name) / SCHEDULE) or {}
        value = doc.get("schedule")
        return value if isinstance(value, str) else None

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        if kind in ("defaults", "settings") and scope != SITE:
            return None
        if kind == SCREENERS and scope != SITE:
            versions = self.screen_versions(scope, name)
            if not versions:
                return None
            latest = read_toml(self.screen_dir(scope, name) / version_file(versions[-1]))
            return screen_document(latest or {}, self.screen_schedule(scope, name))
        return read_toml(self._path(scope, kind, name))

    def names(self, scope: str, kind: str) -> list[str]:
        if kind == "settings":
            if scope != SITE:
                return []
            return sorted(p.stem for p in (self.root / SITE).glob("*.toml") if p.stem != "defaults")
        if kind == "defaults":
            return ["defaults"] if scope == SITE and self._path(SITE, kind, "x").exists() else []
        if kind == SCREENERS and scope != SITE:
            base = self.root / "users" / validate_id("user", scope) / SCREENERS
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
        return self._docs.get((scope, kind, name))

    def names(self, scope: str, kind: str) -> list[str]:
        return sorted(n for (s, k, n) in self._docs if s == scope and k == kind)

    def users(self) -> list[str]:
        return sorted({s for (s, _, _) in self._docs if s != SITE})
