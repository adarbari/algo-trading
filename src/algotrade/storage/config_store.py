"""Read access to configuration documents (L3 site, L4 user). Only backends know layout."""

from collections.abc import Mapping
from typing import Any, Protocol

KINDS = ("defaults", "strategies", "selections")


class ConfigStore(Protocol):
    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None:
        """``scope`` is "site" or a user id; ``kind`` one of ``KINDS``."""
        ...

    def names(self, scope: str, kind: str) -> list[str]: ...

    def users(self) -> list[str]: ...
