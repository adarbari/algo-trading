"""``llm.toml`` (ADR 0040): defaults (off, a local server), typed keys, https for anything that
is not this machine, no secrets in the file."""

from typing import Any

import pytest

from algotrade.config.site.llm import LlmSettings
from algotrade.config.site.settings import load_llm
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.config.site.test_settings import site


def test_defaults_are_off_and_local() -> None:
    d = LlmSettings.from_document(None)
    assert not d.enabled and d.base_url == "http://localhost:11434/v1"
    assert (d.timeout_s, d.answer_limit) == (60.0, 2000)


def test_the_shipped_file_is_off() -> None:
    assert not LlmSettings.from_document(site("llm")).enabled
    assert not load_llm(MemoryConfigStore({})).enabled


def test_a_remote_provider() -> None:
    s = LlmSettings.from_document(
        {
            "enabled": True,
            "base_url": "https://api.groq.com/openai/v1/",
            "model": "llama-3.3-70b-versatile",
            "timeout_s": 20,
            "answer_limit": 800,
        }
    )
    assert s.enabled and s.base_url == "https://api.groq.com/openai/v1"
    assert (s.model, s.timeout_s, s.answer_limit) == ("llama-3.3-70b-versatile", 20.0, 800)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"base_url": "http://api.example.com/v1"}, "must use https"),
        ({"base_url": "ftp://localhost/v1"}, "expected an http"),
        ({"base_url": ""}, "non-empty string"),
        ({"timeout_s": 0}, "timeout_s"),
        ({"answer_limit": 0}, "answer_limit"),
        ({"api_key": "sk-123"}, "looks like a secret"),
        ({"provider": "groq"}, "unknown keys"),
    ],
)
def test_errors_name_the_key(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        LlmSettings.from_document(doc)


def test_plain_http_is_fine_on_this_machine() -> None:
    for host in ("localhost", "127.0.0.1", "[::1]"):
        assert LlmSettings.from_document({"base_url": f"http://{host}:11434/v1"}).enabled is False
