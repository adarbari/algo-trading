"""``ChatCompletions`` (ADR 0041): the request an OpenAI-compatible endpoint gets (JSON mode,
temperature 0, the key only in a header), the content it returns, and every way it fails as a
``ModelUnavailableError`` that names the endpoint but never the key."""

import json

import pytest

from algotrade.core.model.errors import ModelUnavailableError
from algotrade_sources.framework.http import HttpError, pause
from algotrade_sources.framework.registry import build_text_model
from algotrade_sources.llm.chat import ChatCompletions, content_of

BASE = "https://api.groq.com/openai/v1"


def NO_WAIT(seconds: float) -> None:  # noqa: N802 - a constant-like pause for tests
    pass


def answer(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


def test_asks_for_json_at_temperature_zero_and_returns_the_content() -> None:
    sent: list[tuple[str, bytes]] = []

    def transport(url: str, body: bytes) -> bytes:
        sent.append((url, body))
        return answer('{"criteria": []}')

    client = ChatCompletions(BASE + "/", "llama", transport, NO_WAIT, max_tokens=500)
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
        (
            b'{"choices": [{"finish_reason": "length", "message": {"content": "{\\"crit"}}]}',
            "cut off at answer_limit",
        ),
    ],
)
def test_a_malformed_answer_is_unavailable(raw: bytes, message: str) -> None:
    with pytest.raises(ModelUnavailableError, match=message):
        content_of(raw, "llama at " + BASE)


def test_http_and_transport_failures_name_the_endpoint_never_the_key() -> None:
    def refused(url: str, body: bytes) -> bytes:
        raise HttpError(401, None, b'{"error": "bad key sk-secret"}')

    with pytest.raises(ModelUnavailableError, match="HTTP 401") as exc:
        ChatCompletions(BASE, "llama", refused, NO_WAIT).complete("s", "u")
    assert "bad key" in str(exc.value) and "Bearer" not in str(exc.value)

    def down(url: str, body: bytes) -> bytes:
        raise TimeoutError("timed out")

    with pytest.raises(ModelUnavailableError, match="timed out"):
        ChatCompletions(BASE, "llama", down, NO_WAIT, retries=0).complete("s", "u")


def test_a_busy_provider_is_retried_with_a_doubling_pause_or_retry_after() -> None:
    calls: list[int] = []
    slept: list[float] = []

    def busy_then_ok(url: str, body: bytes) -> bytes:
        calls.append(len(calls))
        if len(calls) == 1:
            raise HttpError(503, None, b'{"error": {"message": "high demand"}}')
        if len(calls) == 2:
            raise HttpError(429, 7.0, b"slow down")
        return answer('{"criteria": []}')

    client = ChatCompletions(BASE, "llama", busy_then_ok, slept.append, retries=2)
    assert client.complete("s", "u") == '{"criteria": []}'
    assert len(calls) == 3 and slept == [3.0, 7.0]  # back-off, then the Retry-After header


def test_retries_run_out_and_say_so() -> None:
    slept: list[float] = []

    def always_busy(url: str, body: bytes) -> bytes:
        raise HttpError(503, None, b"high demand")

    with pytest.raises(ModelUnavailableError, match=r"HTTP 503 \(after 3 attempts\) high demand"):
        ChatCompletions(BASE, "llama", always_busy, slept.append, retries=2).complete("s", "u")
    assert slept == [3.0, 6.0]

    def dropped(url: str, body: bytes) -> bytes:
        raise ConnectionResetError("reset")

    with pytest.raises(ModelUnavailableError, match=r"\(after 2 attempts\): reset"):
        ChatCompletions(BASE, "llama", dropped, slept.append, retries=1).complete("s", "u")


def test_a_client_error_is_not_retried() -> None:
    calls: list[int] = []

    def bad_request(url: str, body: bytes) -> bytes:
        calls.append(1)
        raise HttpError(400, None, b"bad model")

    with pytest.raises(ModelUnavailableError, match="HTTP 400 bad model"):
        ChatCompletions(BASE, "llama", bad_request, NO_WAIT, retries=2).complete("s", "u")
    assert len(calls) == 1


def test_the_registry_builds_it_with_the_key_in_a_header_only() -> None:
    model = build_text_model(BASE, "llama", 30.0, 1000, "sk-secret", retries=3)
    assert model.url == BASE + "/chat/completions" and model.max_tokens == 1000
    assert model.retries == 3 and build_text_model(BASE, "m", 1.0, 1, None).retries == 2
    assert model.pause is pause
    assert "sk-secret" not in model.url and "sk-secret" not in json.dumps(model.request("s", "u"))
    local = build_text_model("http://localhost:11434/v1", "llama3.1", 60.0, 2000, None)
    assert local.url == "http://localhost:11434/v1/chat/completions"
