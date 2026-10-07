"""``feature_definitions`` (ADR 0023 step 3): the typed ``FeatureDefinition`` of each
``[<name>]`` of a features file, and errors that name the file and key."""

from typing import Any

import pytest

from algotrade.config.site.features.definitions import feature_definitions
from algotrade.core.model.errors import ConfigurationError


def test_feature_definitions_are_typed() -> None:
    doc = {
        "a": {"expr": "x.y + k", "dtype": "float", "unit": "decimal", "description": "d",
              "null_meaning": "n", "valid_range": [0, float("inf")], "params": {"k": 1},
              "materialise": True, "version": 2},
        "b": {"expr": "'L'", "dtype": "str", "unit": "category", "description": "d",
              "null_meaning": "n", "kind": "label", "categories": ["L"]},
    }  # fmt: skip
    a, b = feature_definitions({"t": doc})
    assert (a.name, a.theme, a.valid_range, a.params, a.materialise, a.version) == (
        "a", "t", (0.0, None), {"k": 1}, True, 2,
    )  # fmt: skip
    assert a.where == "config/site/features/t.toml [a]" and a.kind == "expression"
    assert (b.kind, b.categories, b.valid_range, b.version) == ("label", ("L",), None, 1)
    assert feature_definitions({}) == ()


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"expr": "1"}, r"\[f\]: missing \['dtype', 'unit', 'description', 'null_meaning'\]"),
        ({"expr": "1", "dtype": "float", "unit": "u", "description": "d", "null_meaning": "n",
          "valid_range": [1]}, r"\[f\] valid_range: expected \[min, max\]"),
        ({"expr": "1", "dtype": "float", "unit": "u", "description": "d", "null_meaning": "n",
          "params": {"k": [1]}}, r"\[f\] params: expected a table"),
        ({"expr": "1", "dtype": "float", "unit": "u", "description": "d", "null_meaning": "n",
          "kind": "window"}, r"\[f\] kind: expected one of"),
        ({"expr": "1", "colour": "red"}, r"\[f\]: unknown keys \['colour'\]"),
        ({"expr": "1", "dtype": "float", "unit": "u", "description": "d", "null_meaning": "n",
          "version": 0}, r"\[f\] version: expected an integer >= 1"),
    ],
)  # fmt: skip
def test_feature_definition_errors_name_the_file_and_key(
    section: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=r"config/site/features/t\.toml"):
        feature_definitions({"t": {"f": section}})
    with pytest.raises(ConfigurationError, match=message):
        feature_definitions({"t": {"f": section}})
