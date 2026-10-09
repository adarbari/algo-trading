"""``toml_text``: the config store's one serialiser round-trips and fails closed."""

import tomllib
from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.toml_text import toml_text

DOC: dict[str, Any] = {
    "id": "mine",
    "kind": "screener",
    "criteria": {"price": {"field": "x", "op": "gt", "value": 5.0}},
    "flags": {"f": {"all": [{"field": "a", "op": "in", "value": ["X", "Y"]}]}},
    "weird key": 1.5,
}


def test_toml_text_round_trips_and_fails_closed() -> None:
    assert tomllib.loads(toml_text(DOC)) == DOC
    with pytest.raises(ConfigurationError, match="null"):
        toml_text({"a": None})
    with pytest.raises(ConfigurationError, match="not a config value"):
        toml_text({"a": [object()]})
    with pytest.raises(ConfigurationError, match="larger"):
        toml_text({"a": "x" * 70_000})
