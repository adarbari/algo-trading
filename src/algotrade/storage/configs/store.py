"""Read access to configuration documents (L3 site, L4 user), including a user's rule-screen
drafts and finalised versions (written only through ``writer.ConfigWriter``). Only backends
know layout."""

from collections.abc import Mapping
from typing import Any, Protocol

from algotrade.core.model.errors import ConfigurationError

KINDS = (
    "defaults",
    "strategies",
    "selections",
    "settings",
    "features",
    "field_guide",
    "regime",
    "guide",
    "guide_playbooks",
    "events",
    "edges",
    "screeners",
    "preferences",
    "identity",
    "evaluation",
)


class ConfigStore(Protocol):
    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        """``scope`` is "site" or a user id; ``kind`` one of ``KINDS``. ``settings`` are site-only
        documents read by ingestion (``universe``, ``sources``, ``rollups``, ...); ``features``
        are expression-feature files (``site/features/<theme>.toml``, or a user's
        ``users/<id>/features/<theme>.toml``); ``field_guide`` the site's field guide files
        (``site/field_guide/<theme>.toml``, site-only); ``regime`` the site's regime reference
        files (``site/regime/{cards,episodes}.toml``, ADR 0047, site-only); ``events`` the site's
        event-sensitivity files (``site/events/{scope,releases}.toml``, ADR 0050, site-only);
        ``guide`` the Guide's own files (``site/guide/sections.toml``, ADR 0051, site-only);
        ``guide_playbooks`` its playbook prose (``site/guide/playbooks/<id>.toml``, site-only);
        ``edges`` the edge documents (``site/edges/<id>.toml``, or a user's draft under
        ``users/<id>/edges/``, ADR 0053).
        ``preferences``, ``evaluation`` (the user's edge-evaluation split, ADR 0053) and
        ``identity`` are one file per user (``users/<id>/<kind>.toml``; identity holds the
        sign-in email, ADR 0040), never the site's. ``screeners`` are versioned rule screens:
        ``name`` loads the latest version, ``name@N`` exactly version N; drafts are never
        loaded here."""
        ...

    def names(self, scope: str, kind: str) -> list[str]: ...

    def users(self) -> list[str]: ...

    def overrides(self, name: str) -> list[dict[str, str]]:
        """Curated site corrections (``config/site/overrides/<name>.csv``); [] if absent."""
        ...

    # A user's rule screens as stored (ADR 0029), read-only: ``ConfigWriter`` writes them.
    def draft(self, user: str, name: str) -> dict[str, Any] | None:
        """``user``'s working copy of the screen ``name`` (never loaded to run); None: none."""
        ...

    def drafts(self, user: str) -> list[str]:
        """The names of ``user``'s screens that have a draft (finalised or not), sorted."""
        ...

    def versions(self, user: str, name: str) -> list[int]:
        """Finalised versions, ascending (the latest is the last)."""
        ...

    def version(self, user: str, name: str, version: int) -> dict[str, Any] | None: ...


def split_version(name: str) -> tuple[str, int | None]:
    """``"vrp@3"`` -> ``("vrp", 3)``; ``"vrp"`` -> ``("vrp", None)``; a bad version fails."""
    base, at, version = name.partition("@")
    if not at:
        return name, None
    if not version.isdigit() or len(version) > 9 or int(version) < 1:
        raise ConfigurationError(f"{name!r}: the version after @ is a positive integer")
    return base, int(version)


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

    def draft(self, user: str, name: str) -> dict[str, Any] | None:
        return self._base.draft(user, name)

    def drafts(self, user: str) -> list[str]:
        return self._base.drafts(user)

    def versions(self, user: str, name: str) -> list[int]:
        return self._base.versions(user, name)

    def version(self, user: str, name: str, version: int) -> dict[str, Any] | None:
        return self._base.version(user, name, version)
