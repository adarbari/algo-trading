"""Write access to L4 user configs (ADR 0029): a rule screen's draft, its immutable finalised
versions, deleting a screen (archived, never erased), and a user's expression-feature files.

``ConfigWriter`` extends the read-only ``ConfigStore`` protocol, so one object serves the
resolver (which sees each user screen's latest version) and the writes. Only
``services/authoring`` uses it (import-linter). Every write is user-scoped
(``config/users/<u>/``; never ``site``), keyed by validated ids, and atomic: a temp file in
the same directory, then a rename (drafts, features) or a hard link that fails if
the target exists (versions: a ``v<N>.toml`` is never overwritten). Deleting a screen moves its
whole folder (draft and versions) to ``users/<u>/archive/screeners/<id>-<UTC stamp>/`` in one
rename: it leaves the list and the nightly, its past runs stay attributable to the archived
versions, and it can be moved back by hand. A deleted id is never reused (``was_deleted``):
runs, ideas and views are keyed by the id, so a new screen of that name would inherit them.
The memory writer has the same semantics for tests; a DB backend can replace both under the
protocol later.
"""

import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.storage.configs.files import (
    DRAFT,
    SCREENERS,
    SITE,
    FileConfigStore,
    MemoryConfigStore,
    valid_version,
    version_file,
)
from algotrade.storage.configs.store import ConfigStore, split_version
from algotrade.storage.configs.toml_text import toml_text

USER_DOCUMENT_KINDS = ("edges",)  # one TOML document per id, replaced whole, archived on delete


class VersionExistsError(ConfigurationError):
    """A finalised version is immutable: ``v<N>`` already exists (a concurrent finalise)."""


class ConfigWriter(ConfigStore, Protocol):
    """Writes drafts and versions of ``user``'s rule screens (read through ``ConfigStore``);
    ``user``'s feature files and preferences."""

    def save_draft(self, user: str, name: str, document: Mapping[str, Any]) -> None: ...

    def discard_draft(self, user: str, name: str) -> bool:
        """``True`` when there was a draft."""
        ...

    def add_version(self, user: str, name: str, version: int, document: Mapping[str, Any]) -> None:
        """Write ``v<version>``; ``VersionExistsError`` if it exists (never overwritten)."""
        ...

    def delete_screen(self, user: str, name: str, at: datetime) -> bool:
        """Archive the screen (draft and versions) as of ``at``; ``True`` when there was one."""
        ...

    def was_deleted(self, user: str, name: str) -> bool:
        """``user`` once deleted a screen ``name`` (it is in the archive)."""
        ...

    def save_features(self, user: str, theme: str, document: Mapping[str, Any]) -> None:
        """Replace ``users/<user>/features/<theme>.toml``."""
        ...

    def save_preferences(self, user: str, document: Mapping[str, Any]) -> None:
        """Replace ``users/<user>/preferences.toml``."""
        ...

    def save_user_document(
        self, user: str, kind: str, name: str, document: Mapping[str, Any]
    ) -> None:
        """Replace ``users/<user>/<kind>/<name>.toml`` for a kind in ``USER_DOCUMENT_KINDS``."""
        ...

    def archive_user_document(self, user: str, kind: str, name: str, at: datetime) -> bool:
        """Move that document to ``users/<user>/archive/<kind>/<name>-<stamp>.toml`` (never
        erased); ``True`` when there was one."""
        ...

    def was_archived(self, user: str, kind: str, name: str) -> bool:
        """``user`` once archived a document ``name`` of ``kind``: its id is not reused."""
        ...


def _user(user: str) -> str:
    if user == SITE:
        raise ConfigurationError("site configs change by PR, never through the writer")
    return validate_id("user", user)


def archive_name(name: str, at: datetime, id_kind: str = "screener") -> str:
    """``<id>-<YYYYmmddTHHMMSSffffffZ>``: an archived screen's folder (``at`` is UTC-aware)."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ConfigurationError("an archive time must be timezone-aware (UTC)")
    return f"{validate_id(id_kind, name)}-{at.astimezone(UTC):%Y%m%dT%H%M%S%fZ}"


def _archived_as(name: str, id_kind: str = "screener") -> re.Pattern[str]:
    """Matches the archive names of ``name`` (and no other id that starts with it)."""
    return re.compile(rf"{re.escape(validate_id(id_kind, name))}-\d{{8}}T\d{{12}}Z")


def _document_kind(kind: str) -> str:
    if kind not in USER_DOCUMENT_KINDS:
        raise ConfigurationError(f"{kind!r} is not a kind a user document is written for")
    return kind


def _document_id_kind(kind: str) -> str:
    return _document_kind(kind).removesuffix("s")  # "edges" -> the id kind "edge"


def _document_id(kind: str, name: str) -> str:
    return validate_id(_document_id_kind(kind), name)


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

    def save_draft(self, user: str, name: str, document: Mapping[str, Any]) -> None:
        self._write(user, self.screen_dir(_user(user), name) / DRAFT, toml_text(document))

    def discard_draft(self, user: str, name: str) -> bool:
        path = self._inside_user(user, self.screen_dir(_user(user), name) / DRAFT)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    def add_version(self, user: str, name: str, version: int, document: Mapping[str, Any]) -> None:
        path = self.screen_dir(_user(user), name) / version_file(valid_version(version))
        self._write(user, path, toml_text(document), exclusive=True)

    def delete_screen(self, user: str, name: str, at: datetime) -> bool:
        scope = _user(user)
        source = self._inside_user(user, self.screen_dir(scope, name))
        if not source.is_dir():
            return False
        target = self._inside_user(
            user, self.root / "users" / scope / "archive" / SCREENERS / archive_name(name, at)
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)  # atomic on one filesystem; fails if the target exists
        return True

    def was_deleted(self, user: str, name: str) -> bool:
        base = self.root / "users" / _user(user) / "archive" / SCREENERS
        pattern = _archived_as(name)
        return base.is_dir() and any(pattern.fullmatch(p.name) for p in base.iterdir())

    def save_features(self, user: str, theme: str, document: Mapping[str, Any]) -> None:
        path = (
            self.root / "users" / _user(user) / "features" / f"{validate_id('theme', theme)}.toml"
        )
        self._write(user, path, toml_text(document))

    def save_preferences(self, user: str, document: Mapping[str, Any]) -> None:
        path = self.root / "users" / _user(user) / "preferences.toml"
        self._write(user, path, toml_text(document))

    def _document_path(self, user: str, kind: str, name: str) -> Path:
        folder = self.root / "users" / _user(user) / _document_kind(kind)
        return folder / f"{_document_id(kind, name)}.toml"

    def save_user_document(
        self, user: str, kind: str, name: str, document: Mapping[str, Any]
    ) -> None:
        self._write(user, self._document_path(user, kind, name), toml_text(document))

    def archive_user_document(self, user: str, kind: str, name: str, at: datetime) -> bool:
        current = self._inside_user(user, self._document_path(user, kind, name))
        if not current.is_file():
            return False
        stamped = f"{archive_name(name, at, _document_id_kind(kind))}.toml"
        target = self._inside_user(
            user, self.root / "users" / _user(user) / "archive" / kind / stamped
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        current.rename(target)  # atomic on one filesystem; fails if the target exists
        return True

    def was_archived(self, user: str, kind: str, name: str) -> bool:
        base = self.root / "users" / _user(user) / "archive" / _document_kind(kind)
        pattern = _archived_as(name, _document_id_kind(kind))
        return base.is_dir() and any(pattern.fullmatch(p.stem) for p in base.iterdir())


# ----------------------------------------------------------------------------- memory
def _copy(document: Mapping[str, Any]) -> dict[str, Any]:
    return tomllib.loads(toml_text(document))  # what a file round trip would give back


class MemoryConfigWriter(MemoryConfigStore):
    """The memory store plus drafts and versions (tests)."""

    def __init__(
        self,
        documents: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
        overrides: Mapping[str, list[dict[str, str]]] | None = None,
    ) -> None:
        super().__init__(documents or {}, overrides)
        self._drafts: dict[tuple[str, str], dict[str, Any]] = {}
        self._versions: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
        # (user, archive name) -> (draft, versions) of a deleted screen
        self.archived: dict[tuple[str, str], tuple[dict[str, Any] | None, dict[int, Any]]] = {}
        # (user, kind, archive name) -> a document archived by archive_user_document
        self.archived_documents: dict[tuple[str, str, str], dict[str, Any]] = {}

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
        return versions[max(versions)]

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

    def drafts(self, user: str) -> list[str]:
        return sorted(n for (u, n) in self._drafts if u == _user(user))

    def versions(self, user: str, name: str) -> list[int]:
        return sorted(self._versions.get(self._screen(user, name), {}))

    def version(self, user: str, name: str, version: int) -> dict[str, Any] | None:
        found = self._versions.get(self._screen(user, name), {}).get(valid_version(version))
        return None if found is None else _copy(found)

    def add_version(self, user: str, name: str, version: int, document: Mapping[str, Any]) -> None:
        versions = self._versions.setdefault(self._screen(user, name), {})
        if valid_version(version) in versions:
            raise VersionExistsError(f"v{version} exists: versions are immutable")
        versions[version] = _copy(document)

    def delete_screen(self, user: str, name: str, at: datetime) -> bool:
        key = self._screen(user, name)
        draft, versions = self._drafts.pop(key, None), self._versions.pop(key, {})
        if draft is None and not versions:
            return False
        self.archived[(key[0], archive_name(key[1], at))] = (draft, versions)
        return True

    def was_deleted(self, user: str, name: str) -> bool:
        pattern = _archived_as(name)
        return any(u == _user(user) and pattern.fullmatch(n) for u, n in self.archived)

    def save_features(self, user: str, theme: str, document: Mapping[str, Any]) -> None:
        self._docs[(_user(user), "features", validate_id("theme", theme))] = _copy(document)

    def save_preferences(self, user: str, document: Mapping[str, Any]) -> None:
        self._docs[(_user(user), "preferences", "preferences")] = _copy(document)

    def save_user_document(
        self, user: str, kind: str, name: str, document: Mapping[str, Any]
    ) -> None:
        self._docs[(_user(user), _document_kind(kind), _document_id(kind, name))] = _copy(document)

    def archive_user_document(self, user: str, kind: str, name: str, at: datetime) -> bool:
        key = (_user(user), _document_kind(kind), _document_id(kind, name))
        found = self._docs.pop(key, None)
        if found is None:
            return False
        stamped = archive_name(name, at, _document_id_kind(kind))
        self.archived_documents[(key[0], key[1], stamped)] = dict(found)
        return True

    def was_archived(self, user: str, kind: str, name: str) -> bool:
        pattern = _archived_as(name, _document_id_kind(kind))
        return any(
            u == _user(user) and k == _document_kind(kind) and pattern.fullmatch(n)
            for u, k, n in self.archived_documents
        )
