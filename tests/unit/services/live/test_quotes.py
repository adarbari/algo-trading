"""``LiveQuotes``: live quotes from a feed for an expiry's strikes, cached briefly, recorded in
the background, and the stored delayed chain with a status whenever the feed cannot answer."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.config.site.settings import IbkrSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.chains import live_option_quotes
from algotrade.services.live.quotes import (
    DisabledFeed,
    FeedUnavailableError,
    LiveQuotes,
)
from algotrade.services.live.recorder import LiveRecorder
from algotrade.services.read.context import NotFoundError, ReadContext, open_context
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.live_writer import LiveWriter
from algotrade_api.deps import ReadStore

EXPIRY = date(2022, 12, 23)  # the golden API store's first expiry of EQ:AAA (spot 100)
T0 = datetime(2022, 11, 25, 15, tzinfo=UTC)
OPTIONS = IbkrSettings(live_strikes=3, live_max_strikes=4, live_cache_s=60)


class FakeFeed:
    market_data_type = 3

    def __init__(self, error: Exception | None = None, unlisted: float | None = None) -> None:
        self.error, self.unlisted = error, unlisted
        self.asked: list[tuple[str, date, list[float]]] = []
        self.closed = False

    def quotes(self, symbol: str, expiry: date, strikes: Sequence[float]) -> pd.DataFrame:
        self.asked.append((symbol, expiry, list(strikes)))
        if self.error is not None:
            raise self.error
        rows = [
            {"strike": k, "right": r, "listed": k != self.unlisted, "conid": 7, "bid": 1.0,
             "ask": 1.2, "last": None, "close": 1.1, "volume": 5.0, "iv": 0.3, "delta": -0.4}
            for k in strikes
            for r in ("C", "P")
        ]  # fmt: skip
        return pd.DataFrame(rows)

    def close(self) -> None:
        self.closed = True


class FakeRecorder:
    def __init__(self) -> None:
        self.rows: list[pd.DataFrame] = []
        self.closed = False

    def submit(self, rows: pd.DataFrame) -> bool:
        self.rows.append(rows)
        return True

    def close(self) -> None:
        self.closed = True


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def live(
    feed: object, recorder: FakeRecorder | None = None, clock: Clock | None = None
) -> LiveQuotes:
    return LiveQuotes(feed, recorder, OPTIONS, clock or Clock())  # type: ignore[arg-type]


@pytest.fixture
def ctx(api_golden: tuple[ReadStore, dict[str, str]]) -> ReadContext:
    store = api_golden[0]
    return open_context(store.reader, store.configs, store.user, cache=store.cache)


def test_live_quotes_for_the_strikes_nearest_the_underlying(ctx: ReadContext) -> None:
    feed, recorder = FakeFeed(), FakeRecorder()
    got = live(feed, recorder).chain(ctx, "AAA", EXPIRY)
    assert feed.asked == [("AAA", EXPIRY, [95.0, 100.0, 105.0])]
    assert (got.source, got.status, got.detail, got.delayed) == ("ibkr", "LIVE", None, True)
    assert got.underlying_id == "EQ:AAA" and got.symbol == "AAA" and got.as_of == T0
    assert got.underlying_price == 100.0 and got.strikes == [95.0, 100.0, 105.0]
    first = got.quotes[0]
    assert first["instrument_id"] == "OPT:EQ:AAA:2022-12-23:C95"
    assert (first["right"], first["strike"], first["close"], first["delta"]) == (
        "C",
        95.0,
        1.1,
        -0.4,
    )
    assert [q["right"] for q in got.quotes[:2]] == ["C", "P"]
    recorded = recorder.rows[0]
    assert len(recorded) == 6 and set(recorded["market_data_type"]) == {3}
    assert set(recorded["symbol"]) == {"AAA"} and recorded["ts"].iloc[0] == pd.Timestamp(T0)


def test_an_answer_is_cached_for_the_window_then_read_again(ctx: ReadContext) -> None:
    feed, clock = FakeFeed(), Clock()
    quotes = live(feed, clock=clock)
    quotes.chain(ctx, "AAA", EXPIRY)
    clock.now = T0 + timedelta(seconds=59)
    again = quotes.chain(ctx, "EQ:AAA", EXPIRY)
    assert again.status == "CACHED" and again.as_of == T0 and len(feed.asked) == 1
    other = quotes.chain(ctx, "AAA", EXPIRY, [80.0])  # other strikes: another entry
    assert other.status == "LIVE" and len(feed.asked) == 2
    clock.now = T0 + timedelta(seconds=61)
    assert quotes.chain(ctx, "AAA", EXPIRY).status == "LIVE" and len(feed.asked) == 3


def test_named_strikes_must_be_listed_and_few_enough(ctx: ReadContext) -> None:
    feed = FakeFeed(unlisted=120.0)
    got = live(feed).chain(ctx, "AAA", EXPIRY, [120.0, 80.0, 80.0])
    assert got.strikes == [80.0, 120.0]
    unlisted = [q for q in got.quotes if q["strike"] == 120.0]
    assert unlisted and not any(q["listed"] for q in unlisted)
    with pytest.raises(ConfigurationError, match=r"strikes \[81.0\] are not in the stored chain"):
        live(feed).chain(ctx, "AAA", EXPIRY, [81.0])
    with pytest.raises(ConfigurationError, match="at most 4 strikes"):
        live(feed).chain(ctx, "AAA", EXPIRY, [80.0, 85.0, 90.0, 95.0, 100.0])


@pytest.mark.parametrize(
    ("feed", "status", "detail"),
    [
        (DisabledFeed("[ibkr] is disabled in sources.toml"), "DISABLED", "disabled"),
        (FakeFeed(FeedUnavailableError("UNAVAILABLE", "gateway down")), "UNAVAILABLE", "down"),
        (FakeFeed(RuntimeError("socket closed")), "ERROR", "RuntimeError: socket closed"),
    ],
)
def test_the_stored_chain_with_a_status_when_the_feed_cannot_answer(
    ctx: ReadContext, feed: object, status: str, detail: str
) -> None:
    recorder = FakeRecorder()
    got = live(feed, recorder).chain(ctx, "AAA", EXPIRY)
    assert (got.source, got.status, got.delayed) == ("stored", status, True)
    assert got.detail is not None and detail in got.detail
    assert got.session == date(2022, 11, 23) and got.strikes == [95.0, 100.0, 105.0]
    assert len(got.quotes) == 6 and all(q["listed"] and q["close"] is None for q in got.quotes)
    assert got.quotes[0]["iv"] is not None and got.quotes[0]["bid"] is not None
    assert got.as_of == datetime(2022, 11, 23, 21, tzinfo=UTC)
    assert recorder.rows == []  # nothing live to record


def test_unknown_underlying_or_expiry_is_not_found(ctx: ReadContext) -> None:
    with pytest.raises(NotFoundError, match="no 2022-12-30 expiry"):
        live(FakeFeed()).chain(ctx, "AAA", date(2022, 12, 30))
    with pytest.raises(NotFoundError, match="no option chain"):
        live(FakeFeed()).chain(ctx, "BBB", EXPIRY)
    with pytest.raises(NotFoundError):
        live(FakeFeed()).chain(ctx, "NOPE", EXPIRY)


def test_close_stops_the_feed_and_the_recorder() -> None:
    feed, recorder = FakeFeed(), FakeRecorder()
    live(feed, recorder).close()
    assert feed.closed and recorder.closed
    live(DisabledFeed("off")).close()  # nothing to stop


def test_a_live_answer_is_recorded_to_the_store(ctx: ReadContext) -> None:
    backend = MemoryBackend()
    recorder = LiveRecorder(LiveWriter(backend))
    feed = FakeFeed(unlisted=105.0)
    feed_rows = feed.quotes
    feed.quotes = lambda *a: feed_rows(*a).assign(  # type: ignore[method-assign]
        conid=lambda f: [7.0 if listed else None for listed in f["listed"]], iv=None
    )
    live(feed, recorder).chain(ctx, "AAA", EXPIRY)
    recorder.flush()
    frame = live_option_quotes(StoreReader(backend), date(2022, 11, 25), ["EQ:AAA"])
    assert frame is not None and sorted(set(frame["strike"])) == [95.0, 100.0]  # listed only
    assert frame["conid"].tolist() == [7] * 4 and frame["iv"].isna().all()
    assert set(frame["source"]) == {"ibkr"} and set(frame["market_data_type"]) == {3}
    recorder.close()
