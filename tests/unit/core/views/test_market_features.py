"""MarketFeatures (ADR 0049): market values on the bar timeline, sliced without lookahead."""

import numpy as np
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.core.views.feature_view import FeatureView
from algotrade.core.views.market_features import MarketFeatures
from algotrade.core.views.market_view import MarketView
from tests.helpers.domain_objects import series_from_closes

LABEL = "market.regime@v2.label"
LABELS = ["CALM", "STRESS", None, "CRISIS"]


def features() -> MarketFeatures:
    timestamps = series_from_closes([1, 2, 3, 4]).timestamps
    return MarketFeatures(timestamps, {LABEL: LABELS, "market.x@v1.score": [1.0, 2.0, 3.0, 4.0]})


def test_the_value_at_a_cursor_is_that_sessions_row() -> None:
    market = features()
    assert len(market) == 4 and market.names == (LABEL, "market.x@v1.score")
    assert [market.at(t)[LABEL] for t in range(4)] == LABELS
    assert dict(market.at(1)) == {LABEL: "STRESS", "market.x@v1.score": 2.0}
    assert LABEL in market and "market.y@v1.z" not in market
    with pytest.raises(TypeError):
        market.at(0)[LABEL] = "CALM"  # type: ignore[index]


def test_a_missing_name_or_cursor_is_an_error() -> None:
    market = features()
    with pytest.raises(MissingDataError, match=r"market\.y@v1\.z"):
        market.value("market.y@v1.z", 0)
    with pytest.raises(IndexError):
        market.value(LABEL, 4)


def test_columns_must_be_aligned_to_the_timeline() -> None:
    timestamps = series_from_closes([1, 2, 3]).timestamps
    with pytest.raises(ValueError, match="not aligned"):
        MarketFeatures(timestamps, {LABEL: ["CALM"]})


def test_market_view_slices_market_features_at_its_cursor() -> None:
    data = {"TEST": series_from_closes([1, 2, 3, 4])}
    market = features()
    assert MarketView(data, 1, market).market_feature(LABEL) == "STRESS"
    assert MarketView(data, 2, market).market_feature(LABEL) is None  # unknown, not CALM
    with pytest.raises(MissingDataError):
        MarketView(data, 1).market_feature(LABEL)  # the run loaded none
    with pytest.raises(MissingDataError):
        MarketView(data, 1, market).market_feature("market.y@v1.z")
    short = MarketFeatures(series_from_closes([1, 2]).timestamps, {LABEL: ["CALM", "CALM"]})
    with pytest.raises(ValueError, match="cover 2 bars"):
        MarketView(data, 1, short)


def test_feature_view_carries_the_sessions_market_values() -> None:
    view = FeatureView(np.datetime64("2026-10-02").item(), {"EQ:A": {}}, {LABEL: "CALM"})
    assert view.market == {LABEL: "CALM"}
    assert FeatureView(view.as_of, {}).market == {}
