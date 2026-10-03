"""TOML config files. Layout under the config root (``ALGOTRADE_CONFIG_DIR``, default ./config)::

site/defaults.toml                         L3 defaults (screening, backtest)
site/presets/strategies/<id>.toml          L3 shared strategy / screener configs
site/presets/selections/<id>.toml          L3 shared selections
users/<user>/strategies/<id>.toml          L4 (git-ignored locally)
users/<user>/selections/<id>.toml
"""

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from algotrade.core.errors import ConfigurationError
from algotrade.core.ids import validate_id
from algotrade.storage.config_store import KINDS

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
            return self.root / SITE / "presets" / kind / f"{validate_id(kind, name)}.toml"
        user = validate_id("user", scope)
        return self.root / "users" / user / kind / f"{validate_id(kind, name)}.toml"

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        if kind == "defaults" and scope != SITE:
            return None
        path = self._path(scope, kind, name)
        if not path.exists():
            return None
        try:
            return tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"{path}: invalid TOML: {exc}") from exc

    def names(self, scope: str, kind: str) -> list[str]:
        if kind == "defaults":
            return ["defaults"] if scope == SITE and self._path(SITE, kind, "x").exists() else []
        directory = self._path(scope, kind, "x").parent
        return sorted(p.stem for p in directory.glob("*.toml")) if directory.exists() else []

    def users(self) -> list[str]:
        base = self.root / "users"
        return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []


class MemoryConfigStore:
    """Dict-backed store for tests: ``{(scope, kind, name): document}``."""

    def __init__(self, documents: Mapping[tuple[str, str, str], Mapping[str, Any]]) -> None:
        self._docs = dict(documents)

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        return self._docs.get((scope, kind, name))

    def names(self, scope: str, kind: str) -> list[str]:
        return sorted(n for (s, k, n) in self._docs if s == scope and k == kind)

    def users(self) -> list[str]:
        return sorted({s for (s, _, _) in self._docs if s != SITE})
