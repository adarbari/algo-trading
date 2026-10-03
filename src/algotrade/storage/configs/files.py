"""TOML config files. Layout under the config root (``ALGOTRADE_CONFIG_DIR``, default ./config)::

site/defaults.toml                         L3 defaults (screening, backtest)
site/<name>.toml                           L3 site settings (kind ``settings``)
site/features/<theme>.toml                 L3 expression features (kind ``features``)
site/presets/strategies/<id>.toml          L3 shared strategy / screener configs
site/presets/selections/<id>.toml          L3 shared selections
users/<user>/strategies/<id>.toml          L4 (git-ignored locally)
users/<user>/selections/<id>.toml
users/<user>/features/<theme>.toml         L4 expression features (always virtual)
"""

import csv
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.storage.configs.store import KINDS

SITE = "site"


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

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        if kind in ("defaults", "settings") and scope != SITE:
            return None
        path = self._path(scope, kind, name)
        if not path.exists():
            return None
        try:
            return tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"{path}: invalid TOML: {exc}") from exc

    def names(self, scope: str, kind: str) -> list[str]:
        if kind == "settings":
            if scope != SITE:
                return []
            return sorted(p.stem for p in (self.root / SITE).glob("*.toml") if p.stem != "defaults")
        if kind == "defaults":
            return ["defaults"] if scope == SITE and self._path(SITE, kind, "x").exists() else []
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
