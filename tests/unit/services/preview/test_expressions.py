"""A formula checked for the Builder: typed against the user's catalogue, sampled on the
context's session (never an older partition of an input), read-only; bad input fails with a
``ConfigurationError``."""

from datetime import timedelta

import pytest

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.preview.expressions import check_expression, dry_run
from algotrade.services.read.context import (
    ReadContext,
    at_session,
    open_context,
    open_read_stores,
    open_stores,
)
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.api_store import CONFIG_ROOT, END, api_store


@pytest.fixture(scope="module")
def ctx(golden_source: FixtureSource) -> ReadContext:
    store = api_store(golden_source)[0]
    return open_context(store.reader, store.configs, store.user)


def test_a_bool_formula_and_its_sample(ctx: ReadContext) -> None:
    seq = ctx.reader.visible_seq()
    got = check_expression(ctx, "price_stats.close > 10", sample=1)
    assert (got.type, got.dtype, got.session) == ("bool", "bool", END)
    assert len(got.sample) == 1 and isinstance(got.sample[0].value, bool)
    assert ctx.reader.visible_seq() == seq


def test_a_formula_over_nothing_stored_has_no_session(ctx: ReadContext) -> None:
    got = check_expression(ctx, "earnings.days_to_earnings + ibkr_iv.history_days_ibkr")
    assert got.session is None and got.sample == [] and got.licence == "personal"


def test_an_input_missing_on_the_session_is_not_sampled_from_an_older_one(
    ctx: ReadContext,
) -> None:
    later = at_session(ctx, END + timedelta(days=1))  # nothing stored that day
    got = check_expression(later, "price_stats.close > 10")
    assert got.session is None and got.sample == [] and got.rows == 0
    assert got.missing == ["rollups/instrument/price_stats@v2"]


def test_an_empty_store_is_checked_not_sampled() -> None:
    reader, configs = open_read_stores("memory://", CONFIG_ROOT)
    stores = open_stores(reader, configs, UserContext("local"))
    got = check_expression(stores, "price_stats.close > 10")
    assert (got.type, got.session, got.sample) == ("bool", None, [])
    assert got.missing == ["rollups/instrument/price_stats@v2"]
    with pytest.raises(ConfigurationError):
        check_expression(stores, "price_stats.nope + 1")


@pytest.mark.parametrize("expr", ["", "   ", "null", "1 +", "nope_feature * 2"])
def test_bad_formulas_fail(ctx: ReadContext, expr: str) -> None:
    with pytest.raises(ConfigurationError):
        check_expression(ctx, expr)


def _definition(expr: str, name: str = "wanted") -> FeatureDefinition:
    return FeatureDefinition(
        name=name,
        theme="check",
        expr=expr,
        dtype="float",
        unit="ratio",
        description="x",
        null_meaning="x",
    )


def test_a_dry_run_counts_rows_gaps_range_and_criterion(ctx: ReadContext) -> None:
    seq = ctx.reader.visible_seq()
    got = dry_run(ctx, _definition("price_stats.close"), ("<", 0.0))
    assert got.session == END and got.rows > 0 and got.criterion_pass == 0
    assert got.minimum is not None and got.maximum is not None and got.minimum <= got.maximum
    assert got.no_value_rate is not None and 0.0 <= got.no_value_rate <= 1.0
    assert 0 < len(got.sample) <= 5
    above = dry_run(ctx, _definition("price_stats.close"), (">=", got.minimum))
    assert above.criterion_pass == round(got.rows * (1 - (got.no_value_rate or 0.0)))
    assert ctx.reader.visible_seq() == seq


def test_a_dry_run_of_a_bool_formula_has_no_range(ctx: ReadContext) -> None:
    got = dry_run(ctx, _definition("price_stats.close > 10"), ("==", 1.0))
    assert got.minimum is None and got.maximum is None
    assert got.criterion_pass is not None and got.criterion_pass > 0


def test_a_dry_run_is_not_read_from_an_older_session(ctx: ReadContext) -> None:
    got = dry_run(at_session(ctx, END + timedelta(days=1)), _definition("price_stats.close"))
    assert got.session is None and got.rows == 0 and got.sample == []
    assert got.missing == ["rollups/instrument/price_stats@v2"]


def test_a_dry_run_rejects_a_bad_formula_and_operator(ctx: ReadContext) -> None:
    with pytest.raises(ConfigurationError):
        dry_run(ctx, _definition("price_stats.nope + 1"))
    with pytest.raises(ConfigurationError):
        dry_run(ctx, _definition("price_stats.close"), ("~", 1.0))
