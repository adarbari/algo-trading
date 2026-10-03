"""Read access to configuration documents (L3 site, L4 user). Only backends know layout."""

from collections.abc import Mapping
from typing import Any, Protocol

KINDS = ("defaults", "strategies", "selections", "settings", "features")


class ConfigStore(Protocol):
    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        """``scope`` is "site" or a user id; ``kind`` one of ``KINDS``. ``settings`` are site-only
        documents read by ingestion (``universe``, ``sources``, ``rollups``, ...); ``features``
        are expression-feature files (``site/features/<theme>.toml``, or a user's
        ``users/<id>/features/<theme>.toml``)."""
        ...

    def names(self, scope: str, kind: str) -> list[str]: ...

    def users(self) -> list[str]: ...

    def overrides(self, name: str) -> list[dict[str, str]]:
        """Curated site corrections (``config/site/overrides/<name>.csv``); [] if absent."""
        ...
