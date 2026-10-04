"""A formula checked for the Builder: typed against the user's catalogue, sampled on the latest
session its inputs have, read-only; bad input fails with a ``ConfigurationError``."""

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.explore.preview.expressions import check_expression
from algotrade.services.explore.store import ReadStore
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.api_store import END, api_store


@pytest.fixture(scope="module")
def store(golden_source: FixtureSource) -> ReadStore:
    return api_store(golden_source)[0]


def test_a_bool_formula_and_its_sample(store: ReadStore) -> None:
    seq = store.reader.visible_seq()
    got = check_expression(store, "price_stats.close > 10", sample=1)
    assert (got.type, got.dtype, got.session) == ("bool", "bool", END)
    assert len(got.sample) == 1 and isinstance(got.sample[0].value, bool)
    assert store.reader.visible_seq() == seq


def test_a_formula_over_nothing_stored_has_no_session(store: ReadStore) -> None:
    got = check_expression(store, "earnings.days_to_earnings + ibkr_iv.history_days_ibkr")
    assert got.session is None and got.sample == [] and got.licence == "personal"


@pytest.mark.parametrize("expr", ["", "   ", "null", "1 +", "nope_feature * 2"])
def test_bad_formulas_fail(store: ReadStore, expr: str) -> None:
    with pytest.raises(ConfigurationError):
        check_expression(store, expr)
