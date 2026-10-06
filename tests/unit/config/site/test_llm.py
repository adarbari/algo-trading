"""``llm.toml`` (ADR 0041): defaults (off, a local server), typed keys, https for anything that
is not this machine, no secrets in the file. ``phrasebook.toml``: phrases in file order, each
with words, fields and a hint; errors name the entry."""

from typing import Any

import pytest

from algotrade.config.site.llm import LlmSettings, Phrase, PhrasebookSettings
from algotrade.config.site.settings import load_llm, load_phrasebook
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.config.site.test_settings import site


def test_defaults_are_off_and_local() -> None:
    d = LlmSettings.from_document(None)
    assert not d.enabled and d.base_url == "http://localhost:11434/v1"
    assert (d.timeout_s, d.answer_limit, d.retries) == (60.0, 8000, 2)


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
            "retries": 0,
        }
    )
    assert s.enabled and s.base_url == "https://api.groq.com/openai/v1"
    assert (s.model, s.timeout_s, s.answer_limit) == ("llama-3.3-70b-versatile", 20.0, 800)
    assert s.retries == 0


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"base_url": "http://api.example.com/v1"}, "must use https"),
        ({"base_url": "ftp://localhost/v1"}, "expected an http"),
        ({"base_url": ""}, "non-empty string"),
        ({"timeout_s": 0}, "timeout_s"),
        ({"answer_limit": 0}, "answer_limit"),
        ({"retries": -1}, "retries"),
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


def test_phrasebook_entries_in_file_order() -> None:
    book = PhrasebookSettings.from_document(
        {
            "phrase": [
                {
                    "say": ["momentum", " trending up "],
                    "fields": ["rollup.a@v1.x"],
                    "hint": " gate:  x gt 0 ",
                },
                {"say": ["cheap"], "fields": ["rollup.a@v1.close", "feature.p"]},
            ]
        }
    )
    assert book.phrases == (
        Phrase(("momentum", "trending up"), ("rollup.a@v1.x",), "gate:  x gt 0"),
        Phrase(("cheap",), ("rollup.a@v1.close", "feature.p"), ""),
    )
    assert PhrasebookSettings.from_document(None).phrases == ()
    assert load_phrasebook(MemoryConfigStore({})).phrases == ()


def test_the_shipped_phrasebook_loads() -> None:
    book = PhrasebookSettings.from_document(site("phrasebook"))
    assert len(book.phrases) >= 10
    assert any("momentum" in p.say for p in book.phrases)
    assert all(p.hint for p in book.phrases)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"phrase": {"say": ["x"]}}, r"expected a list of tables"),
        ({"phrase": [{"fields": ["a"]}]}, r"\[\[phrase\]\]\[0\] say"),
        ({"phrase": [{"say": ["x"]}]}, r"\[\[phrase\]\]\[0\] fields"),
        ({"phrase": [{"say": ["x"], "fields": [""]}]}, r"fields: expected"),
        ({"phrase": [{"say": "x", "fields": ["a"]}]}, r"a list of strings"),
        ({"phrase": [{"say": ["x"], "fields": ["a"], "mean": "y"}]}, r"unknown keys"),
        ({"phrases": []}, r"unknown keys"),
    ],
)
def test_phrasebook_errors_name_the_entry(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        PhrasebookSettings.from_document(doc)
