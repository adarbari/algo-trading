"""``filing_activity@v1``: 8-K counts over the 5 sessions ending at S-1 (the span ends there
because S's index is unread on the night of S), the walk that says how far they are complete,
earnings reaction windows in the last 5 sessions, known_from <= S, and the nulls that stop an
unknown being read as "no news"."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.events import filing_activity
from algotrade.features.rollups.events.filing_activity import FILINGS, GROUP
from algotrade.features.rollups.price import price_stats
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import start_run
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END, series, store, write_bars, write_earnings, write_rows
from tests.helpers.stored_frames import stamped

SESSION = END
GRID = sessions_ending(SESSION, 12)
STATS = pd.DataFrame(
    {"instrument_id": ["EQ:A", "EQ:B", "EQ:C"], "session_date": SESSION, "history_days": 252}
)


PREV = sessions_ending(SESSION, 2)[0]  # S-1: the filing span ends here
FIRST = sessions_ending(SESSION, 6)[0]  # S-5: its first session
NIGHT = "filings/walk"


def _filings(rows: list[tuple[str, date]], hour: float = 12.0) -> pd.DataFrame:
    """(instrument, known_from) rows accepted at ``hour`` New York time on their day (UTC hour
    +4 in October)."""
    frame = [
        {"instrument_id": i, "ts": pd.Timestamp(k, tz="UTC") + pd.Timedelta(hours=hour + 4),
         "known_from": k, "accession": f"{i}-{k}-{n}", "form": "8-K"}
        for n, (i, k) in enumerate(rows)
    ]  # fmt: skip
    return stamped(frame, SESSION, "f")


def _walk(walked_to: date | None = PREV, run_session: date = SESSION) -> pd.DataFrame:
    rows = [] if walked_to is None else [{"session_date": run_session, "walked_to": walked_to}]
    return pd.DataFrame(rows, columns=["session_date", "walked_to"])


def _compute(
    filings: pd.DataFrame | None,
    earn: pd.DataFrame | None = None,
    walk: pd.DataFrame | None = None,
) -> pd.DataFrame:
    walk = _walk() if walk is None else walk
    inputs = {
        filing_activity.PRICE_STATS: STATS,
        FILINGS: filings,
        NIGHT: walk,
        earnings.EVENTS: earn,
    }
    return filing_activity.compute(inputs, SESSION, None).set_index("instrument_id")


def _earn(rows: list[tuple[str, date]]) -> pd.DataFrame:
    frame = [
        {"instrument_id": i, "ts": pd.Timestamp(d, tz="UTC"), "time": "unknown",
         "known_from": d, "reported": True}
        for i, d in rows
    ]  # fmt: skip
    return stamped(frame, SESSION, "e")


def test_counts_filings_over_the_five_sessions_ending_at_the_previous_one() -> None:
    old = GRID[0]  # before the span: seen, so a zero is knowable
    out = _compute(_filings([("EQ:A", FIRST), ("EQ:A", PREV), ("EQ:B", old), ("EQ:C", PREV)]))
    assert out["filing_count_5d"].tolist() == [2, 0, 1]  # the span's first and last day count


def test_a_filing_of_the_session_itself_never_counts() -> None:
    """S's 8-Ks are not stored on the night of S (the index is read once published): the span
    ends at S-1, so the value is the same before and after they arrive."""
    base = _filings([("EQ:A", PREV), ("EQ:B", GRID[0]), ("EQ:C", PREV)])
    late = pd.concat([base, _filings([("EQ:B", SESSION), ("EQ:A", SESSION)])], ignore_index=True)
    assert _compute(base)["filing_count_5d"].tolist() == [1, 0, 1]
    assert _compute(late)["filing_count_5d"].tolist() == [1, 0, 1]  # recomputed after S's index


def test_a_recompute_after_the_next_nights_data_gives_the_same_value() -> None:
    base = _filings([("EQ:A", PREV), ("EQ:B", GRID[0]), ("EQ:C", PREV)])
    after = pd.concat(
        [base, _filings([("EQ:A", SESSION)]), _filings([("EQ:B", PREV)], hour=19.0)],
        ignore_index=True,
    )  # S's filings, and a late S-1 acceptance (after the 17:30 index cut-off, listed in S's index)
    walks = pd.concat([_walk(PREV), _walk(SESSION, SESSION + timedelta(days=1))])
    assert _compute(after, walk=walks)["filing_count_5d"].tolist() == [1, 0, 1]
    assert _compute(base)["filing_count_5d"].tolist() == [1, 0, 1]


def test_a_filing_after_the_previous_index_cutoff_is_not_in_the_span() -> None:
    out = _compute(
        _filings([("EQ:A", PREV), ("EQ:B", GRID[0])]).pipe(
            lambda f: pd.concat([f, _filings([("EQ:B", PREV)], hour=18.0)], ignore_index=True)
        )
    )
    assert out["filing_count_5d"].tolist()[:2] == [1, 0]  # 18:00 on S-1 is in S's index: unread


def test_the_span_is_unknown_unless_the_walk_reached_the_previous_session() -> None:
    rows = _filings([("EQ:A", PREV), ("EQ:B", GRID[0]), ("EQ:C", PREV)])
    behind = sessions_ending(SESSION, 3)[0]  # S-2: S-1 is only partly covered
    for walk in (_walk(behind), _walk(None), pd.DataFrame(columns=["session_date", "walked_to"])):
        assert _compute(rows, walk=walk)["filing_count_5d"].isna().all()
    assert not _compute(rows, walk=_walk(SESSION))["filing_count_5d"].isna().any()  # further: ok


def test_a_walk_recorded_after_the_session_does_not_cover_it() -> None:
    rows = _filings([("EQ:A", PREV), ("EQ:B", GRID[0])])
    later = _walk(SESSION, SESSION + timedelta(days=1))  # a later night's run: not known on S
    assert _compute(rows, walk=later)["filing_count_5d"].isna().all()


def test_an_instrument_with_no_filing_stored_is_unknown_not_zero() -> None:
    out = _compute(_filings([("EQ:A", PREV), ("EQ:B", GRID[0])]))
    assert out["filing_count_5d"].isna().tolist() == [False, False, True]


def test_a_backfill_that_starts_after_the_span_knows_nothing() -> None:
    out = _compute(_filings([("EQ:A", PREV), ("EQ:B", PREV)]))
    assert out["filing_count_5d"].isna().all()  # nothing stored before the span: no zeros


def test_no_filing_table_is_all_unknown() -> None:
    assert _compute(None)["filing_count_5d"].isna().all()
    assert _compute(_filings([]).iloc[0:0])["filing_count_5d"].isna().all()


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
    write_rows(  # EQ:A filed on S-1, EQ:B long before
        writer, "events/filing", SESSION,
        [
            {"instrument_id": "EQ:A", "ts": pd.Timestamp(PREV, tz="UTC") + pd.Timedelta(hours=16),
             "known_from": PREV, "accession": "a1", "form": "8-K", "cik": "1",
             "filing_date": PREV, "items": "7.01"},
            {"instrument_id": "EQ:B", "ts": pd.Timestamp(GRID[0], tz="UTC"), "known_from": GRID[0],
             "accession": "b1", "form": "8-K", "cik": "2", "filing_date": GRID[0], "items": "7.01"},
        ],
    )  # fmt: skip
    write_earnings(writer, GRID[0], [("EQ:A", GRID[0] - timedelta(days=60), "pre_market")])
    record = start_run("filings", SESSION, datetime(2026, 10, 2, 22, tzinfo=UTC))
    record.finish(datetime(2026, 10, 2, 23, tzinfo=UTC), stats={"walked_to": PREV.isoformat()})
    writer.save_run(record)
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
