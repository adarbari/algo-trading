"""``event_reaction@v1`` and ``market_event_reaction@v1`` on synthetic bars: point in time (a
reaction session after the session, a release known later, a moved date), short history."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.instruments import index_id
from algotrade.core.time.calendar import next_session, previous_session, sessions_ending
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.event_study import event_reaction as er
from algotrade.features.rollups.event_study import market_event_reaction as mer
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 2)
A, SHORT = "EQ:A", "EQ:S"
GRID = sessions_ending(SESSION, er.HISTORY + 1)
CPI_DAY = GRID[-30]
SPIKE = 0.08


def _returns() -> np.ndarray:
    # alternating +-1%: a normal day of about 1% and no big move by chance (a random walk would
    # flag 2 normal days on about one session in twenty)
    return 0.01 * (-1.0) ** np.arange(len(GRID))


def _bars(spike_days: tuple[date, ...] = (), short: bool = True) -> pd.DataFrame:
    r = _returns()
    for d in spike_days:
        r[GRID.index(d)] = -SPIKE
    close = 100 * np.exp(np.cumsum(r))
    rows = [{"instrument_id": A, "session_date": d, "close": c, "open": c, "high": c, "low": c,
             "volume": 1000.0} for d, c in zip(GRID, close, strict=True)]  # fmt: skip
    if short:  # a name with 100 sessions of bars
        rows += [{"instrument_id": SHORT, "session_date": d, "close": 50.0 + i % 3, "open": 50.0,
                  "high": 50.0, "low": 50.0, "volume": 1.0}
                 for i, d in enumerate(GRID[-100:])]  # fmt: skip
    return pd.DataFrame(rows)


def _release(
    key: str, day: date, known: date, status: str = "scheduled", time: str = "08:30"
) -> dict[str, object]:
    return {"instrument_id": f"MACRO:{key}", "ts": pd.Timestamp(day, tz="UTC"),
            "known_from": known, "release_key": key, "release_name": key, "release_date": day,
            "time_et": time, "status": status}  # fmt: skip


def _inputs(
    bars: pd.DataFrame,
    releases: list[dict[str, object]],
    reports: list[dict[str, object]] | None = None,
    calendar: bool = True,
) -> dict[str, pd.DataFrame | None]:
    # the calendar must cover the window (its first release at the grid's start) or the residual
    # and the shares are unknown (``calendar`` False: no calendar at all)
    covering = [_release("ISM_SERVICES", GRID[1], GRID[0])] if calendar else []
    rel = (
        stamped([*covering, *releases], SESSION, "m")
        if (releases or calendar) and calendar
        else None
    )
    rows = [{"instrument_id": A, "ts": pd.Timestamp(date(2020, 1, 1), tz="UTC"), "time": "unknown",
             "known_from": date(2020, 1, 1), "reported": True}, *(reports or [])]  # fmt: skip
    return {earnings.EVENTS: stamped(rows, SESSION, "e"), "bars/1d": bars,
            "instruments/symbol_ids": None,
            er.MACRO_RELEASE: rel}  # fmt: skip


def _a(frame: pd.DataFrame) -> pd.Series:
    row = frame.set_index("instrument_id").loc[A]
    assert isinstance(row, pd.Series)
    return row


def test_a_macro_release_is_read_in_normal_days_on_its_reaction_session() -> None:
    bars = _bars(spike_days=(CPI_DAY,))
    out = er.compute(_inputs(bars, [_release("CPI", CPI_DAY, GRID[0])]), SESSION, None)
    row = _a(out)
    assert row["macro_cpi_n"] == 1
    assert row["macro_cpi_multiple_median"] > 5  # an 8% fall over a 1% day
    assert row["macro_cpi_down_worst"] == pytest.approx(np.expm1(-SPIKE))
    assert pd.isna(row["macro_ppi_multiple_median"]) and pd.isna(row["macro_ppi_n"])  # not listed
    assert row["reaction_status"] == er.OK


def test_a_release_after_the_close_reacts_on_the_next_session() -> None:
    bars = _bars(spike_days=(next_session(CPI_DAY),))
    out = er.compute(
        _inputs(bars, [_release("CPI", CPI_DAY, GRID[0], time="16:30")]), SESSION, None
    )
    assert _a(out)["macro_cpi_multiple_median"] > 5


def test_a_reaction_after_the_session_a_later_known_release_and_a_moved_date_are_not_counted() -> (
    None
):
    rel = [
        _release("CPI", SESSION, GRID[0], time="16:30"),  # reacts on the next session: not here yet
        _release("PPI", CPI_DAY, SESSION),  # known only today: invisible a session earlier ...
        _release("GDP", CPI_DAY, GRID[0]),
        _release("GDP", CPI_DAY, GRID[1], status="moved"),  # ... and a moved date is dropped
    ]
    out = er.compute(_inputs(_bars(), rel), SESSION, None)
    row = _a(out)
    assert row["macro_cpi_n"] == 0  # listed, its reaction session not here yet
    assert pd.isna(row["macro_gdp_n"])  # its only date moved away: no release known
    assert row["macro_ppi_n"] == 1  # known by the session itself
    earlier = er.compute(_inputs(_bars(), rel), previous_session(SESSION), None)
    assert pd.isna(_a(earlier)["macro_ppi_n"])  # not known yet: UNKNOWN


def test_earnings_by_report_time_and_an_unknown_time_is_left_out_of_the_multiples() -> None:
    pre, post, unknown = GRID[-100], GRID[-200], GRID[-300]
    bars = _bars(spike_days=(pre, next_session(post), unknown))
    reports = [
        {
            "instrument_id": A,
            "ts": pd.Timestamp(d, tz="UTC"),
            "time": t,
            "known_from": d,
            "reported": True,
        }
        for d, t in ((pre, "pre_market"), (post, "after_hours"), (unknown, "unknown"))
    ]
    out = er.compute(_inputs(bars, [], reports), SESSION, None)
    row = _a(out)
    assert row["earnings_n"] == 2  # the unknown-time report is counted by neither multiple
    assert row["earnings_down_worst"] == pytest.approx(np.expm1(-SPIKE))
    assert row["unattributed_big_moves_252d"] == 0  # the unknown-time spike is older than a year
    assert row["share_of_top_moves_earnings"] > 0


def test_big_moves_without_an_event_are_the_unattributed_jump_risk() -> None:
    quiet, cpi = GRID[-20], CPI_DAY
    bars = _bars(spike_days=(quiet, cpi))
    out = er.compute(_inputs(bars, [_release("CPI", cpi, GRID[0])]), SESSION, None)
    row = _a(out)
    assert row["big_moves_252d"] == 2 and row["big_down_moves_252d"] == 2
    assert row["unattributed_big_moves_252d"] == 1
    assert row["unattributed_share_252d"] == pytest.approx(0.5)
    shares = [
        row[f"share_of_top_moves_{c}"] for c in ("earnings", "macro", "structure", "unscheduled")
    ]
    assert sum(shares) == pytest.approx(1.0)
    assert row["share_of_top_moves_macro"] == pytest.approx(1 / 20)
    assert row["share_of_top_moves_unscheduled"] > 0.8


def test_the_flags_of_the_session_itself() -> None:
    out = er.compute(_inputs(_bars(spike_days=(SESSION,)), []), SESSION, None)
    row = _a(out)
    assert row["big_move_5pct_today"] == 1 and row["big_move_2x_today"] == 1
    assert row["normal_day_20d"] > 0.005


def test_a_name_with_short_history_has_null_statistics_and_the_status_says_so() -> None:
    out = er.compute(_inputs(_bars(), []), SESSION, None).set_index("instrument_id")
    short = out.loc[SHORT]
    assert short["reaction_status"] == er.SHORT_HISTORY
    assert short.drop("reaction_status").isna().all()


def test_the_market_group_reads_the_index_level() -> None:
    r = _returns()
    r[GRID.index(CPI_DAY)] = -SPIKE
    level = 4000 * np.exp(np.cumsum(r))
    macro = pd.DataFrame({"instrument_id": index_id("SPX"), "obs_date": GRID, "value": level})
    inputs = {
        "macro/series": macro,
        er.MACRO_RELEASE: stamped([_release("CPI", CPI_DAY, GRID[0])], SESSION, "m"),
    }
    out = mer.compute(inputs, SESSION, None)
    row = out.iloc[0]
    assert len(out) == 1
    assert row["spx_macro_cpi_n"] == 1 and row["spx_macro_cpi_multiple_median"] > 5
    none = mer.compute({"macro/series": None, er.MACRO_RELEASE: None}, SESSION, None).iloc[0]
    assert pd.isna(none["spx_macro_cpi_multiple_median"])  # no index: UNKNOWN


def test_every_column_is_declared_in_order() -> None:
    out = er.compute(_inputs(_bars(), []), SESSION, None)
    assert list(out.columns) == ["instrument_id", *er.COLUMNS]


def test_a_missing_or_short_calendar_is_unknown_never_event_free() -> None:
    bars = _bars(spike_days=(GRID[-20],))
    none = _a(er.compute(_inputs(bars, [], calendar=False), SESSION, None))
    assert pd.isna(none["macro_cpi_n"]) and pd.isna(none["unattributed_big_moves_252d"])
    assert pd.isna(none["share_of_top_moves_unscheduled"])
    assert none["big_moves_252d"] == 1  # the big move itself does not need the calendar
    # a calendar that starts 30 sessions ago covers neither the year nor the window
    short = _inputs(bars, [_release("CPI", CPI_DAY, GRID[0])], calendar=False)
    short[er.MACRO_RELEASE] = stamped([_release("CPI", CPI_DAY, GRID[0])], SESSION, "m")
    row = _a(er.compute(short, SESSION, None))
    assert row["macro_cpi_n"] == 1 and pd.isna(row["macro_ppi_n"])  # a key never listed: UNKNOWN
    assert pd.isna(row["unattributed_share_252d"]) and pd.isna(row["share_of_top_moves_macro"])
