"""``load_market_history`` (ADR 0047): a stored market field over a window, each session from
its own partition (an older one is never carried forward: a session with no row is a gap),
numbers bucketed with their extremes kept, flags and labels merged into segments, the window
cut to the session, and computed (``feature.*``) or unknown names refused."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_ending
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.market.buckets import Point, Segment
from algotrade.services.read.market.history import MAX_POINTS, load_market_history
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with
from tests.unit.services.read.regime.conftest import (
    SEP28,
    SEP29,
    SEP30,
    regime_ctx,
    with_regime,
    write_regime,
)

RISK = "market.regime@v2.macro_risk"
LABEL = "market.regime@v2.label"
CURVE_ON = "market.regime_indicators@v1.curve_on"


def test_a_number_has_a_point_per_session_and_a_missing_session_is_a_gap() -> None:
    # stored: 28 and 29 Sep at 10.0, nothing for 30 Sep, 1 Oct 62.5: 29 Sep's value is not carried
    [risk] = load_market_history(regime_ctx(), [RISK], SEP28, D1)
    assert (risk.name, risk.bucket_sessions, risk.segments) == (RISK, 1, ())
    assert risk.points == (
        Point(SEP28, 10.0), Point(SEP29, 10.0), Point(SEP30, None), Point(D1, 62.5),
    )  # fmt: skip


def test_a_label_and_a_flag_are_merged_into_segments() -> None:
    label, curve = load_market_history(regime_ctx(), [LABEL, CURVE_ON], SEP28, D1)
    assert (label.points, label.bucket_sessions) == ((), 1)
    assert label.segments == (
        Segment(SEP28, SEP29, "CALM"), Segment(SEP30, SEP30, "UNKNOWN"), Segment(D1, D1, "STRESS"),
    )  # fmt: skip
    # the curve flag is stored only for 1 Oct (ON); the sessions before it have nothing
    assert curve.segments == (Segment(SEP28, SEP30, "UNKNOWN"), Segment(D1, D1, "ON"))


def test_an_older_partition_is_ignored_and_the_window_is_cut_to_the_session() -> None:
    ctx = regime_ctx(D0)  # the session is 30 Sep: 1 Oct is not known
    [label] = load_market_history(ctx, [LABEL], SEP28, D1)
    assert label.segments == (Segment(SEP28, SEP29, "CALM"), Segment(SEP30, SEP30, "UNKNOWN"))
    [risk] = load_market_history(ctx, [RISK], SEP28, D1)
    # nothing is read from 1 Oct, and 29 Sep's 10.0 does not stand in for 30 Sep
    assert risk.points[-1] == Point(SEP30, None)


def test_nothing_stored_is_one_gap_or_one_unknown_run() -> None:
    ctx = with_regime(context(store_with()))
    risk, label = load_market_history(ctx, [RISK, LABEL], SEP28, D1)
    assert risk.points == (Point(SEP28, None),)
    assert label.segments == (Segment(SEP28, D1, "UNKNOWN"),)


def test_names_keep_their_order_and_repeats_are_dropped() -> None:
    found = load_market_history(regime_ctx(), [LABEL, RISK, LABEL], SEP28, D1)
    assert [h.name for h in found] == [LABEL, RISK]


def test_a_long_history_is_bucketed_and_keeps_its_spike_deterministically() -> None:
    days = sessions_ending(D1, 800)

    def write(writer: StoreWriter) -> None:
        for i, day in enumerate(days):
            write_regime(writer, day, "CALM", macro_risk=50.0 if i != 333 else 99.0)

    ctx = with_regime(context(store_with(write)))
    [first] = load_market_history(ctx, [RISK], days[0], D1, points=100)
    [again] = load_market_history(ctx, [RISK], days[0], D1, points=100)
    assert first == again
    assert first.bucket_sessions == 16 and len(first.points) <= 100  # ceil(800 / 50)
    spike = next(p for p in first.points if p.value == 99.0)
    assert spike.session == days[333]  # at its own session, not its bucket's first
    assert all(p.value in (50.0, 99.0) for p in first.points)
    [label] = load_market_history(ctx, [LABEL], days[0], D1, points=100)
    assert label.segments == (Segment(days[0], D1, "CALM"),)  # points do not bucket a label


@pytest.mark.parametrize(
    ("names", "error", "message"),
    [
        (["feature.anything"], ConfigurationError, r"only stored market fields.*feature\.\*"),
        (["rollup.price_stats@v2.close"], ConfigurationError, "only stored market fields"),
        (["instrument.symbol"], ConfigurationError, "only stored market fields"),
        (["market.nope@v1.x"], UnknownFeatureError, "unknown market feature"),
    ],
)
def test_only_stored_market_fields_have_a_history(
    names: list[str], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        load_market_history(regime_ctx(), names, SEP28, D1)


def test_the_window_and_the_point_budget_are_checked() -> None:
    ctx = regime_ctx()
    with pytest.raises(ConfigurationError, match=f"end {SEP28} is before start {D1}"):
        load_market_history(ctx, [RISK], D1, SEP28)
    for points in (1, MAX_POINTS + 1):
        with pytest.raises(ConfigurationError, match="points"):
            load_market_history(ctx, [RISK], SEP28, D1, points=points)
    [after] = load_market_history(regime_ctx(D0), [RISK], date(2026, 10, 5), date(2026, 10, 9))
    assert after.points == ()  # a window that starts after the session has no session
