"""``FeatureSet.coverage`` (ADR 0055, coverage of coalescing expressions): which missing
tables block a screen and which it tolerates, over the real site catalogue and a few
test expressions."""

from dataclasses import replace

import pytest

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

IBKR = "rollups/instrument/ibkr_iv@v1"
CBOE = "rollups/instrument/iv30@v1"
PS = "rollups/instrument/price_stats@v2"
OL = "rollups/instrument/option_liquidity@v1"
SITE = site_features(FileConfigStore(REPO_ROOT / "config"))


def define(name: str, expr: str, dtype: str = "float", **kw: object) -> FeatureDefinition:
    base = FeatureDefinition(name, "t", expr, dtype, "decimal", f"test {name}", "never")
    return replace(base, **kw)  # type: ignore[arg-type]


def test_every_leg_missing_is_blocking_both_tables() -> None:
    assert SITE.coverage(["feature.vrp_iv30"], [IBKR, CBOE]) == ([IBKR, CBOE], [])


def test_the_ibkr_leg_present_covers_vrp_iv30_and_tolerates_the_missing_cboe_table() -> None:
    assert SITE.coverage(["feature.vrp_iv30"], [CBOE]) == ([], [CBOE])


def test_the_cboe_leg_present_tolerates_the_missing_optional_table() -> None:
    assert SITE.coverage(["feature.vrp_iv30"], [IBKR]) == ([], [IBKR])


def test_a_literal_leg_never_covers_a_coalesce() -> None:
    fs = SITE.with_user(
        [define("tier", 'coalesce(option_liquidity.put_tier, "D")', dtype="str", owner="u")]
    )
    assert fs.coverage(["feature.tier"], [OL]) == ([OL], [])
    assert fs.coverage(["feature.tier"], []) == ([], [])


def test_a_table_read_by_an_uncovered_operand_is_blocking() -> None:
    blocking, tolerated = SITE.coverage(["feature.vrp_iv_hv_spread"], [CBOE, PS])
    assert blocking == [PS] and tolerated == [CBOE]


def test_a_non_coalesce_read_of_an_optional_group_stays_tolerated() -> None:
    assert SITE.coverage(["rollup.ibkr_iv@v1.iv30_ibkr"], [IBKR]) == ([], [IBKR])


def test_a_missing_required_stored_field_blocks_and_an_unexplained_table_stays_blocking() -> None:
    assert SITE.coverage(["rollup.price_stats@v2.hv30"], [PS, "x/unknown"]) == (
        [PS, "x/unknown"],
        [],
    )


def test_exists_is_always_covered() -> None:
    fs = SITE.with_user([define("listed", "exists(option_liquidity)", dtype="bool", owner="u")])
    fields = ["feature.listed", "rollup.ibkr_iv@v1.iv30_ibkr"]
    assert fs.coverage(fields, [IBKR]) == ([], [IBKR])


@pytest.mark.parametrize("name", sorted(SITE.expressions))
def test_every_site_expression_coverage_resolves(name: str) -> None:
    """No unknown refs: coverage walks every expression with every table missing."""
    tables = list(dict.fromkeys(g.table for g in SITE.groups.values()))
    blocking, tolerated = SITE.coverage([f"feature.{name}"], tables)
    assert set(blocking) | set(tolerated) == set(tables)
