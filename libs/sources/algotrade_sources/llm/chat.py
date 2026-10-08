"""``ChatCompletions``: one request to an OpenAI-compatible ``/chat/completions`` endpoint
(ADR 0041). System text and user text in, a ``Completion`` out (the assistant's text, the model
that answered, the tokens the provider reported, how long it took), at temperature 0 and asking
for a JSON object, so the same prompt gets the same draft (as far as the provider allows). A
provider that is busy (429, 500, 502, 503, 504) or unreachable is retried ``retries`` times
with a doubling pause (``Retry-After`` wins); anything else, or the last failure, is a
``ModelUnavailableError`` (``core``) naming what went wrong, never the credential: the API
answers 503 with it."""

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ModelUnavailableError
from algotrade_sources.framework.http import HttpError, JsonTransport

COMPLETIONS = "/chat/completions"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ChatCompletions:
    """A client for one endpoint and model. ``transport`` POSTs a JSON body to a URL and
    returns the response body (``framework.http.json_post_transport`` with the credential
    header, or a fake in tests); ``pause`` waits between retries (``framework.http.pause``, or
    a recorder in tests): the registry supplies both, so this module never paces itself."""

    base_url: str
    model: str
    transport: JsonTransport
    pause: Callable[[float], None]
    max_tokens: int = 2000
    retries: int = 2  # attempts after the first, on a busy provider or a transport failure
    backoff_s: float = 3.0  # the wait before the first retry; doubled each time
    throttle_s: float = 20.0  # the wait after a 429 without Retry-After (a per-minute quota)
    extra: Mapping[str, Any] = field(default_factory=dict)  # provider fields sent as given
    provider: str = "default"  # the ``llm.toml`` id this client answers as
    clock: Callable[[], float] = time.monotonic

    @property
    def names(self) -> tuple[str, ...]:
        """The model this answers as: part of a cache key."""
        return (self.model,)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        """Every user may be answered by an unrestricted provider (the chain limits)."""
        return self.names

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + COMPLETIONS

    def request(self, system: str, user: str) -> dict[str, Any]:
        """The body sent (stable key order: a provider's prompt cache sees the same bytes)."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        # The configured extras follow the standard keys and never replace them.
        return body | {k: v for k, v in self.extra.items() if k not in body}

    def complete(self, system: str, user: str, *, tag: CallTag | None = None) -> Completion:
        started = self.clock()
        body = json.dumps(self.request(system, user), separators=(",", ":")).encode()
        where = f"{self.model} at {self.base_url}"
        attempts = self.retries + 1
        for attempt in range(attempts):
            last = attempt + 1 == attempts
            tried = f" (after {attempts} attempts)" if attempts > 1 else ""
            try:
                raw = self.transport(self.url, body)
            except HttpError as exc:
                detail = exc.body.decode("utf-8", "replace").strip()[:200]
                if exc.status not in RETRY_STATUSES or last:
                    tried = tried if exc.status in RETRY_STATUSES else ""
                    raise ModelUnavailableError(
                        f"{where}: HTTP {exc.status}{tried} {detail}"
                    ) from exc
                floor = self.throttle_s if exc.status == 429 else 0.0
                delay = exc.retry_after or max(floor, self.backoff_s * 2**attempt)
            except (OSError, TimeoutError) as exc:
                if last:
                    raise ModelUnavailableError(f"{where}{tried}: {exc}") from exc
                delay = self.backoff_s * 2**attempt
            else:
                text = content_of(raw, where)
                tokens = usage_of(raw)
                return Completion(text, self.model, self.provider, *tokens, self.clock() - started)
            self.pause(delay)
        raise AssertionError("unreachable")  # pragma: no cover


def content_of(raw: bytes, where: str) -> str:
    """``choices[0].message.content`` of a chat-completions response body."""
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ModelUnavailableError(f"{where}: the answer is not JSON") from exc
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        message = parsed["error"].get("message") or parsed["error"]
        raise ModelUnavailableError(f"{where}: {message}")
    try:
        choice = parsed["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelUnavailableError(
            f"{where}: no choices[0].message.content in the answer"
        ) from exc
    if isinstance(choice, dict) and choice.get("finish_reason") == "length":
        # A model that thinks before answering (Gemini 3.x) spends the budget on thinking first.
        raise ModelUnavailableError(
            f"{where}: the answer was cut off at answer_limit tokens (thinking counts against "
            "it on some models); raise answer_limit in config/site/llm.toml"
        )
    if not isinstance(content, str) or not content.strip():
        raise ModelUnavailableError(f"{where}: the answer is empty")
    return content


def usage_of(raw: bytes) -> tuple[int | None, int | None]:
    """``(usage.prompt_tokens, usage.completion_tokens)`` of a response body that
    ``content_of`` accepted; ``None`` for a count the provider left out (never ``0``)."""
    usage = json.loads(raw).get("usage")
    if not isinstance(usage, dict):
        return None, None
    return _count(usage.get("prompt_tokens")), _count(usage.get("completion_tokens"))


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
