"""The API's text model (ADR 0041): ``llm.toml`` builds it, and a file that does not load turns
the text model off with the file's message instead of stopping the app."""

import logging
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.services.text_model.chain import FallbackTextModel
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from algotrade_api.text_model import OFF, open_text_model
from algotrade_sources.llm.chat import ChatCompletions
from algotrade_sources.llm.claude_cli import ClaudeCli
from tests.helpers.api_store import as_user


def configs(llm: dict[str, Any] | None) -> MemoryConfigStore:
    return MemoryConfigStore({} if llm is None else {("site", "settings", "llm"): llm})


def test_a_missing_or_disabled_file_is_off_without_a_complaint(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert open_text_model(configs(None)) == (None, OFF)
    assert open_text_model(configs({"enabled": False})) == (None, OFF)
    assert not caplog.records


def test_an_enabled_file_builds_the_model_with_its_request_fields() -> None:
    model, _ = open_text_model(
        configs({"enabled": True, "model": "gemini", "request": {"reasoning_effort": "low"}})
    )
    assert isinstance(model, ChatCompletions) and model.model == "gemini"
    assert model.names == ("gemini",)
    assert dict(model.extra) == {"reasoning_effort": "low"}


CHAIN: dict[str, Any] = {
    "enabled": True,
    "provider": [
        {"id": "claude", "base_url": "https://api.anthropic.com/v1", "model": "claude-haiku-4-5"},
        {
            "id": "gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-2.5-flash",
        },
    ],
}


def test_a_chain_is_one_adapter_per_provider_each_with_its_own_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALGOTRADE_LLM_API_KEY_CLAUDE", "sk-claude")
    monkeypatch.setenv("ALGOTRADE_LLM_API_KEY_GEMINI", "sk-gemini")
    monkeypatch.setenv("ALGOTRADE_LLM_API_KEY", "sk-legacy")  # the legacy form's, never a chain's
    model, _ = open_text_model(configs(CHAIN))
    assert isinstance(model, FallbackTextModel)
    assert model.names == ("claude-haiku-4-5", "gemini-2.5-flash")
    assert [pid for pid, _ in model.members] == [
        "claude",
        "gemini",
    ] and model.deadline_s == 440.0  # 2 x (3 x 60 s + 2 x 20 s)
    claude = model.members[0][1]
    assert isinstance(claude, ChatCompletions) and claude.provider == "claude"


CLI_CHAIN: dict[str, Any] = {
    "enabled": True,
    "provider": [
        {
            "id": "claude_cli",
            "kind": "claude-cli",
            "command": "/Users/o/.local/bin/claude",
            "model": "haiku",
            "only_users": ["abhi"],
        },
        CHAIN["provider"][1],
    ],
}


def test_a_claude_cli_provider_is_wired_for_its_users_with_the_scrubbed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALGOTRADE_LLM_API_KEY_GEMINI", "sk-gemini")
    monkeypatch.setenv("HOME", "/Users/o")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")  # never reaches the child
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    model, _ = open_text_model(configs(CLI_CHAIN))
    assert isinstance(model, FallbackTextModel)
    assert model.names_for("abhi") == ("haiku", "gemini-2.5-flash")
    assert model.names_for("bob") == ("gemini-2.5-flash",)
    cli = model.members[0][1]
    assert isinstance(cli, ClaudeCli) and cli.provider == "claude_cli" and cli.retries == 0
    assert cli.command == "/Users/o/.local/bin/claude"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in cli.env and "ANTHROPIC_API_KEY" not in cli.env
    assert cli.env["HOME"] == "/Users/o"


def test_a_lone_claude_cli_provider_still_answers_only_its_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, _ = open_text_model(configs(CLI_CHAIN | {"provider": CLI_CHAIN["provider"][:1]}))
    assert isinstance(model, FallbackTextModel) and model.names_for("bob") == ()


def test_a_claude_cli_provider_without_only_users_turns_the_text_model_off() -> None:
    bare = {k: v for k, v in CLI_CHAIN["provider"][0].items() if k != "only_users"}
    model, reason = open_text_model(configs(CLI_CHAIN | {"provider": [bare]}))
    assert model is None and "needs only_users" in reason


def test_a_remote_provider_without_a_key_is_left_out_of_the_chain(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("ALGOTRADE_LLM_API_KEY_CLAUDE", raising=False)
    monkeypatch.setenv("ALGOTRADE_LLM_API_KEY_GEMINI", "sk-gemini")
    with caplog.at_level(logging.WARNING):
        model, _ = open_text_model(configs(CHAIN))
    assert isinstance(model, ChatCompletions) and model.provider == "gemini"
    assert "ALGOTRADE_LLM_API_KEY_CLAUDE" in caplog.text and "sk-gemini" not in caplog.text


def test_a_chain_with_no_key_at_all_is_off_with_the_variables_to_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("ALGOTRADE_LLM_API_KEY_CLAUDE", "ALGOTRADE_LLM_API_KEY_GEMINI"):
        monkeypatch.delenv(name, raising=False)
    model, reason = open_text_model(configs(CHAIN))
    assert model is None and "ALGOTRADE_LLM_API_KEY_CLAUDE" in reason


def test_a_file_with_both_forms_turns_the_text_model_off() -> None:
    model, reason = open_text_model(configs(CHAIN | {"model": "llama3.1"}))
    assert model is None and "use one form" in reason


def test_a_file_that_does_not_load_is_logged_and_turns_the_text_model_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        model, reason = open_text_model(configs({"enabled": True, "reasoning_effort": "low"}))
    assert model is None
    assert "llm.toml" in reason and "reasoning_effort" in reason
    assert [r.levelname for r in caplog.records] == ["ERROR"]
    assert "reasoning_effort" in caplog.records[0].getMessage()


def test_the_app_starts_with_a_wrong_llm_toml_and_drafting_answers_503(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    store = replace(api_golden[0], configs=configs({"enabled": True, "nonsense": 1}))
    app = create_app(ApiSettings("memory://", "config", live=True), store, authenticator=as_user())
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    response = client.post("/screeners/s/draft-from-text", json={"text": "stocks over $5"})
    assert response.status_code == 503
    assert "llm.toml" in response.json()["detail"] and "nonsense" in response.json()["detail"]
