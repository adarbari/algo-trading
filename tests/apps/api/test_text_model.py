"""The API's text model (ADR 0041): ``llm.toml`` builds it, and a file that does not load turns
the text model off with the file's message instead of stopping the app."""

import logging
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from algotrade_api.text_model import OFF, open_text_model
from algotrade_sources.llm.chat import ChatCompletions
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
    assert model.name == "gemini"
    assert dict(model.extra) == {"reasoning_effort": "low"}


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
