"""Feature inputs asked of ``algotrade.data`` by table name: each table's point-in-time read
(bars, earnings snapshots, chain partitions, events by event date, the Treasury curve, share
facts, the reference's security types, IBKR vols, macro series by vintage and id) and other
groups' stored rows, with this
run's rows winning."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data import feature_inputs as inputs
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
from tests.helpers.stored_frames import stamped


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
    later = loaded.at(late, 0)
    assert later is not None and list(later["vintage_date"]) == [early, late]
    assert loaded.at(early - timedelta(days=1), 0) is None
    every = inputs.load_input(reader, MACRO_SERIES, [END], 0).at(END, 0)
    assert every is not None and set(every["instrument_id"]) == {"MACRO:A", "MACRO:B"}
    assert inputs.has_input(MACRO_SERIES)
    with pytest.raises(ValueError, match="read whole"):
        inputs.load_input(reader, SHARES, [END], 0, ids=("EQ:A",))
