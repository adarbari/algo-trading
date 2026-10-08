"""``ChatCompletions`` (ADR 0041): the request an OpenAI-compatible endpoint gets (JSON mode,
temperature 0, the key only in a header), the content it returns, and every way it fails as a
``ModelUnavailableError`` that names the endpoint but never the key."""

import json

import pytest

from algotrade.core.model.errors import ModelUnavailableError
from algotrade_sources.framework.http import HttpError, pause
from algotrade_sources.framework.registry import build_text_model
from algotrade_sources.llm.chat import ChatCompletions, content_of
from tests.helpers.payloads.llm import anthropic_answer, gemini_answer

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
    done = client.complete("task", "sentence")
    assert done.text == '{"criteria": []}' and done.model == "llama" and done.provider == "default"
    ((url, body),) = sent
    assert url == BASE + "/chat/completions"
    request = json.loads(body)
    assert request["model"] == "llama" and request["temperature"] == 0
    assert request["max_tokens"] == 500
    assert request["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in request["messages"]] == ["system", "user"]
    assert request["messages"][0]["content"] == "task"
    assert "reasoning_effort" not in request


def test_extra_request_fields_are_sent_but_cannot_override_the_adapters() -> None:
    client = ChatCompletions(
        BASE,
        "gemini",
        lambda u, b: answer("{}"),
        NO_WAIT,
        extra={"reasoning_effort": "low", "model": "other", "temperature": 1},
    )
    request = client.request("s", "u")
    assert request["reasoning_effort"] == "low"
    assert request["model"] == "gemini" and request["temperature"] == 0
    assert list(request) == [
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "response_format",
        "reasoning_effort",
    ]  # the extras follow the standard keys


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
        if len(calls) == 3:
            raise HttpError(429, None, b"quota")
        return answer('{"criteria": []}')

    client = ChatCompletions(BASE, "llama", busy_then_ok, slept.append, retries=3)
    assert client.complete("s", "u").text == '{"criteria": []}'
    # back-off, then the Retry-After header, then the per-minute floor for a bare 429
    assert len(calls) == 4 and slept == [3.0, 7.0, 20.0]


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
    assert model.pause is pause and model.extra == {}
    assert build_text_model(BASE, "m", 1.0, 1, None, extra={"reasoning_effort": "low"}).extra == {
        "reasoning_effort": "low"
    }
    assert "sk-secret" not in model.url and "sk-secret" not in json.dumps(model.request("s", "u"))
    local = build_text_model("http://localhost:11434/v1", "llama3.1", 60.0, 2000, None)
    assert local.url == "http://localhost:11434/v1/chat/completions"
    assert build_text_model(BASE, "m", 1.0, 1, None, provider="claude").provider == "claude"


def test_tokens_and_latency_come_from_the_provider_payloads() -> None:
    ticks = iter([10.0, 12.5])
    claude = ChatCompletions(
        BASE,
        "claude-haiku-4-5",
        lambda u, b: anthropic_answer('{"criteria": []}'),
        NO_WAIT,
        provider="claude",
        clock=lambda: next(ticks),
    )
    done = claude.complete("s", "u")
    assert (done.provider, done.model) == ("claude", "claude-haiku-4-5")
    assert (done.input_tokens, done.output_tokens, done.latency_s) == (412, 87, 2.5)
    assert done.fell_back_from is None
    gemini = ChatCompletions(BASE, "gemini-2.5-flash", lambda u, b: gemini_answer("{}"), NO_WAIT)
    assert gemini.complete("s", "u").output_tokens == 2140


@pytest.mark.parametrize(
    ("usage", "tokens"),
    [
        (None, (None, None)),
        ({}, (None, None)),
        ({"prompt_tokens": 5}, (5, None)),
        ({"prompt_tokens": "5", "completion_tokens": True}, (None, None)),
        ({"prompt_tokens": -1, "completion_tokens": 0}, (None, 0)),
        ("usage", (None, None)),
    ],
)
def test_a_count_the_provider_left_out_is_none_never_zero(
    usage: object, tokens: tuple[int | None, int | None]
) -> None:
    body: dict[str, object] = {"choices": [{"message": {"content": "{}"}}]}
    if usage is not None:
        body["usage"] = usage
    done = ChatCompletions(BASE, "m", lambda u, b: json.dumps(body).encode(), NO_WAIT).complete(
        "s", "u"
    )
    assert (done.input_tokens, done.output_tokens) == tokens
