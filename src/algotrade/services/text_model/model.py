"""The text model a use case asks (ADR 0041, amended 2026-10-08): one call, system text and user
text in, a ``Completion`` out (the text, the model that answered, tokens, latency). The API
injects the adapter, or the chain of them (``chain.py``), that the site settings name
(``algotrade_sources.llm``); tests inject a fake with recorded answers. One that cannot answer
raises ``ModelUnavailableError`` (``core``); its message never carries a credential. ``names``
are the models that may answer, in the order tried (what a cache of their answers is keyed by);
``names_for(user)`` the ones that may answer that user (a provider can be limited to some)."""

from typing import Protocol

from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ModelUnavailableError

__all__ = ["CallTag", "Completion", "ModelUnavailableError", "TextModel"]


class TextModel(Protocol):
    @property
    def names(self) -> tuple[str, ...]:
        """The models that may answer, in chain order (one for a single adapter): what a cache
        of the answers is looked up by. The answer's own ``Completion.model`` is what it is
        stored under."""
        ...

    def names_for(self, user: str | None) -> tuple[str, ...]:
        """``names`` limited to the models ``user`` may be answered by (``None``: no one's)."""
        ...

    def complete(self, system: str, user: str, *, tag: CallTag | None = None) -> Completion:
        """The model's answer for ``system`` (the task and its facts) and ``user`` (the
        question), asked as ``tag`` (who and why); raises ``ModelUnavailableError`` when it
        cannot answer now."""
        ...
