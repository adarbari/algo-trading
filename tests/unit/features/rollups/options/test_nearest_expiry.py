"""``nearest_expiry@v1``: the nearest listed expiry on or after the session (0-DTE included,
earlier expiries ignored), its calendar DTE and exchange sessions to it, a row per underlying
with a chain (null when every expiry is past), no rows without a chain partition, and the
same answer as Ideas' per-request ``chain_expiries`` rule it replaces."""

from datetime import date, timedelta

import pandas as pd

from algotrade.data.chains import chain_expiries
from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.options import nearest_expiry as ne
from tests.helpers.rollup_store import END, store, write_chains

# END is Friday 2026-10-02: the next Friday is 5 sessions out, 7 calendar days.
NEXT_FRIDAY = END + timedelta(days=7)
MONTHLY = date(2026, 10, 16)
SPOTS = {"EQ:WEEKLY": 100.0}  # the underlying quote is not an input


def quote(underlying: str, expiry: date, strike: float = 100.0) -> dict:
    return {
        "instrument_id": f"OPT:{underlying}:{expiry}:C{strike}",
        "underlying_id": underlying,
        "ts": pd.Timestamp(END, tz="UTC") + pd.Timedelta(hours=21),
        "expiry": expiry,
        "right": "C",
        "strike": strike,
        "bid": 1.0,
        "ask": 1.1,
        "volume": 10.0,
        "open_interest": 100.0,
        "iv": 30.0,
        "delta": 0.5,
    }


OPTIONS = [
    quote("EQ:WEEKLY", MONTHLY),
    quote("EQ:WEEKLY", NEXT_FRIDAY),
    quote("EQ:WEEKLY", NEXT_FRIDAY, 105.0),  # many contracts per expiry: one row
    quote("EQ:ZERO", END),  # expires on the session: 0-DTE counts
    quote("EQ:ZERO", MONTHLY),
    quote("EQ:STALE", END - timedelta(days=1), 90.0),  # before the session: ignored
    quote("EQ:STALE", MONTHLY),
    quote("EQ:PAST", END - timedelta(days=7)),  # nothing on or after the session
]


def _frame(options: list[dict]) -> pd.DataFrame:
    writer, reader = store()
    write_chains(writer, END, options, SPOTS)
    frame = compute_one(reader, ne.GROUP, END).frame
    assert frame is not None
    return frame.set_index("instrument_id")


def test_nearest_expiry_dte_and_sessions() -> None:
    out = _frame(OPTIONS).to_dict("index")
    assert sorted(out) == ["EQ:PAST", "EQ:STALE", "EQ:WEEKLY", "EQ:ZERO"]
    weekly = out["EQ:WEEKLY"]
    assert (weekly["expiry_date"], weekly["dte"], weekly["sessions_to_expiry"]) == (
        NEXT_FRIDAY,
        7,
        5,
    )
    assert (out["EQ:ZERO"]["expiry_date"], out["EQ:ZERO"]["dte"]) == (END, 0)
    assert out["EQ:ZERO"]["sessions_to_expiry"] == 0
    assert (out["EQ:STALE"]["expiry_date"], out["EQ:STALE"]["dte"]) == (MONTHLY, 14)
    assert out["EQ:STALE"]["sessions_to_expiry"] == 10


def test_a_chain_with_only_past_expiries_is_null_not_zero() -> None:
    past = _frame(OPTIONS).loc["EQ:PAST"]
    assert pd.isna(past["expiry_date"]) and pd.isna(past["dte"])
    assert pd.isna(past["sessions_to_expiry"])


def test_no_chain_partition_is_no_rows() -> None:
    _, reader = store()
    assert compute_one(reader, ne.GROUP, END).frame is None


def test_matches_the_per_request_rule_it_replaces() -> None:
    """``ranking.top_ideas``: nearest ``e >= session`` of ``chain_expiries``, DTE in days."""
    writer, reader = store()
    write_chains(writer, END, OPTIONS, SPOTS)
    expiries = chain_expiries(reader, END, ["EQ:WEEKLY", "EQ:ZERO", "EQ:STALE", "EQ:PAST"])
    assert len(expiries) == 4
    frame = compute_one(reader, ne.GROUP, END).frame
    assert frame is not None
    stored = frame.set_index("instrument_id")
    for iid, listed in expiries.items():
        nearest = next((e for e in listed if e >= END), None)
        dte = None if nearest is None else (nearest - END).days
        got = stored.loc[iid]
        assert (None if pd.isna(got["dte"]) else int(got["dte"])) == dte
        assert (None if pd.isna(got["expiry_date"]) else got["expiry_date"]) == nearest


def test_registered_with_its_columns() -> None:
    assert GROUPS["nearest_expiry@v1"] is ne.GROUP
    assert list(ne.COLUMNS) == ["expiry_date", "dte", "sessions_to_expiry"]
