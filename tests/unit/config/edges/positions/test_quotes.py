"""``[option_quotes]`` of ``verdict.toml``: typed apart from ``VerdictSettings``, fail-closed."""

import tomllib
from pathlib import Path

import pytest

from algotrade.config.edges.positions.quotes import KEYS, OptionQuotes
from algotrade.core.model.errors import ConfigurationError


def test_the_committed_section_is_the_default_and_the_file_without_it_is_too() -> None:
    doc = tomllib.loads(Path("config/site/verdict.toml").read_text())
    assert set(doc["option_quotes"]) == set(KEYS)
    assert OptionQuotes.from_document(doc) == OptionQuotes()
    assert OptionQuotes.from_document(None) == OptionQuotes(True, True, 0.15, 1)


def test_a_section_overrides_and_a_bad_value_is_refused() -> None:
    read = OptionQuotes.from_document({"option_quotes": {"max_spread_share": 0.3}})
    assert read.max_spread_share == 0.3 and read.two_sided
    for bad in ({"max_spread_share": 2}, {"min_volume_or_oi": -1}, {"two_sided": 1}, {"x": 1}):
        with pytest.raises(ConfigurationError):
            OptionQuotes.from_document({"option_quotes": bad})
