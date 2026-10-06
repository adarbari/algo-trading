"""``[quality.coverage.<group>.<column>]``: defaults, overrides, and clear errors."""

import pytest

from algotrade.config.site.coverage import DEFAULT_COVERAGE
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import ConfigurationError


def load(doc: dict) -> SourcesSettings:  # type: ignore[type-arg]
    return SourcesSettings.from_document({"quality": {"coverage": doc}})


def test_the_defaults_make_only_core_prices_fail() -> None:
    rules = {r.feature: r for r in SourcesSettings().coverage}
    assert rules["price_stats.close"].level_of("core") == "FAIL"
    assert rules["price_stats.close"].level_of("rest") == "WARN"
    assert all(r.level_of("core") == "WARN" for f, r in rules.items() if f != "price_stats.close")
    assert rules["earnings.next_earnings_date"].covered_by == "row"
    assert SourcesSettings().coverage == DEFAULT_COVERAGE
    overdue = rules["earnings.last_earnings_date"]
    assert (overdue.covered_by, overdue.max_age_days, overdue.or_value) == (
        "recent",
        100,
        "next_earnings_date",
    )
    assert (overdue.core_min, overdue.rest_min, overdue.level_of("core")) == (1.0, 0.0, "WARN")


def test_the_overdue_age_is_configurable() -> None:
    s = load({"earnings": {"last_earnings_date": {"max_age_days": 120}}})
    rule = next(r for r in s.coverage if r.feature == "earnings.last_earnings_date")
    assert (rule.max_age_days, rule.covered_by) == (120, "recent")


def test_a_file_rule_overrides_only_the_keys_it_sets_and_may_add_a_feature() -> None:
    s = load({"iv30": {"iv30": {"rest_min": 0.5, "level": "FAIL"}}, "momentum": {"x": {}}})
    rules = {r.feature: r for r in s.coverage}
    iv = rules["iv30.iv30"]
    assert (iv.rest_min, iv.core_min, iv.level_of("core")) == (0.5, 0.99, "FAIL")
    assert rules["price_stats.close"] == next(r for r in DEFAULT_COVERAGE if "close" in r.feature)
    assert rules["momentum.x"].core_min == 0.95  # the generic limits


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"iv30": {"iv30": {"core_min": 2}}}, "a fraction between 0 and 1"),
        ({"iv30": {"iv30": {"level": "PANIC"}}}, r"one of \['WARN', 'FAIL'\]"),
        ({"iv30": {"iv30": {"covered_by": "magic"}}}, "covered_by"),
        ({"iv30": {"iv30": {"min": 0.5}}}, "unknown keys"),
        ({"earnings": {"last_earnings_date": {"max_age_days": 0}}}, "an integer >= 1"),
    ],
)
def test_bad_values_name_the_key(doc: dict, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ConfigurationError, match=message):
        load(doc)
