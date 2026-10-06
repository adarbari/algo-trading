"""``price_history@v1``: no trade on the session, the range status (FULL, SINCE_LISTING,
NEW_LISTING, FEW_BARS) and the high / low over the history available; on stored bars by hand,
and as properties of ``history`` over random bar masks (gaps, listings, determinism, no
lookahead)."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.price import price_history as ph
from algotrade.features.rollups.price import price_stats as ps
from tests.helpers.rollup_store import END, series, store, write_bars

P = ph.PriceHistoryParams()
SMALL = ph.PriceHistoryParams(
    year_sessions=20, full_bars=18, listing_quiet=5, min_listing_sessions=4
)
F32 = 2e-7


def row(frame: pd.DataFrame | None, iid: str) -> dict[str, object]:
    assert frame is not None
    return frame.set_index("instrument_id").loc[iid].to_dict()


def test_on_stored_bars() -> None:
    writer, reader = store()
    full, young = series(320), series(30, seed=2)
    days = write_bars(
        writer,
        {"EQ:FULL": full, "EQ:NEW": young, "EQ:BABY": series(5, seed=3),
         "EQ:QUIET": full, "EQ:THIN": full, "EQ:GONE": full},
        skip={"EQ:QUIET": [319], "EQ:THIN": [i for i in range(320) if i % 5],
              "EQ:GONE": list(range(10, 320))},
    )  # fmt: skip
    frame = compute_one(reader, ph.GROUP, END).frame
    a = row(frame, "EQ:FULL")
    assert (a["bar_status"], a["range_status"], a["range_sessions"]) == ("TRADED", "FULL", 252)
    assert a["last_bar_session"] == END
    highs = np.maximum(np.r_[full[0], full[:-1]], full) * 1.01
    assert a["high_avail"] == pytest.approx(highs[-252:].max(), rel=F32)
    new = row(frame, "EQ:NEW")
    assert (new["range_status"], new["range_sessions"]) == ("SINCE_LISTING", 30)
    assert new["high_avail"] == pytest.approx(
        (np.maximum(np.r_[young[0], young[:-1]], young) * 1.01).max(), rel=F32
    )
    baby = row(frame, "EQ:BABY")
    assert baby["range_status"] == "NEW_LISTING" and pd.isna(baby["high_avail"])
    quiet = row(frame, "EQ:QUIET")  # no bar on the session: a row says so
    assert (quiet["bar_status"], quiet["last_bar_session"]) == ("NO_TRADE", days[-2])
    thin = row(frame, "EQ:THIN")  # every 5th session, since before the window
    assert thin["range_status"] == "FEW_BARS" and pd.isna(thin["low_avail"])
    assert "EQ:GONE" not in set(frame["instrument_id"])  # no bar in the window: no row
    assert str(frame["range_sessions"].dtype) == "int64[pyarrow]"


def test_full_matches_price_stats_52_week_rule() -> None:
    stats = ps.PriceStatsParams()
    assert (P.year_sessions, P.full_bars) == (stats.year_sessions, stats.min_year_sessions)


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"year_sessions": 1}, "year_sessions"),
        ({"full_bars": 0}, "full_bars"),
        ({"listing_quiet": 0}, "listing_quiet"),
        ({"min_listing_sessions": 300}, "min_listing_sessions"),
    ],
)
def test_params_are_checked(changes: dict[str, int], problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        replace(P, **changes)


def _panel(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    prices = np.arange(1.0, mask.size + 1).reshape(mask.shape)
    close = np.where(mask, prices, np.nan)
    return close * 1.1, close * 0.9, close


masks = st.integers(1, 6).flatmap(
    lambda n: st.lists(
        st.lists(st.booleans(), min_size=n, max_size=n), min_size=25, max_size=25
    ).map(np.array)
)


@settings(max_examples=200, deadline=None)
@given(mask=masks)
def test_history_properties(mask: np.ndarray) -> None:
    high, low, close = _panel(mask)
    out = ph.history(high, low, close, SMALL)
    window = mask[-SMALL.year_sessions :]
    assert (out["present"] == window.any(axis=0)).all()  # a row exactly with a bar in it
    for j in np.flatnonzero(out["present"]):
        status, bars = out["range_status"][j], window[:, j].sum()
        assert (out["bar_status"][j] == "TRADED") == mask[-1, j]
        assert mask[out["last_bar"][j], j] and not mask[out["last_bar"][j] + 1 :, j].any()
        first = np.argmax(window[:, j])
        assert out["range_sessions"][j] == SMALL.year_sessions - first
        assert (status == "FULL") == (bars >= SMALL.full_bars)
        ranged = status in ("FULL", "SINCE_LISTING")
        assert np.isnan(out["high_avail"][j]) != ranged  # a value exactly with a range
        if ranged:  # the window's own bars, never zero or a filled gap
            assert out["high_avail"][j] == np.nanmax(high[-SMALL.year_sessions :, j])
            assert out["low_avail"][j] == np.nanmin(low[-SMALL.year_sessions :, j])
        if status in ("SINCE_LISTING", "NEW_LISTING"):  # nothing in the quiet sessions before
            start = len(mask) - SMALL.year_sessions + first
            assert not mask[max(0, start - SMALL.listing_quiet) : start, j].any()
    again = ph.history(high.copy(), low.copy(), close.copy(), SMALL)
    assert all(_same(out[k], again[k]) for k in out)  # deterministic


def _same(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.array_equal(a, b, equal_nan=a.dtype.kind == "f"))


def test_bars_after_the_session_change_nothing() -> None:
    """Point-in-time: the row for a session is the same whatever is stored after it."""
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(300), "EQ:B": series(40, seed=4)})
    session = days[-6]
    before = compute_one(reader, ph.GROUP, session).frame
    write_bars(writer, {"EQ:A": series(5, seed=9) * 50, "EQ:C": series(5, seed=8)})  # later bars
    after = compute_one(reader, ph.GROUP, session).frame
    pd.testing.assert_frame_equal(before, after)
    assert row(before, "EQ:B")["range_sessions"] == 35
