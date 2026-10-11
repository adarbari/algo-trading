"""The text model a use case asks (ADR 0041, amended 2026-10-08): one call, system text and user
text in, a ``Completion`` out (the text, the model that answered, tokens, latency). The API
injects the adapter, or the chain of them (``chain.py``), that the site settings name
(``algotrade_sources.llm``); tests inject a fake with recorded answers. One that cannot answer
raises ``ModelUnavailableError`` (``core``); its message never carries a credential. ``names``
are the models that may answer, in the order tried (what a cache of their answers is keyed by);
``names_for(user)`` the ones that may answer that user (a provider can be limited to some)."""

import logging
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ModelUnavailableError

__all__ = ["CallTag", "Completion", "ModelUnavailableError", "TextModel", "reject_answer"]


log = logging.getLogger(__name__)


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

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: CallTag | None = None,
        schema: Mapping[str, Any] | None = None,
        accept: Callable[[str], None] | None = None,
    ) -> Completion:
        """The model's answer for ``system`` (the task and its facts) and ``user`` (the
        question), asked as ``tag`` (who and why); raises ``ModelUnavailableError`` when it
        cannot answer now. ``schema``: the JSON Schema the answer should fit, sent to a provider
        configured to take one (``structured = "json_schema"``) and ignored by the others, so the
        caller still checks the answer. ``accept``: the caller's check of the answer text; it
        raises ``ModelUnavailableError`` (``InvalidAnswerError``) for one it cannot use. A chain
        then repairs once and falls through to its next provider; a single adapter lets the error
        propagate."""
        ...


def reject_answer(
    model: TextModel,
    tag: CallTag | None,
    completion: Completion,
    reason: str,
    user_text: str,
    prompt_chars: int | None = None,
) -> None:
    """Tell ``model`` that its ``completion`` could not be used (``reason``; ``user_text`` the
    prompt it answered, ``prompt_chars`` the length of system + user). The chain
    (``FallbackTextModel.reject``) logs it in the usage log as a ``rejected`` row with the raw
    answer (ADR 0058). A model without ``reject`` (an adapter used alone, a test fake) ignores
    it. Never raises."""
    reject = getattr(model, "reject", None)
    if reject is None:
        return
    try:
        reject(tag, completion, reason, user_text, prompt_chars)
    except Exception:  # recording a rejection must never mask the error being raised
        log.exception("the text model could not record a rejected answer")
