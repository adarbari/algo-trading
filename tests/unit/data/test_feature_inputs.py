"""Feature inputs asked of ``algotrade.data`` by table name: each table's point-in-time read
(bars, earnings snapshots, chain partitions, events by event date, the Treasury curve, share
facts, the reference's security types, IBKR vols, the universe snapshot, the symbol -> id
map, macro series by vintage and id) and other groups' stored rows (instrument and market
groups), with this run's rows winning."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import next_session, sessions_between
from algotrade.data import feature_inputs as inputs
from algotrade.data import prices
from algotrade.data.macro.series import TABLE as MACRO_SERIES
from algotrade.data.shares import TABLE as SHARES
from tests.helpers.rollup_store import (
    END,
    series,
    store,
    write_bars,
    write_curve,
    write_dividends,
    write_split,
)
from tests.helpers.stored_frames import stamped, universe_rows, write_reference


def test_loaders() -> None:
    assert inputs.sessions_before(date(2026, 10, 5), 1) == date(2026, 10, 2)  # Mon -> Fri
    assert inputs.sessions_before(date(2026, 10, 4), 0) == date(2026, 10, 2)  # Sunday
    _, reader = store()
    chains = inputs.load_input(reader, "chains/status", [END], 0)
    assert chains.at(END, 0) is None
    with pytest.raises(ValueError, match="lookback"):
        chains.at(END, 1)
    assert inputs.load_input(reader, "events/earnings", [END], 0).at(END, 0) is None
    assert inputs.load_input(reader, "bars/1d", [END], 3).at(END, 3) is None
    with pytest.raises(KeyError, match="no feature input"):
        inputs.load_input(reader, "bars/5m", [END], 0)


def test_rollup_input_reads_store_and_this_runs_rows_win() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(5)})
    table = "rollups/instrument/up@v1"
    for i, day in enumerate(days[:4]):
        rows = stamped([{"instrument_id": "EQ:A", "v": float(i)}], day, f"r{i}")
        writer.write_table(table, day, f"r{i}", rows)
    mine = pd.DataFrame({"instrument_id": ["EQ:A"], "v": [99.0]})
    loaded = inputs.load_input(reader, table, days[2:], 2, {table: {days[3]: mine, days[4]: None}})
    window = loaded.at(days[3], 2)
    assert window is not None
    assert list(window["v"]) == [1.0, 2.0, 99.0] and list(window["session_date"]) == days[1:4]
    assert "run_id" not in window.columns
    assert loaded.at(days[4], 2) is None  # computed here with no rows: no stale stored rows
    assert inputs.load_input(reader, "rollups/instrument/none@v1", [END], 0).at(END, 0) is None
    assert inputs.has_input(table) and not inputs.has_input("bars/7m")
    assert inputs.has_input("rollups/market/breadth@v1") and inputs.is_group_table(table)
    assert not inputs.is_group_table("rollups/market/")


def test_universe_is_the_snapshot_the_session_sees_and_none_before_the_first() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(4)})
    universe = inputs.load_input(reader, "universe", days, 0)
    assert universe.at(days[0], 0) is None  # nothing stored
    writer.write_table("universe", days[1], "u1", stamped(universe_rows(["A", "B"]), days[1], "u1"))
    writer.write_table("universe", days[3], "u3", stamped(universe_rows(["A"]), days[3], "u3"))
    universe = inputs.load_input(reader, "universe", days, 0)
    assert universe.at(days[0], 0) is None  # only later lists: survivorship, so none
    seen = universe.at(days[2], 0)
    assert seen is not None and sorted(seen["instrument_id"]) == ["EQ:A", "EQ:B"]
    latest = universe.at(days[3], 0)
    assert latest is not None and list(latest["instrument_id"]) == ["EQ:A"]


def test_symbol_ids_resolve_through_the_reference_the_session_sees() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(3)})
    ids = inputs.load_input(reader, "instruments/symbol_ids", days, 0)
    assert ids.at(days[0], 0) is None  # no reference stored
    write_reference(writer, days[1], {"SPY": "EQ:BBG000BDTBL9", "A": "EQ:A"})
    ids = inputs.load_input(reader, "instruments/symbol_ids", days, 0)
    early, on = ids.at(days[0], 0), ids.at(days[1], 0)
    assert on is not None and on.to_dict("list") == {
        "symbol": ["A", "SPY"],
        "instrument_id": ["EQ:A", "EQ:BBG000BDTBL9"],
        "pre_snapshot": [False, False],
    }
    assert early is not None and list(early["pre_snapshot"]) == [True, True]


def test_event_inputs_are_by_event_date_and_never_later() -> None:
    writer, reader = store()
    write_dividends(
        writer,
        [
            ("EQ:A", END - timedelta(days=30), 0.5, "recurring"),
            ("EQ:A", END + timedelta(days=10), 0.5, "recurring"),  # declared, not yet ex
        ],
    )
    write_split(writer, "EQ:A", END - timedelta(days=3), 2.0, END)
    divs = inputs.load_input(reader, "events/dividend", [END], 30).at(END, 30)
    assert divs is not None and list(divs["event_date"]) == [END - timedelta(days=30)]
    assert "session_date" not in divs.columns
    splits = inputs.load_input(reader, "events/split", [END], 1).at(END, 1)
    assert splits is not None and splits.empty  # 3 days back is outside 1 session
    _, empty = store()
    assert inputs.load_input(empty, "events/dividend", [END], 5).at(END, 5).empty  # type: ignore[union-attr]


def test_rates_input_is_the_curve_the_session_sees() -> None:
    writer, reader = store()
    loaded = inputs.load_input(reader, "rates/treasury", [END], 0)
    assert loaded.at(END, 0) is None
    write_curve(writer, END - timedelta(days=1), 0.04)
    frame = loaded.at(END, 0)
    assert frame is not None and set(frame["curve_date"]) == {END - timedelta(days=1)}
    assert list(frame["tenor_days"]) == [30, 91, 365] and not frame["pre_snapshot"].any()


def test_share_facts_are_seen_from_their_filing_date() -> None:
    writer, reader = store()
    assert inputs.load_input(reader, SHARES, [END], 0).at(END, 0) is None
    early, late = END - timedelta(days=30), END + timedelta(days=5)
    rows = [
        {"instrument_id": "EQ:A", "cik": "1", "concept": "dei", "shares": n, "period_start": None,
         "period_end": f, "filed": f, "fetched_on": late}
        for n, f in ((10.0, early), (12.0, late))
    ]  # fmt: skip
    writer.write_table(SHARES, late, "r1", stamped(rows, late, "r1"))  # stored after both
    loaded = inputs.load_input(reader, SHARES, [END], 0)
    seen = loaded.at(END, 0)
    assert seen is not None and list(seen["shares"]) == [10.0]  # the later filing is not seen
    assert loaded.at(early - timedelta(days=1), 0) is None


def test_ibkr_vols_are_the_session_and_earlier_rows_merged_per_instrument() -> None:
    """``volatility/ibkr_iv30`` (``data.volatility.ibkr_iv30``): runs merge per instrument
    (a later history run replaces a snapshot); ``None`` without a row on the session."""
    writer, reader = store()
    days = [END - timedelta(days=d) for d in (3, 2, 1)] + [END]
    table = "volatility/ibkr_iv30"
    for i, day in enumerate(days[:-1]):
        rows = [{"instrument_id": "EQ:A", "iv30_ibkr": 0.2 + i / 100, "hv30_ibkr": 0.1,
                 "source_kind": "history"}]  # fmt: skip
        writer.write_table(table, day, "h", stamped(rows, day, "h"))
    snap = [{"instrument_id": "EQ:A", "iv30_ibkr": 0.5, "hv30_ibkr": None,
             "source_kind": "snapshot"}]  # fmt: skip
    writer.write_table(table, days[2], "s", stamped(snap, days[2], "s"))
    loaded = inputs.load_input(reader, table, [days[2]], 2)
    window = loaded.at(days[2], 2)
    assert window is not None
    assert list(window["iv30_ibkr"]) == pytest.approx([0.2, 0.21, 0.5])  # the later run wins
    assert list(window["source_kind"]) == ["history", "history", "snapshot"]
    assert inputs.load_input(reader, table, [END], 3).at(END, 3) is None  # nothing on END


def test_reference_input_is_the_security_types_the_session_sees() -> None:
    writer, reader = store()
    assert inputs.load_input(reader, "instruments/reference", [END], 0).at(END, 0) is None
    rows = [
        {"instrument_id": "EQ:A", "symbol": "A", "asset_class": "equity", "multiplier": 1.0,
         "security_type": "ADR", "status": "ACTIVE"},
        {"instrument_id": "EQ:B", "symbol": "B", "asset_class": "equity", "multiplier": 1.0,
         "security_type": "COMMON_STOCK", "status": "ACTIVE"},
    ]  # fmt: skip
    writer.write_table("instruments/reference", END, "r", stamped(rows, END, "r"))
    seen = inputs.load_input(reader, "instruments/reference", [END], 0).at(END, 0)
    assert seen is not None and list(seen.columns) == ["instrument_id", "security_type"]
    assert dict(zip(seen["instrument_id"], seen["security_type"], strict=True)) == {
        "EQ:A": "ADR",
        "EQ:B": "COMMON_STOCK",
    }


def test_a_bars_window_never_spans_a_missing_session() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(6)}, skip={"EQ:A": [2]})  # no bars that session
    loaded = inputs.load_input(reader, "bars/1d", [days[5]], 5)
    with pytest.raises(MissingDataError, match=f"no bars for {days[2]} in the 6-session window"):
        loaded.at(days[5], 5)
    assert loaded.at(days[5], 2) is not None  # days[3..5]: no gap


def test_bars_windows_allow_the_start_of_history_and_one_names_gap() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(4), "EQ:B": series(4)}, skip={"EQ:B": [1]})
    window = inputs.load_input(reader, "bars/1d", [days[3]], 20).at(days[3], 20)
    assert window is not None  # 20 sessions back is before the first stored one: not a gap
    assert sorted(window["session_date"].unique()) == days  # B's missing bar is not a gap


def test_macro_series_are_seen_from_their_vintage_and_read_by_id() -> None:
    writer, reader = store()
    assert inputs.load_input(reader, MACRO_SERIES, [END], 0).at(END, 0) is None
    early, late = END - timedelta(days=30), END + timedelta(days=5)
    rows = [
        {"instrument_id": iid, "series": iid[6:], "obs_date": early, "vintage_date": v,
         "value": x, "vintage_kind": "alfred"}
        for iid, v, x in (("MACRO:A", early, 1.0), ("MACRO:A", late, 1.5), ("MACRO:B", early, 9.0))
    ]  # fmt: skip
    writer.write_table(MACRO_SERIES, late, "r1", stamped(rows, late, "r1"))  # stored after all
    loaded = inputs.load_input(reader, MACRO_SERIES, [END], 0, ids=("MACRO:A",))
    seen = loaded.at(END, 0)
    assert seen is not None and list(seen["value"]) == [1.0]  # the revision is not out yet
    assert "session_date" not in seen.columns
    later = loaded.at(late, 0)  # only the latest vintage of each observation
    assert later is not None and list(later["value"]) == [1.5]
    assert list(later["vintage_date"]) == [late]
    assert loaded.at(early - timedelta(days=1), 0) is None
    every = inputs.load_input(reader, MACRO_SERIES, [END], 0).at(END, 0)
    assert every is not None and set(every["instrument_id"]) == {"MACRO:A", "MACRO:B"}
    assert inputs.has_input(MACRO_SERIES)
    with pytest.raises(ValueError, match="read whole"):
        inputs.load_input(reader, SHARES, [END], 0, ids=("EQ:A",))


def test_macro_series_keep_the_lookback_window_and_each_series_latest() -> None:
    writer, reader = store()
    old, recent = END - timedelta(days=400), END - timedelta(days=3)
    rows = [
        {"instrument_id": iid, "series": iid[6:], "obs_date": d, "vintage_date": d,
         "value": x, "vintage_kind": "lagged"}
        for iid, d, x in (("MACRO:A", old, 1.0), ("MACRO:A", recent, 2.0), ("MACRO:B", old, 7.0))
    ]  # fmt: skip
    writer.write_table(MACRO_SERIES, END, "r1", stamped(rows, END, "r1"))
    seen = inputs.load_input(reader, MACRO_SERIES, [END], 20).at(END, 20)
    assert seen is not None  # A's old value is outside 20 sessions; B's only one is its latest
    assert list(zip(seen["instrument_id"], seen["value"], strict=True)) == [
        ("MACRO:A", 2.0),
        ("MACRO:B", 7.0),
    ]


def test_the_newest_session_reads_what_it_knew_from_its_own_partition() -> None:
    """The backfill's partition date is the last session of the chunk: a lag-1 series whose
    last observation is that session (public the day after) gives the previous day's value; an
    ALFRED vintage dated on the session is known by it."""
    writer, reader = store()
    days = sessions_between(END - timedelta(days=10), END)
    lagged = [
        {"instrument_id": "MACRO:HY", "series": "HY", "obs_date": d, "vintage_date": nxt,
         "value": float(i), "vintage_kind": "lagged"}
        for i, (d, nxt) in enumerate(zip(days, [*days[1:], END + timedelta(days=1)], strict=True))
    ]  # fmt: skip
    alfred = {"instrument_id": "MACRO:UR", "series": "UR", "obs_date": END - timedelta(days=35),
              "vintage_date": END, "value": 4.2, "vintage_kind": "alfred"}  # fmt: skip
    writer.write_table(MACRO_SERIES, END, "r1", stamped([*lagged, alfred], END, "r1"))
    loaded = inputs.load_input(reader, MACRO_SERIES, days, 0)
    seen = loaded.at(END, 0)
    assert seen is not None
    latest = seen.groupby("instrument_id").tail(1).set_index("instrument_id")
    assert latest.loc["MACRO:HY", "obs_date"] == days[-2]  # END's own is public tomorrow
    assert latest.loc["MACRO:HY", "value"] == float(len(days) - 2)
    assert latest.loc["MACRO:UR", "value"] == 4.2  # a vintage on the session is known by it


def test_bar_windows_are_the_closes_of_each_window_up_to_the_session() -> None:
    writer, reader = store()
    first, last = date(2020, 2, 12), date(2020, 3, 13)
    days = sessions_between(first, date(2020, 4, 3))
    write_bars(writer, {"EQ:A": series(len(days)), "EQ:B": series(len(days), seed=2)}, days[-1])
    windows = ((first, last), (date(2019, 1, 2), date(2019, 2, 1)))  # the 2nd: before the store
    loaded = inputs.load_input(reader, "bars/1d", [days[10], days[-1]], 0, windows=windows)
    early = loaded.at(days[10], 0)
    assert early is not None
    assert set(early["window"]) == {0} and early["day"].max() == pd.Timestamp(days[10])
    assert early["day"].is_monotonic_increasing and len(early) == 2 * 11
    full = loaded.at(days[-1], 0)
    assert full is not None and full["day"].max() == pd.Timestamp(last)  # the window ends at last
    assert list(full.columns) == ["window", "day", "instrument_id", "close"]
    assert full["instrument_id"].dtype == "category"
    assert loaded.at(first - timedelta(days=20), 0) is None


def test_bar_windows_share_one_adjustment_so_a_split_inside_one_leaves_its_ratios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prices, "WINDOW_PIECE", 4)  # the split is in a later piece than most bars
    writer, reader = store()
    days = sessions_between(date(2020, 2, 12), date(2020, 3, 13))
    write_bars(writer, {"EQ:A": [100.0] * 10 + [50.0] * (len(days) - 10)}, days[-1])
    write_split(writer, "EQ:A", days[10], 2.0, days[10])
    loaded = inputs.load_input(reader, "bars/1d", [days[-1]], 0, windows=((days[0], days[-1]),))
    frame = loaded.at(days[-1], 0)
    assert frame is not None and set(frame["close"].round(6)) == {50.0}


def test_windows_are_only_for_tables_that_declare_them() -> None:
    _, reader = store()
    with pytest.raises(ValueError, match="no fixed windows"):
        inputs.load_input(reader, "events/earnings", [END], 0, windows=((END, END),))


def test_bars_by_symbol_read_only_the_ids_the_reference_resolves_each_session() -> None:
    """``symbols`` narrows ``bars/1d`` to the ids the tickers resolve to in the snapshot each
    session of the chunk sees (the union): a ticker whose id changes inside the chunk keeps
    both ids' bars; other instruments are not read."""
    writer, reader = store()
    days = write_bars(writer, {"EQ:OLD": series(4), "EQ:NEW": series(4, 2), "EQ:X": series(4, 3)})
    write_reference(writer, days[0], {"SPY": "EQ:OLD", "X": "EQ:X"})
    write_reference(writer, days[2], {"SPY": "EQ:NEW", "X": "EQ:X"}, run_id="ref2")
    loaded = inputs.load_input(reader, "bars/1d", days, 1, symbols=("SPY", "QQQ"))
    for day in (days[1], days[3]):
        frame = loaded.at(day, 1)
        assert frame is not None and set(frame["instrument_id"]) == {"EQ:OLD", "EQ:NEW"}
    early = inputs.load_input(reader, "bars/1d", days[:2], 1, symbols=("SPY",))
    assert set(early.at(days[1], 1)["instrument_id"]) == {"EQ:OLD"}  # type: ignore[index]
    unlisted = inputs.load_input(reader, "bars/1d", days, 0, symbols=("QQQ",)).at(days[3], 0)
    assert unlisted is not None and unlisted.empty  # bars are stored: input, none of QQQ's
    assert loaded.at(next_session(days[3]), 0) is None  # no bars stored for the session
    with pytest.raises(ValueError, match="symbols are only for"):
        inputs.load_input(reader, "events/split", days, 0, symbols=("SPY",))


def test_bars_by_symbol_without_a_reference_are_empty_and_without_bars_none() -> None:
    writer, reader = store()
    assert inputs.load_input(reader, "bars/1d", [END], 0, symbols=("A",)).at(END, 0) is None
    days = write_bars(writer, {"EQ:A": series(3)})
    frame = inputs.load_input(reader, "bars/1d", days, 0, symbols=("A",)).at(days[-1], 0)
    assert frame is not None and frame.empty and "close" in frame.columns


def test_a_bar_window_never_spans_a_missing_session() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(30)}, skip={"EQ:A": [12]})  # no bars that session
    window = ((days[0], days[-1]),)
    with pytest.raises(MissingDataError, match=f"no bars for {days[12]} in the window"):
        inputs.load_input(reader, "bars/1d", [days[-1]], 0, windows=window)
    # a window that ends before the gap, or starts before the first stored session, is whole
    whole = ((days[0], days[11]),)
    assert (
        inputs.load_input(reader, "bars/1d", [days[-1]], 0, windows=whole).at(days[-1], 0)
        is not None
    )
    early = ((days[0] - timedelta(days=40), days[5]),)
    assert (
        inputs.load_input(reader, "bars/1d", [days[-1]], 0, windows=early).at(days[-1], 0)
        is not None
    )


def test_bar_windows_hold_only_instruments_with_a_bar_in_the_chunk() -> None:
    writer, reader = store()  # EQ:GONE trades only on the first ten sessions
    days = write_bars(
        writer, {"EQ:A": series(30), "EQ:GONE": series(30)}, skip={"EQ:GONE": list(range(10, 30))}
    )
    loaded = inputs.load_input(reader, "bars/1d", [days[-1]], 0, windows=((days[0], days[-1]),))
    frame = loaded.at(days[-1], 0)
    assert frame is not None and set(frame["instrument_id"].astype(str)) == {"EQ:A"}
    both = inputs.load_input(reader, "bars/1d", days[5:], 0, windows=((days[0], days[-1]),))
    seen = both.at(days[-1], 0)
    assert seen is not None and set(seen["instrument_id"].astype(str)) == {"EQ:A", "EQ:GONE"}
