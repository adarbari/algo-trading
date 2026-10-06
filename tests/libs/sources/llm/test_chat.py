"""``ChatCompletions`` (ADR 0041): the request an OpenAI-compatible endpoint gets (JSON mode,
temperature 0, the key only in a header), the content it returns, and every way it fails as a
``ModelUnavailableError`` that names the endpoint but never the key."""

import json

import pytest

from algotrade.core.model.errors import ModelUnavailableError
from algotrade_sources.framework.http import HttpError
from algotrade_sources.framework.registry import build_text_model
from algotrade_sources.llm.chat import ChatCompletions, content_of

BASE = "https://api.groq.com/openai/v1"


def answer(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


def test_asks_for_json_at_temperature_zero_and_returns_the_content() -> None:
    sent: list[tuple[str, bytes]] = []

    def transport(url: str, body: bytes) -> bytes:
        sent.append((url, body))
        return answer('{"criteria": []}')

    client = ChatCompletions(BASE + "/", "llama", transport, max_tokens=500)
    assert client.complete("task", "sentence") == '{"criteria": []}'
    ((url, body),) = sent
    assert url == BASE + "/chat/completions"
    request = json.loads(body)
    assert request["model"] == "llama" and request["temperature"] == 0
    assert request["max_tokens"] == 500
    assert request["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in request["messages"]] == ["system", "user"]
    assert request["messages"][0]["content"] == "task"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"not json", "not JSON"),
        (b'{"choices": []}', "no choices"),
        (b'{"choices": [{"message": {"content": "  "}}]}', "empty"),
        (b'{"error": {"message": "model not found", "code": 404}}', "model not found"),
    ],
)
def test_a_malformed_answer_is_unavailable(raw: bytes, message: str) -> None:
    with pytest.raises(ModelUnavailableError, match=message):
        content_of(raw, "llama at " + BASE)


def test_http_and_transport_failures_name_the_endpoint_never_the_key() -> None:
    def refused(url: str, body: bytes) -> bytes:
        raise HttpError(429, 7.0, b'{"error": "rate limited"}')

    with pytest.raises(ModelUnavailableError, match="HTTP 429") as exc:
        ChatCompletions(BASE, "llama", refused).complete("s", "u")
    assert "rate limited" in str(exc.value) and "Bearer" not in str(exc.value)

    def down(url: str, body: bytes) -> bytes:
        raise TimeoutError("timed out")

    with pytest.raises(ModelUnavailableError, match="timed out"):
        ChatCompletions(BASE, "llama", down).complete("s", "u")


def test_the_registry_builds_it_with_the_key_in_a_header_only() -> None:
    model = build_text_model(BASE, "llama", 30.0, 1000, "sk-secret")
    assert model.url == BASE + "/chat/completions" and model.max_tokens == 1000
    assert "sk-secret" not in model.url and "sk-secret" not in json.dumps(model.request("s", "u"))
    local = build_text_model("http://localhost:11434/v1", "llama3.1", 60.0, 2000, None)
    assert local.url == "http://localhost:11434/v1/chat/completions"
