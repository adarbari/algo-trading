"""Chain reads filter by underlying (``algotrade.data.chains``)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.chains import (
    CHRONIC,
    chain_expiries,
    chain_labels,
    chain_status,
    live_option_quotes,
    option_quotes,
    tolerated_stale,
    underlying_quotes,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.live_writer import LiveWriter
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import chain_status_rows, stamped

DAY = date(2026, 10, 1)
TS = pd.Timestamp("2026-10-01T20:00", tz="UTC")


def option(contract: str, underlying: str) -> dict[str, object]:
    return {
        "instrument_id": contract,
        "underlying_id": underlying,
        "ts": TS,
        "expiry": date(2026, 11, 20),
        "right": "P",
        "strike": 100.0,
        "bid": 1.0,
        "ask": 1.1,
        "volume": 10.0,
        "open_interest": 100.0,
        "iv": 0.3,
        "delta": -0.3,
    }


def test_option_quotes_filter_on_the_underlying() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    assert option_quotes(reader, DAY, ["EQ:A"]) is None
    rows = [option("OPT:A1", "EQ:A"), option("OPT:A2", "EQ:A"), option("OPT:B1", "EQ:B")]
    writer.write_table("chains/option_quotes", DAY, "c", stamped(rows, DAY, "c"))
    only_a = option_quotes(reader, DAY, ["EQ:A"])
    assert only_a is not None and list(only_a["instrument_id"]) == ["OPT:A1", "OPT:A2"]
    every = option_quotes(reader, DAY)
    assert every is not None and len(every) == 3


def test_underlying_quotes_and_status() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    with pytest.raises(MissingDataError, match="algotrade-ingest chains"):
        chain_status(reader, DAY, hint="algotrade-ingest chains")
    assert chain_status(reader, DAY) is None
    status = [{"instrument_id": i, "status": "OK"} for i in ("EQ:A", "EQ:B")]
    writer.write_table("chains/status", DAY, "c", stamped(status, DAY, "c"))
    quote = {"symbol": "A", "ts": TS, "price": 1.0, "close": 1.0, "volume": 1.0, "iv30": 0.2}
    quotes = [{"instrument_id": i, **quote} for i in ("EQ:A", "EQ:B")]
    writer.write_table("chains/underlying_quotes", DAY, "c", stamped(quotes, DAY, "c"))
    got = chain_status(reader, DAY, ["EQ:B"])
    assert got is not None and list(got["instrument_id"]) == ["EQ:B"]
    under = underlying_quotes(reader, DAY, ["EQ:A"])
    assert under is not None and list(under["instrument_id"]) == ["EQ:A"]


def test_chain_expiries_one_pruned_read_per_underlying_in_the_session_only() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    assert chain_expiries(reader, DAY, ["EQ:A"]) == {}
    near, far = date(2026, 10, 9), date(2026, 11, 20)
    rows = [option("OPT:A1", "EQ:A"), option("OPT:A2", "EQ:A"), option("OPT:B1", "EQ:B")]
    rows[1]["expiry"] = near
    writer.write_table("chains/option_quotes", DAY, "c", stamped(rows, DAY, "c"))
    later = date(2026, 10, 2)
    writer.write_table(
        "chains/option_quotes", later, "d", stamped([option("OPT:C", "EQ:C")], later, "d")
    )
    assert chain_expiries(reader, DAY, ["EQ:A", "EQ:C"]) == {"EQ:A": [near, far]}


def test_live_option_quotes_keep_every_snapshot_and_filter_on_the_underlying() -> None:
    backend = MemoryBackend()
    writer, reader = LiveWriter(backend), StoreReader(backend)
    assert live_option_quotes(reader, DAY) is None
    for n, run in enumerate(("l1", "l2")):
        rows = [
            {**option(c, u), "ts": TS + pd.Timedelta(minutes=n), "close": None}
            for c, u in (("OPT:A1", "EQ:A"), ("OPT:B1", "EQ:B"))
        ]
        for row in rows:
            row.pop("open_interest")
        with writer.publishing(run, TS.to_pydatetime()):
            writer.write_live("live/option_quotes", DAY, run, stamped(rows, DAY, run))
    only_a = live_option_quotes(reader, DAY, ["EQ:A"])
    assert only_a is not None and list(only_a["instrument_id"]) == ["OPT:A1", "OPT:A1"]
    every = live_option_quotes(reader, DAY)
    assert every is not None and len(every) == 4


SOURCES = SourcesSettings()  # 2% of core and 20% of rest may be stale; 2% fetch failures


def test_tolerated_stale_lists_the_stale_names_when_every_tier_is_within_its_limit() -> None:
    frame = pd.DataFrame(chain_status_rows(50, 1, 50, 10))  # exactly 2% and 20%
    found = tolerated_stale(frame, DAY, SOURCES)
    assert sorted(found) == ["EQ:C0", *sorted(f"EQ:R{i}" for i in range(10))]
    assert set(found.values()) == {"STALE_DATA: chain is for 2026-10-01"}


@pytest.mark.parametrize(
    ("core_stale", "rest_stale", "fetch_errors"),
    [(2, 0, 0), (0, 11, 0), (1, 10, 5)],  # core over, rest over, fetch failures over 2%
)
def test_tolerated_stale_is_empty_when_any_limit_is_exceeded(
    core_stale: int, rest_stale: int, fetch_errors: int
) -> None:
    frame = pd.DataFrame(chain_status_rows(50, core_stale, 50, rest_stale, fetch_errors))
    assert tolerated_stale(frame, DAY, SOURCES) == {}


def test_tolerated_stale_fails_closed_without_core_names_or_a_status() -> None:
    no_core = pd.DataFrame(chain_status_rows(0, 0, 50, 1))  # tiered, but no core: inputs missing
    assert tolerated_stale(no_core, DAY, SOURCES) == {}
    assert tolerated_stale(None, DAY, SOURCES) == {}
    assert tolerated_stale(pd.DataFrame(), DAY, SOURCES) == {}


def test_a_status_without_tiers_counts_as_rest() -> None:
    frame = pd.DataFrame(chain_status_rows(0, 0, 10, 2)).drop(columns="tier")
    assert len(tolerated_stale(frame, DAY, SOURCES)) == 2  # 20% of rest
    assert (
        tolerated_stale(
            pd.DataFrame(chain_status_rows(0, 0, 10, 3)).drop(columns="tier"), DAY, SOURCES
        )
        == {}
    )


# A chain the feed has served stale for more than ``max_chain_stale_sessions`` sessions is not
# a feed that has not rolled yet: it is a fetch failure, for the gate and the screens alike.
LATE = date(2026, 10, 6)  # 2026-09-23 is 9 sessions before it; 2026-09-29 is 5


def test_a_chain_stale_for_more_than_the_limit_is_labelled_a_fetch_failure() -> None:
    frame = pd.DataFrame(
        [
            {"status": "STALE_DATA: chain is for 2026-09-23"},  # 9 sessions old
            {"status": "STALE_DATA: chain is for 2026-09-29"},  # 5: at the limit, still stale
            {"status": "STALE_DATA"},  # no date: its age is unknown, stale as recorded
            {"status": "OK"},
        ]
    )
    labels = chain_labels(frame, LATE, max_stale_sessions=5)
    assert list(labels) == [CHRONIC, "STALE_DATA", "STALE_DATA", "OK"]
    assert chain_labels(frame, LATE, max_stale_sessions=10).iloc[0] == "STALE_DATA"


def test_a_chronically_stale_chain_is_never_tolerated() -> None:
    frame = pd.DataFrame(chain_status_rows(50, 0, 50, 1, chain_day="2026-09-23"))
    assert tolerated_stale(frame, LATE, SOURCES) == {}  # a fetch failure (1%), not excluded
    at_limit = pd.DataFrame(chain_status_rows(50, 0, 50, 1, chain_day="2026-09-29"))
    assert list(tolerated_stale(at_limit, LATE, SOURCES)) == ["EQ:R0"]


def test_chronically_stale_chains_count_against_the_fetch_failure_limit() -> None:
    chronic = chain_status_rows(50, 0, 50, 3, chain_day="2026-09-23")  # 3% failed
    fresh = chain_status_rows(0, 0, 1, 1, chain_day="2026-10-05")
    fresh[0] |= {"instrument_id": "EQ:F0", "symbol": "F0"}
    assert tolerated_stale(pd.DataFrame([*chronic, *fresh]), LATE, SOURCES) == {}
