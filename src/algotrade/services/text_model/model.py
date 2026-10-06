"""The text model a use case asks (ADR 0041): one call, system text and user text in, the
assistant's text out. The API injects the adapter the site settings name
(``algotrade_sources.llm``); tests inject a fake with recorded answers. One that cannot answer
raises ``ModelUnavailableError`` (``core``); its message never carries a credential. ``name``
is the model's identity (what a cache of its answers is keyed by)."""

from typing import Protocol

from algotrade.core.model.errors import ModelUnavailableError

__all__ = ["ModelUnavailableError", "TextModel"]


class TextModel(Protocol):
    @property
    def name(self) -> str:
        """The model this answers as (``llm.toml`` ``model``): part of a cache key."""
        ...

    def complete(self, system: str, user: str) -> str:
        """The model's text for ``system`` (the task and its facts) and ``user`` (the question);
        raises ``ModelUnavailableError`` when it cannot answer now."""
        ...
