"""A formula checked for the Builder: typed against the user's catalogue, sampled on the
context's session (never an older partition of an input), read-only; bad input fails with a
``ConfigurationError``."""

from datetime import timedelta

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.preview.expressions import check_expression
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
