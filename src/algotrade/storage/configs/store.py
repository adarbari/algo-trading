"""Read access to configuration documents (L3 site, L4 user). Only backends know layout."""

from collections.abc import Mapping
from typing import Any, Protocol

from algotrade.core.model.errors import ConfigurationError

KINDS = ("defaults", "strategies", "selections", "settings", "features", "screeners", "preferences")


class ConfigStore(Protocol):
    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        """``scope`` is "site" or a user id; ``kind`` one of ``KINDS``. ``settings`` are site-only
        documents read by ingestion (``universe``, ``sources``, ``rollups``, ...); ``features``
        are expression-feature files (``site/features/<theme>.toml``, or a user's
        ``users/<id>/features/<theme>.toml``). ``screeners`` are versioned rule screens:
        ``name`` loads the latest version (a user's with their schedule switch applied,
        ``screen_document``), ``name@N`` exactly version N; drafts are never loaded here."""
        ...

    def names(self, scope: str, kind: str) -> list[str]: ...

    def users(self) -> list[str]: ...

    def overrides(self, name: str) -> list[dict[str, str]]:
        """Curated site corrections (``config/site/overrides/<name>.csv``); [] if absent."""
        ...


def split_version(name: str) -> tuple[str, int | None]:
    """``"vrp@3"`` -> ``("vrp", 3)``; ``"vrp"`` -> ``("vrp", None)``; a bad version fails."""
    base, at, version = name.partition("@")
    if not at:
        return name, None
    if not version.isdigit() or len(version) > 9 or int(version) < 1:
        raise ConfigurationError(f"{name!r}: the version after @ is a positive integer")
    return base, int(version)


def screen_document(version: Mapping[str, Any], schedule: str | None) -> dict[str, Any]:
    """A user rule screen as the resolver sees it: the (immutable) finalised version with the
    separate schedule switch applied. ``schedule = None`` also clears a schedule inherited
    from the preset it extends (a user screen runs nightly only when its switch is on). The
    schedule says when a screen runs, not what it computes: it is not in the config hash."""
    return {**version, "schedule": schedule}


class OverlayConfigStore:
    """``base`` with some documents replaced (or added): how a document *would* resolve
    before it is written (authoring validates drafts and features through it)."""

    def __init__(
        self, base: ConfigStore, documents: Mapping[tuple[str, str, str], Mapping[str, Any]]
    ) -> None:
        self._base, self._docs = base, dict(documents)

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        found = self._docs.get((scope, kind, name))
        return found if found is not None else self._base.load(scope, kind, name)

    def names(self, scope: str, kind: str) -> list[str]:
        extra = {n for (s, k, n) in self._docs if (s, k) == (scope, kind)}
        return sorted({*self._base.names(scope, kind), *extra})

    def users(self) -> list[str]:
        return self._base.users()

    def overrides(self, name: str) -> list[dict[str, str]]:
        return self._base.overrides(name)
