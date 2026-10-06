"""Catalogue features per stored session over an explicit window (range grain): rollup columns
and expression features, in the order asked, ``None`` where a session has no value; names
outside the catalogue and instrument facts are request errors."""

from datetime import date
from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.instruments.series import SeriesPoint, load_series
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with

CLOSE = "rollup.price_stats@v2.close"
HV20 = "rollup.price_stats@v2.hv20"
FROM_HIGH = "feature.pct_from_high_52w"


def test_rollup_columns_and_expressions_per_stored_session() -> None:
    ctx = context(store_with())
    found = load_series(ctx, ["EQ:AAA", "EQ:ETFX"], [CLOSE, HV20, FROM_HIGH, CLOSE], D0)
    aaa = found["EQ:AAA"]
    assert (aaa.names, aaa.start, aaa.end) == ((CLOSE, HV20, FROM_HIGH), D0, D1)
    assert aaa.points[0] == SeriesPoint(D0, (50.0, 0.3, pytest.approx(50.0 / 60.0 - 1)))
    assert aaa.points[1].session == D1 and aaa.points[1].values[:2] == (51.0, None)
    assert [p.session for p in found["EQ:ETFX"].points] == [D0]  # no D1 row


def test_an_explicit_end_and_a_window_with_nothing_stored() -> None:
    ctx = context(store_with())
    assert [p.session for p in load_series(ctx, ["EQ:AAA"], [CLOSE], D0, D0)["EQ:AAA"].points] == [
        D0
    ]
    early = load_series(ctx, ["EQ:AAA"], [CLOSE], date(2020, 1, 1), date(2020, 2, 1))
    assert early["EQ:AAA"].points == ()


def test_unknown_names_and_instrument_facts_are_refused() -> None:
    ctx = context(store_with())
    with pytest.raises(UnknownFeatureError):
        load_series(ctx, ["EQ:AAA"], ["rollup.nope@v1.x"], D0)
    with pytest.raises(ConfigurationError, match="no history"):
        load_series(ctx, ["EQ:AAA"], ["instrument.sector"], D0)
    with pytest.raises(ConfigurationError, match="after the session"):
        load_series(context(store_with(), D0), ["EQ:AAA"], [CLOSE], D0, D1)


def _count_range_reads(monkeypatch: pytest.MonkeyPatch, ctx: ReadContext) -> list[str]:
    reads: list[str] = []
    original = ctx.reader.table_range

    def spy(table: str, *args: Any, **kwargs: Any) -> Any:
        reads.append(table)
        return original(table, *args, **kwargs)

    monkeypatch.setattr(ctx.reader, "table_range", spy)
    return reads


def test_the_rows_of_a_stored_table_are_read_once_until_something_is_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = context(store_with())
    reads = _count_range_reads(monkeypatch, ctx)
    first = load_series(ctx, ["EQ:AAA"], [CLOSE], D0)
    assert load_series(ctx, ["EQ:AAA"], [CLOSE, HV20], D0)["EQ:AAA"].points[0].values == (50.0, 0.3)
    assert load_series(ctx, ["EQ:AAA"], [CLOSE], D0) == first
    assert reads == ["rollups/instrument/price_stats@v2"]  # one read for three requests
    load_series(ctx, ["EQ:AAA", "EQ:ETFX"], [CLOSE], D0)  # other ids, another window: a new key
    load_series(ctx, ["EQ:AAA"], [CLOSE], D1)
    assert len(reads) == 3
    seq = ctx.reader.visible_seq()
    monkeypatch.setattr(ctx.reader, "visible_seq", lambda: seq + 1)  # a publish
    load_series(ctx, ["EQ:AAA"], [CLOSE], D0)
    assert len(reads) == 4


def test_a_read_that_finds_nothing_is_cached_too_and_expressions_never_are(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = context(store_with())
    reads = _count_range_reads(monkeypatch, ctx)
    for _ in range(2):
        assert (
            load_series(ctx, ["EQ:AAA"], [CLOSE], date(2020, 1, 1), date(2020, 2, 1))[
                "EQ:AAA"
            ].points
            == ()
        )
    assert len(reads) == 1
    keys = [k for k in ctx.cache._items if k[0] == "series-frame"]
    load_series(ctx, ["EQ:AAA"], [FROM_HIGH], D0)
    assert [k for k in ctx.cache._items if k[0] == "series-frame"] == keys  # not stored here
