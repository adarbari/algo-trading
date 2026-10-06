"""``ChatCompletions``: one request to an OpenAI-compatible ``/chat/completions`` endpoint
(ADR 0041). System text and user text in, the assistant's text out, at temperature 0 and asking
for a JSON object, so the same prompt gets the same draft (as far as the provider allows).
Anything but a well-formed answer is a ``ModelUnavailableError`` (``core``) naming what went
wrong, never the credential: the API answers 503 with it."""

import json
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.errors import ModelUnavailableError
from algotrade_sources.framework.http import HttpError, JsonTransport

COMPLETIONS = "/chat/completions"


@dataclass(frozen=True)
class ChatCompletions:
    """A client for one endpoint and model. ``transport`` POSTs a JSON body to a URL and
    returns the response body (``framework.http.json_post_transport`` with the credential
    header, or a fake in tests)."""

    base_url: str
    model: str
    transport: JsonTransport
    max_tokens: int = 2000

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + COMPLETIONS

    def request(self, system: str, user: str) -> dict[str, Any]:
        """The body sent (stable key order: a provider's prompt cache sees the same bytes)."""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }

    def complete(self, system: str, user: str) -> str:
        body = json.dumps(self.request(system, user), separators=(",", ":")).encode()
        try:
            raw = self.transport(self.url, body)
        except HttpError as exc:
            detail = exc.body.decode("utf-8", "replace").strip()[:200]
            where = f"{self.model} at {self.base_url}"
            raise ModelUnavailableError(f"{where}: HTTP {exc.status} {detail}") from exc
        except (OSError, TimeoutError) as exc:
            raise ModelUnavailableError(f"{self.model} at {self.base_url}: {exc}") from exc
        return content_of(raw, f"{self.model} at {self.base_url}")


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
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelUnavailableError(
            f"{where}: no choices[0].message.content in the answer"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise ModelUnavailableError(f"{where}: the answer is empty")
    return content
