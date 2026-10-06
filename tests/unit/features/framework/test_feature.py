"""``Feature`` declarations: validation of every field, references, ranges and the key a
group gives its features."""

from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.declaration import FeatureGroup, Input
from algotrade.features.framework.feature import (
    Feature,
    NullReason,
    feature_problems,
    in_range,
    is_feature_ref,
    not_applicable,
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
        ({"null_status": "status"}, "goes with illiquid_statuses or explained_statuses"),
        ({"illiquid_statuses": ("A",)}, "goes with"),
        ({"explained_statuses": ("NO_TRADE",)}, "goes with"),
        ({"null_status": "s", "explained_statuses": ("STALE",)}, "['STALE'] are not NullReason"),
        (
            {
                "null_status": "s",
                "illiquid_statuses": ("NO_TRADE",),
                "explained_statuses": ("NO_TRADE",),
            },
            "either illiquid or explained",
        ),
        ({"null_status": "iv30.status@x"}, "null_status 'iv30.status@x' is not"),
    ],
)
def test_problems_are_named(changes: dict[str, Any], problem: str) -> None:
    assert any(problem in p for p in feature_problems(_feature(**changes)))


def test_explained_statuses_are_null_reasons() -> None:
    f = _feature(null_status="bar_status", explained_statuses=("NO_TRADE", "FEW_BARS"))
    assert feature_problems(f) == []
    assert {r.value for r in NullReason} == {"NO_TRADE", "NOT_ANNOUNCED", "NEW_LISTING", "FEW_BARS"}


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
        (
            *features({"a": "float", "status": "str"}),
            _feature(name="b", null_status="status", illiquid_statuses=("X",)),
        ),
        lambda *_: None, applies_to="optionable",
    )  # fmt: skip
    assert {f.applies_to for f in group.features} == {"optionable"}
    assert group.feature("b").status_field == "rollup.demo@v1.status"
    other = _feature(null_status="iv30.iv30_status@v1", illiquid_statuses=("X",))
    assert other.status_field == "rollup.iv30@v1.iv30_status" and feature_problems(other) == []
    assert other.status_column == ("iv30@v1", "iv30_status")
    assert other.status_table == "rollups/instrument/iv30@v1"
    assert group.feature("b").status_table == "rollups/instrument/demo@v1"
    assert _feature().status_table == ""
    assert _feature().status_field == "" and _feature().applies_to == "any"
    own = FeatureGroup(
        "demo2", 1, "", (Input("bars/1d"),), (_feature(applies_to="operating_company"),),
        lambda *_: None, applies_to="optionable",
    )  # fmt: skip
    assert own.feature("hv30").applies_to == "operating_company"  # a feature's own value wins
    with pytest.raises(ValueError, match="not a column of the group"):
        FeatureGroup(
            "d3",
            1,
            "",
            (Input("bars/1d"),),
            (_feature(null_status="nope", illiquid_statuses=("X",)),),
            lambda *_: None,
        )


def test_a_cross_group_null_status_must_name_a_declared_column() -> None:
    def group(status: str) -> FeatureGroup:
        return FeatureGroup(
            "demo", 1, "", (Input("bars/1d"),),
            (_feature(null_status=status, illiquid_statuses=("X",)),), lambda *_: None,
        )  # fmt: skip

    other = FeatureGroup(
        "iv30", 1, "", (Input("bars/1d"),), features({"iv30_status": "str"}), lambda *_: None
    )
    FeatureSet({"demo@v1": group("iv30.iv30_status@v1"), "iv30@v1": other}, {}, {})  # fine
    for bad in ("iv30.nope@v1", "ghost.iv30_status@v1", "iv30.iv30_status@v2"):
        with pytest.raises(ConfigurationError, match="not a declared feature column"):
            FeatureSet({"demo@v1": group(bad), "iv30@v1": other}, {}, {})


def test_not_applicable_is_decided_from_the_reference_facts() -> None:
    assert not_applicable(["optionable"], False, "COMMON_STOCK") == "optionable"
    assert not_applicable(["optionable"], None, "COMMON_STOCK") == ""  # null is not "no"
    assert not_applicable([], False, "ETF") == ""  # applies to any


def test_operating_company_rules_out_non_operating_types_and_blank_checks() -> None:
    op = ["operating_company"]
    assert not_applicable(op, True, "ETF") == "operating_company"
    assert not_applicable(op, True, "PREFERRED") == "operating_company"
    assert not_applicable(op, True, "COMMON_STOCK", "6770") == "operating_company"
    assert not_applicable(op, True, "COMMON_STOCK", "3571") == ""
    assert not_applicable(op, True, "ADR") == ""
    assert not_applicable(op, True, "COMMON_STOCK", None) == ""  # null sic: never a false n/a
    assert not_applicable(op, True, None, None) == ""  # null type: unknown, not n/a
