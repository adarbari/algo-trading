"""``Feature`` declarations: validation of every field, references, ranges and the key a
group gives its features."""

from typing import Any

import pytest

from algotrade.features.framework.declaration import FeatureGroup, Input
from algotrade.features.framework.feature import (
    Feature,
    feature_problems,
    in_range,
    is_feature_ref,
    strictest,
)
from tests.helpers.rollup_store import features


def _feature(**changes: Any) -> Feature:
    base: dict[str, Any] = {
        "name": "hv30",
        "dtype": "float",
        "unit": "decimal",
        "description": "realised vol",
        "null_meaning": "a gap",
        "valid_range": (0, 5),
        "inputs": ("bars/1d.close", "price_stats.close@v1"),
    }
    return Feature(**{**base, **changes})


def test_a_valid_feature_has_no_problems() -> None:
    assert feature_problems(_feature()) == []


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"name": "Bad"}, "name must match"),
        ({"dtype": "decimal"}, "dtype must be"),
        ({"unit": "percent"}, "unit"),
        ({"kind": "magic"}, "kind"),
        ({"entity": "market"}, "entity"),
        ({"description": " "}, "describe it"),
        ({"null_meaning": ""}, "when it is null"),
        ({"dtype": "str", "unit": "category", "valid_range": (0, 1)}, "numeric dtype"),
        ({"valid_range": (2, 1)}, "min > max"),
        ({"categories": ("A",)}, "categories need dtype str"),
        ({"inputs": ("close",)}, "neither"),
        ({"licence": "public"}, "licence 'public' must be one of"),
        ({"applies_to": "stocks"}, "applies_to 'stocks' must be one of"),
        ({"null_status": "iv30.status@x"}, "null_status 'iv30.status@x' is not"),
    ],
)
def test_problems_are_named(changes: dict[str, Any], problem: str) -> None:
    assert any(problem in p for p in feature_problems(_feature(**changes)))


def test_ranges_and_references() -> None:
    f = _feature()
    assert in_range(f, 0.0) and in_range(f, 5.0) and not in_range(f, 5.1)
    assert in_range(_feature(valid_range=None), -1e9)
    assert in_range(_feature(valid_range=(None, 0)), -3) and not in_range(
        _feature(valid_range=(0, None)), -1
    )
    assert is_feature_ref("price_stats.close@v1") and not is_feature_ref("bars/1d.close")


def test_a_group_owns_and_versions_its_features() -> None:
    group = FeatureGroup(
        "demo", 2, "", (Input("bars/1d"),), features({"a": "float", "b": "int"}), lambda *_: None
    )
    a = group.feature("a")
    assert (a.group, a.version, a.key, a.field) == ("demo@v2", 2, "demo.a@v2", "rollup.demo@v2.a")
    assert dict(group.columns) == {"a": "float", "b": "int"}


def test_licences_default_open_and_the_strictest_wins() -> None:
    assert _feature().licence == "open"
    assert strictest([]) == "open" and strictest(["open", "open"]) == "open"
    assert strictest(["open", "personal"]) == "personal"


def test_applicability_is_inherited_from_the_group_and_status_fields_resolve() -> None:
    group = FeatureGroup(
        "demo", 1, "", (Input("bars/1d"),),
        (*features({"a": "float", "status": "str"}), _feature(name="b", null_status="status")),
        lambda *_: None, applies_to="optionable",
    )  # fmt: skip
    assert {f.applies_to for f in group.features} == {"optionable"}
    assert group.feature("b").status_field == "rollup.demo@v1.status"
    other = _feature(null_status="iv30.iv30_status@v1")
    assert other.status_field == "rollup.iv30@v1.iv30_status" and feature_problems(other) == []
    assert _feature().status_field == "" and _feature().applies_to == "any"
    own = FeatureGroup(
        "demo2", 1, "", (Input("bars/1d"),), (_feature(applies_to="not_etf"),),
        lambda *_: None, applies_to="optionable",
    )  # fmt: skip
    assert own.feature("hv30").applies_to == "not_etf"  # a feature's own value wins
    with pytest.raises(ValueError, match="not a column of the group"):
        FeatureGroup(
            "d3", 1, "", (Input("bars/1d"),), (_feature(null_status="nope"),), lambda *_: None
        )
