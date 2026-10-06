"""The text model a draft is asked from (ADR 0041): one call, system text and user text in,
the assistant's text out. The API injects the adapter the site settings name
(``algotrade_sources.llm``); tests inject a fake with recorded answers. One that cannot answer
raises ``ModelUnavailableError`` (``core``); its message never carries a credential."""

from typing import Protocol

from algotrade.core.model.errors import ModelUnavailableError

__all__ = ["ModelUnavailableError", "TextModel"]


class TextModel(Protocol):
    def complete(self, system: str, user: str) -> str:
        """The model's text for ``system`` (the task and the catalogue) and ``user`` (the
        sentence); raises ``ModelUnavailableError`` when it cannot answer now."""
        ...
