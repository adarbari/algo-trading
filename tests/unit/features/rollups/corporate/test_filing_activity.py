"""``filing_activity@v1``: 8-K counts and earnings reaction windows in the last 5 sessions,
known_from <= S, and the nulls that stop an unknown being read as "no news"."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.rollups.corporate import earnings, filing_activity
from algotrade.features.rollups.corporate.filing_activity import FILINGS, GROUP
from algotrade.features.rollups.price import price_stats
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END, series, store, write_bars, write_earnings, write_rows
from tests.helpers.stored_frames import stamped

SESSION = END
GRID = sessions_ending(SESSION, 12)
STATS = pd.DataFrame(
    {"instrument_id": ["EQ:A", "EQ:B", "EQ:C"], "session_date": SESSION, "history_days": 252}
)


def _filings(rows: list[tuple[str, date]]) -> pd.DataFrame:
    frame = [
        {"instrument_id": i, "ts": pd.Timestamp(k, tz="UTC"), "known_from": k,
         "accession": f"{i}-{k}", "form": "8-K"}
        for i, k in rows
    ]  # fmt: skip
    return stamped(frame, SESSION, "f")


def _compute(filings: pd.DataFrame | None, earn: pd.DataFrame | None = None) -> pd.DataFrame:
    inputs = {filing_activity.PRICE_STATS: STATS, FILINGS: filings, earnings.EVENTS: earn}
    return filing_activity.compute(inputs, SESSION, None).set_index("instrument_id")


def _earn(rows: list[tuple[str, date]]) -> pd.DataFrame:
    frame = [
        {"instrument_id": i, "ts": pd.Timestamp(d, tz="UTC"), "time": "unknown",
         "known_from": d, "reported": True}
        for i, d in rows
    ]  # fmt: skip
    return stamped(frame, SESSION, "e")


def test_counts_filings_known_in_the_window() -> None:
    start = sessions_ending(SESSION, 5)[0]
    old = GRID[0]  # before the window: seen, so a zero is knowable
    out = _compute(
        _filings([("EQ:A", start), ("EQ:A", SESSION), ("EQ:B", old), ("EQ:C", SESSION)]),
    )
    assert out["filing_count_5d"].tolist() == [2, 0, 1]  # the window's first session counts


def test_an_instrument_with_no_filing_known_is_unknown_not_zero() -> None:
    out = _compute(_filings([("EQ:A", SESSION), ("EQ:B", GRID[0])]))
    assert out["filing_count_5d"].isna().tolist() == [False, False, True]


def test_a_backfill_that_starts_after_the_window_knows_nothing() -> None:
    out = _compute(_filings([("EQ:A", SESSION), ("EQ:B", SESSION)]))
    assert out["filing_count_5d"].isna().all()  # nothing stored before the window: no zeros


def test_no_filing_table_is_all_unknown() -> None:
    assert _compute(None)["filing_count_5d"].isna().all()
    assert _compute(_filings([]).iloc[0:0])["filing_count_5d"].isna().all()


def test_a_filing_known_after_the_session_never_counts() -> None:
    later = SESSION + timedelta(days=3)
    out = _compute(_filings([("EQ:A", GRID[0]), ("EQ:A", later), ("EQ:B", GRID[0])]))
    assert out["filing_count_5d"].tolist()[:2] == [0, 0]  # the later one is invisible


def test_earnings_in_the_window_and_the_session_before_it() -> None:
    first = sessions_ending(SESSION, 6)[0]  # its reaction window ends on the window's first day
    out = _compute(
        None,
        _earn([("EQ:A", SESSION), ("EQ:B", first), ("EQ:C", sessions_ending(SESSION, 7)[0])]),
    )
    assert out["earnings_in_5d"].tolist() == [True, True, False]


def test_earnings_unknown_without_any_report_and_a_future_report_is_not_news() -> None:
    out = _compute(None, _earn([("EQ:A", SESSION + timedelta(days=2)), ("EQ:B", GRID[0])]))
    flags = out["earnings_in_5d"]
    assert flags["EQ:A"] is False or not flags["EQ:A"]  # reports later: not in the window
    assert flags["EQ:B"] is False or not flags["EQ:B"]
    assert pd.isna(flags["EQ:C"])  # no report known at all


def test_runs_through_the_store_with_known_from() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(260), "EQ:B": series(260, 2)})
    write_rows(  # EQ:A filed on the session, EQ:B long before; the 8-K of EQ:B on D+1 is unknown
        writer, "events/filing", SESSION,
        [
            {"instrument_id": "EQ:A", "ts": pd.Timestamp(SESSION, tz="UTC"), "known_from": SESSION,
             "accession": "a1", "form": "8-K", "cik": "1", "filing_date": SESSION, "items": "7.01"},
            {"instrument_id": "EQ:B", "ts": pd.Timestamp(GRID[0], tz="UTC"), "known_from": GRID[0],
             "accession": "b1", "form": "8-K", "cik": "2", "filing_date": GRID[0], "items": "7.01"},
        ],
    )  # fmt: skip
    write_earnings(writer, GRID[0], [("EQ:A", GRID[0] - timedelta(days=60), "pre_market")])
    out = compute_in_memory(reader, [price_stats.GROUP, GROUP], [SESSION])
    frame = out[GROUP.key][0].frame
    assert frame is not None
    rows = frame.set_index("instrument_id")
    assert rows["filing_count_5d"].to_dict() == {"EQ:A": 1, "EQ:B": 0}
    assert bool(rows.loc["EQ:A", "earnings_in_5d"]) is False
    assert pd.isna(rows.loc["EQ:B", "earnings_in_5d"])


def test_volume_shock_and_news_free_flags() -> None:
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    ids = ["EQ:QUIET", "EQ:NEWS", "EQ:EARN", "EQ:EDGE", "EQ:LOWVOL", "EQ:UNK", "EQ:NOVOL"]
    vol = pd.DataFrame(
        {
            "instrument_id": ids,
            "session_date": END,
            "volume_z_20d": [3.0, 3.0, 3.0, 2.0, 0.5, 3.0, np.nan],
        }
    ).astype({"volume_z_20d": "float32"})
    filings = pd.DataFrame(
        {
            "instrument_id": ids,
            "session_date": END,
            "filing_count_5d": pd.array([0, 2, 0, 0, 0, None, 0], dtype="Int64"),
            "earnings_in_5d": pd.array(
                [False, False, True, False, False, False, None], dtype="boolean"
            ),
        }
    )
    frames = {"rollups/instrument/volume@v1": vol, "rollups/instrument/filing_activity@v1": filings}
    out = fs.evaluate(frames, ["volume_shock", "news_free_5d", "volume_shock_no_news"])
    out = out.set_index("instrument_id")
    assert out["news_free_5d"].to_dict() == {
        "EQ:QUIET": True,
        "EQ:NEWS": False,  # two 8-Ks
        "EQ:EARN": False,  # a reaction window in the last 5 sessions
        "EQ:EDGE": True,
        "EQ:LOWVOL": True,
        "EQ:UNK": None,  # filings not knowable: never "no news"
        "EQ:NOVOL": None,  # no earnings report known
    }
    assert out["volume_shock_no_news"].to_dict() == {
        "EQ:QUIET": True,
        "EQ:NEWS": False,
        "EQ:EARN": False,
        "EQ:EDGE": True,  # z 2.0: the edge counts
        "EQ:LOWVOL": False,
        "EQ:UNK": None,
        "EQ:NOVOL": None,
    }
