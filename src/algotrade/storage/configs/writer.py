"""Write access to L4 user configs (ADR 0029): a rule screen's draft, its immutable finalised
versions and its schedule switch, and a user's expression-feature files.

``ConfigWriter`` extends the read-only ``ConfigStore`` protocol, so one object serves the
resolver (which sees each user screen's latest version) and the writes. Only
``services/authoring`` uses it (import-linter). Every write is user-scoped
(``config/users/<u>/``; never ``site``), keyed by validated ids, and atomic: a temp file in
the same directory, then a rename (drafts, schedules, features) or a hard link that fails if
the target exists (versions: a ``v<N>.toml`` is never overwritten). The memory writer has the
same semantics for tests; a DB backend can replace both under the protocol later.
"""

import json
import math
import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.storage.configs.files import (
    DRAFT,
    SCHEDULE,
    SCREENERS,
    SITE,
    FileConfigStore,
    MemoryConfigStore,
    read_toml,
    version_file,
)
from algotrade.storage.configs.store import ConfigStore, screen_document, split_version

MAX_DOCUMENT_BYTES = 64 * 1024  # a config is a few KiB; refuse anything far larger


class VersionExistsError(ConfigurationError):
    """A finalised version is immutable: ``v<N>`` already exists (a concurrent finalise)."""


class ConfigWriter(ConfigStore, Protocol):
    """Drafts, versions and schedules of ``user``'s rule screens; ``user``'s feature files."""

    def draft(self, user: str, name: str) -> dict[str, Any] | None: ...

    def save_draft(self, user: str, name: str, document: Mapping[str, Any]) -> None: ...

    def discard_draft(self, user: str, name: str) -> bool:
        """``True`` when there was a draft."""
        ...

    def versions(self, user: str, name: str) -> list[int]:
        """Finalised versions, ascending (the latest is the last)."""
        ...

    def version(self, user: str, name: str, version: int) -> dict[str, Any] | None: ...

    def add_version(self, user: str, name: str, version: int, document: Mapping[str, Any]) -> None:
        """Write ``v<version>``; ``VersionExistsError`` if it exists (never overwritten)."""
        ...

    def schedule(self, user: str, name: str) -> str | None: ...

    def set_schedule(self, user: str, name: str, schedule: str | None) -> None: ...

    def save_features(self, user: str, theme: str, document: Mapping[str, Any]) -> None:
        """Replace ``users/<user>/features/<theme>.toml``."""
        ...


# ----------------------------------------------------------------------------- TOML text
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def _key(key: Any) -> str:
    if not isinstance(key, str):
        raise ConfigurationError(f"config keys are strings, not {key!r}")
    return key if _BARE_KEY.fullmatch(key) else json.dumps(key)


def _float(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return repr(value)


def _scalar(value: Any) -> str | None:
    """TOML text of a scalar; ``None`` when ``value`` is not one."""
    text: str | None = None
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = _float(value)
    elif isinstance(value, str):
        text = json.dumps(value)  # a JSON string is a valid TOML basic string
    elif isinstance(value, (datetime, date)):
        text = value.isoformat()
    return text


def _value(value: Any, path: str) -> str:
    scalar = _scalar(value)
    if scalar is not None:
        return scalar
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(v, f"{path}[]") for v in value) + "]"
    if isinstance(value, Mapping):
        items = (f"{_key(k)} = {_value(v, f'{path}.{k}')}" for k, v in value.items())
        return "{ " + ", ".join(items) + " }" if value else "{}"
    raise ConfigurationError(f"{path}: {type(value).__name__} is not a config value")


def _table(document: Mapping[str, Any], prefix: str, out: list[str]) -> None:
    scalars = [(k, v) for k, v in document.items() if not isinstance(v, Mapping)]
    tables = [(k, v) for k, v in document.items() if isinstance(v, Mapping)]
    if prefix and (scalars or not tables):
        out.append(f"[{prefix}]")
    for key, value in scalars:
        if value is None:
            raise ConfigurationError(f"{prefix or 'document'}.{key}: TOML has no null")
        out.append(f"{_key(key)} = {_value(value, f'{prefix}.{key}')}")
    if scalars:
        out.append("")
    for key, value in tables:
        _table(value, f"{prefix}.{_key(key)}" if prefix else _key(key), out)


def toml_text(document: Mapping[str, Any]) -> str:
    """``document`` as TOML; fails closed unless it reads back identical (and is small)."""
    out: list[str] = []
    _table(document, "", out)
    text = "\n".join(out).rstrip("\n") + "\n"
    if len(text.encode()) > MAX_DOCUMENT_BYTES:
        raise ConfigurationError(f"config document larger than {MAX_DOCUMENT_BYTES} bytes")
    if _normalised(tomllib.loads(text)) != _normalised(document):
        raise ConfigurationError("config document does not round-trip through TOML")
    return text


def _normalised(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _normalised(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalised(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return value


def _user(user: str) -> str:
    if user == SITE:
        raise ConfigurationError("site configs change by PR, never through the writer")
    return validate_id("user", user)


def _version(version: int) -> int:
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ConfigurationError(f"invalid version {version!r}: a positive integer")
    return version


def _schedule_document(schedule: str | None) -> dict[str, Any]:
    return {} if schedule is None else {"schedule": schedule}


# ----------------------------------------------------------------------------- files
class FileConfigWriter(FileConfigStore):
    """The TOML files under the config root (layout: ``storage/configs/files.py``)."""

    def _inside_user(self, user: str, path: Path) -> Path:
        base = self.root / "users" / _user(user)
        if os.path.commonpath([base, path]) != str(base):  # ids are validated; belt and braces
            raise ConfigurationError(f"{path}: outside {base}")
        return path

    def _write(self, user: str, path: Path, text: str, *, exclusive: bool = False) -> None:
        path = self._inside_user(user, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            if exclusive:
                try:
                    os.link(tmp, path)  # atomic, and fails if the version exists
                except FileExistsError:
                    message = f"{path.name} exists: versions are immutable"
                    raise VersionExistsError(message) from None
            else:
                tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)

    def draft(self, user: str, name: str) -> dict[str, Any] | None:
        return read_toml(self.screen_dir(_user(user), name) / DRAFT)

    def save_draft(self, user: str, name: str, document: Mapping[str, Any]) -> None:
        self._write(user, self.screen_dir(_user(user), name) / DRAFT, toml_text(document))

    def discard_draft(self, user: str, name: str) -> bool:
        path = self._inside_user(user, self.screen_dir(_user(user), name) / DRAFT)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    def versions(self, user: str, name: str) -> list[int]:
        return self.screen_versions(_user(user), name)

    def version(self, user: str, name: str, version: int) -> dict[str, Any] | None:
        return read_toml(self.screen_dir(_user(user), name) / version_file(_version(version)))

    def add_version(self, user: str, name: str, version: int, document: Mapping[str, Any]) -> None:
        path = self.screen_dir(_user(user), name) / version_file(_version(version))
        self._write(user, path, toml_text(document), exclusive=True)

    def schedule(self, user: str, name: str) -> str | None:
        return self.screen_schedule(_user(user), name)

    def set_schedule(self, user: str, name: str, schedule: str | None) -> None:
        path = self.screen_dir(_user(user), name) / SCHEDULE
        self._write(user, path, toml_text(_schedule_document(schedule)))

    def save_features(self, user: str, theme: str, document: Mapping[str, Any]) -> None:
        path = (
            self.root / "users" / _user(user) / "features" / f"{validate_id('theme', theme)}.toml"
        )
        self._write(user, path, toml_text(document))


# ----------------------------------------------------------------------------- memory
def _copy(document: Mapping[str, Any]) -> dict[str, Any]:
    return tomllib.loads(toml_text(document))  # what a file round trip would give back


class MemoryConfigWriter(MemoryConfigStore):
    """The memory store plus drafts, versions and schedules (tests)."""

    def __init__(
        self,
        documents: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
        overrides: Mapping[str, list[dict[str, str]]] | None = None,
    ) -> None:
        super().__init__(documents or {}, overrides)
        self._drafts: dict[tuple[str, str], dict[str, Any]] = {}
        self._versions: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
        self._schedules: dict[tuple[str, str], str] = {}

    def _screen(self, user: str, name: str) -> tuple[str, str]:
        return _user(user), validate_id("screener", name)

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        if kind != SCREENERS or scope == SITE:
            return super().load(scope, kind, name)
        name, pinned = split_version(name)
        versions = self._versions.get((scope, name))
        if not versions:
            return None
        if pinned is not None:
            return versions.get(pinned)
        return screen_document(versions[max(versions)], self._schedules.get((scope, name)))

    def names(self, scope: str, kind: str) -> list[str]:
        if kind != SCREENERS or scope == SITE:
            return super().names(scope, kind)
        return sorted(n for (u, n), v in self._versions.items() if u == scope and v)

    def users(self) -> list[str]:
        return sorted({*super().users(), *(u for u, _ in self._versions)})

    def draft(self, user: str, name: str) -> dict[str, Any] | None:
        found = self._drafts.get(self._screen(user, name))
        return None if found is None else _copy(found)

    def save_draft(self, user: str, name: str, document: Mapping[str, Any]) -> None:
        self._drafts[self._screen(user, name)] = _copy(document)

    def discard_draft(self, user: str, name: str) -> bool:
        return self._drafts.pop(self._screen(user, name), None) is not None

    def versions(self, user: str, name: str) -> list[int]:
        return sorted(self._versions.get(self._screen(user, name), {}))

    def version(self, user: str, name: str, version: int) -> dict[str, Any] | None:
        found = self._versions.get(self._screen(user, name), {}).get(_version(version))
        return None if found is None else _copy(found)

    def add_version(self, user: str, name: str, version: int, document: Mapping[str, Any]) -> None:
        versions = self._versions.setdefault(self._screen(user, name), {})
        if _version(version) in versions:
            raise VersionExistsError(f"v{version} exists: versions are immutable")
        versions[version] = _copy(document)

    def schedule(self, user: str, name: str) -> str | None:
        return self._schedules.get(self._screen(user, name))

    def set_schedule(self, user: str, name: str, schedule: str | None) -> None:
        key = self._screen(user, name)
        if schedule is None:
            self._schedules.pop(key, None)
        else:
            self._schedules[key] = schedule

    def save_features(self, user: str, theme: str, document: Mapping[str, Any]) -> None:
        self._docs[(_user(user), "features", validate_id("theme", theme))] = _copy(document)
