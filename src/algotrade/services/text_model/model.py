"""The text model a use case asks (ADR 0041, amended 2026-10-08): one call, system text and user
text in, a ``Completion`` out (the text, the model that answered, tokens, latency). The API
injects the adapter, or the chain of them (``chain.py``), that the site settings name
(``algotrade_sources.llm``); tests inject a fake with recorded answers. One that cannot answer
raises ``ModelUnavailableError`` (``core``); its message never carries a credential. ``names``
are the models that may answer, in the order tried (what a cache of their answers is keyed by)."""

from typing import Protocol

from algotrade.core.model.completion import Completion
from algotrade.core.model.errors import ModelUnavailableError

__all__ = ["Completion", "ModelUnavailableError", "TextModel"]


class TextModel(Protocol):
    @property
    def names(self) -> tuple[str, ...]:
        """The models that may answer, in chain order (one for a single adapter): what a cache
        of the answers is looked up by. The answer's own ``Completion.model`` is what it is
        stored under."""
        ...

    def complete(self, system: str, user: str) -> Completion:
        """The model's answer for ``system`` (the task and its facts) and ``user`` (the
        question); raises ``ModelUnavailableError`` when it cannot answer now."""
        ...
