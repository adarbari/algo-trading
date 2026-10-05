"""``anchored_vwap@v1``: the docs' worked example by hand, the anchor rule (after the close:
next session; before the open or unknown: the report day), a report due after today's close
leaves the previous anchor, nulls (no report, one session, a gap, no volume, too old), splits
as of the session, and point in time (reports and bars after the session never count)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.corporate.earnings import valid_events
from algotrade.features.rollups.price import anchored_vwap as av
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import END, series, store, write_bars, write_earnings, write_split

DAYS = sessions_ending(END, 40)  # END is a Friday: DAYS[-3] Wednesday, DAYS[-2] Thursday


def flat_bars(writer: StoreWriter, iids: list[str], **kw: dict[str, list[float]]) -> None:
    """40 sessions closing at 10.00 (high 11, low 9, volume 100), the last two as the docs'
    example: Thursday typical 10.00 on 100 shares, Friday typical 12.00 on 300."""
    close = [10.0] * 38 + [10.0, 12.0]
    high = [11.0] * 38 + [11.0, 13.0]
    low = [9.0] * 38 + [9.0, 11.0]
    volume = [100.0] * 38 + [100.0, 300.0]
    write_bars(
        writer,
        dict.fromkeys(iids, close),
        opens=dict.fromkeys(iids, close),
        highs=dict.fromkeys(iids, high),
        lows=dict.fromkeys(iids, low),
        volume={i: kw.get("volume", {}).get(i, volume) for i in iids},
        skip=kw.get("skip"),  # type: ignore[arg-type]
    )


def rows(reader: StoreReader, day: date = END) -> dict[str, dict[str, object]]:
    frame = compute_one(reader, av.GROUP, day).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def test_worked_example_and_the_anchor_rule() -> None:
    writer, reader = store()
    ids = ["EQ:POST", "EQ:PRE", "EQ:UNKNOWN", "EQ:TODAY_POST", "EQ:TODAY_PRE", "EQ:NONE"]
    flat_bars(writer, ids)
    write_earnings(
        writer,
        DAYS[-25],  # a calendar stored well before; the backfill rows cover the past dates
        [
            ("EQ:POST", DAYS[-3], "after_hours"),  # Wednesday after the close: anchor Thursday
            ("EQ:PRE", DAYS[-2], "pre_market"),  # Thursday before the open: anchor Thursday
            ("EQ:UNKNOWN", DAYS[-2], "time-not-supplied"),  # unknown: the report day
            ("EQ:TODAY_POST", DAYS[-20], "pre_market"),  # previous report ...
            ("EQ:TODAY_POST", END, "after_hours"),  # ... today after the close: not yet
            ("EQ:TODAY_PRE", END, "pre_market"),  # today before the open: one session
        ],
    )
    out = rows(reader)
    for iid in ("EQ:POST", "EQ:PRE", "EQ:UNKNOWN"):
        assert out[iid]["avwap_earnings"] == pytest.approx(11.5), iid  # (1000 + 3600) / 400
        assert out[iid]["avwap_anchor_date"] == DAYS[-2]
    prior = out["EQ:TODAY_POST"]
    assert prior["avwap_anchor_date"] == DAYS[-20]
    # 18 sessions of typical 10 on 100, Thursday 10 on 100, Friday 12 on 300
    assert prior["avwap_earnings"] == pytest.approx((19 * 10 * 100 + 12 * 300) / (19 * 100 + 300))
    assert np.isnan(out["EQ:TODAY_PRE"]["avwap_earnings"])  # one session: not an average yet
    assert out["EQ:TODAY_PRE"]["avwap_anchor_date"] == END
    assert (
        np.isnan(out["EQ:NONE"]["avwap_earnings"]) and out["EQ:NONE"]["avwap_anchor_date"] is None
    )


def test_gaps_no_volume_and_stale_anchors_are_null() -> None:
    writer, reader = store()
    flat_bars(
        writer,
        ["EQ:GAP", "EQ:IDLE"],
        volume={"EQ:IDLE": [100.0] * 30 + [0.0] * 10},
        skip={"EQ:GAP": [36]},  # no bar 3 sessions before the end, after the anchor
    )
    write_earnings(
        writer,
        DAYS[-25],
        [
            ("EQ:GAP", DAYS[-10], "pre_market"),
            ("EQ:IDLE", DAYS[-5], "pre_market"),
        ],
    )
    out = rows(reader)
    assert (
        np.isnan(out["EQ:GAP"]["avwap_earnings"])
        and out["EQ:GAP"]["avwap_anchor_date"] == DAYS[-10]
    )
    assert np.isnan(out["EQ:IDLE"]["avwap_earnings"])  # no volume since the anchor
    edge = sessions_ending(END, av.MAX_SESSIONS + 1)[0]  # exactly 126 sessions back: kept
    writer2, reader2 = store()
    old = sessions_ending(END, av.MAX_SESSIONS + 2)[0]  # 127 sessions back: stale
    write_bars(writer2, {"EQ:EDGE": series(200, seed=3), "EQ:OLD": series(200, seed=4)})
    write_earnings(
        writer2, DAYS[-25], [("EQ:EDGE", edge, "pre_market"), ("EQ:OLD", old, "pre_market")]
    )
    out = rows(reader2)
    assert out["EQ:EDGE"]["avwap_anchor_date"] == edge and out["EQ:EDGE"]["avwap_earnings"] > 0
    assert np.isnan(out["EQ:OLD"]["avwap_earnings"]) and out["EQ:OLD"]["avwap_anchor_date"] is None


def test_split_adjusted_as_of_the_session() -> None:
    writer, reader = store()
    c = series(40, seed=9)
    raw = c.copy()
    raw[-3:] /= 2  # a 2-for-1 split three sessions before the end
    volume = np.full(40, 1000.0)
    raw_volume = volume.copy()
    raw_volume[-3:] *= 2
    write_bars(
        writer,
        {"EQ:P": c, "EQ:S": raw},
        opens={"EQ:P": c, "EQ:S": raw},
        volume={"EQ:P": volume, "EQ:S": raw_volume},
    )
    write_split(writer, "EQ:S", DAYS[-3], 2.0, stored=END)
    write_earnings(
        writer, DAYS[-25], [("EQ:P", DAYS[-8], "pre_market"), ("EQ:S", DAYS[-8], "pre_market")]
    )
    out = rows(reader)
    assert out["EQ:S"]["avwap_earnings"] == pytest.approx(
        out["EQ:P"]["avwap_earnings"] / 2, rel=1e-6
    )


def test_point_in_time_reports_and_bars_after_the_session_never_count() -> None:
    writer, reader = store()
    full = series(60, seed=12)
    write_bars(writer, {"EQ:A": full}, opens={"EQ:A": full})
    write_earnings(writer, DAYS[-30], [("EQ:A", DAYS[-25], "pre_market")])
    write_earnings(writer, DAYS[-12], [("EQ:A", DAYS[-10], "after_hours")])  # known from -12
    picks = [DAYS[-20], DAYS[-13], DAYS[-11], DAYS[-9], END]
    backfill = {r.session: r.frame for r in compute_sessions(reader, av.GROUP, picks)}
    anchors = {
        d: f.set_index("instrument_id").at["EQ:A", "avwap_anchor_date"]
        for d, f in backfill.items()
        if f is not None
    }
    assert anchors == {
        DAYS[-20]: DAYS[-25],
        DAYS[-13]: DAYS[-25],  # the next report is not known yet
        DAYS[-11]: DAYS[-25],
        DAYS[-9]: DAYS[-9],  # Wednesday after the close: anchors the next session
        END: DAYS[-9],
    }
    for day in picks:  # a store cut at the session gives the same row
        cut_writer, cut = store()
        upto = full[: len(full) - len(DAYS) + DAYS.index(day) + 1]
        write_bars(cut_writer, {"EQ:A": upto}, end=day, opens={"EQ:A": upto})
        write_earnings(cut_writer, DAYS[-30], [("EQ:A", DAYS[-25], "pre_market")])
        if DAYS[-12] <= day:
            write_earnings(cut_writer, DAYS[-12], [("EQ:A", DAYS[-10], "after_hours")])
        alone = compute_one(cut, av.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfill[day])


def test_registered() -> None:
    assert GROUPS["anchored_vwap@v1"].table == "rollups/instrument/anchored_vwap@v1"
    assert [i.table for i in av.GROUP.inputs] == ["events/earnings", "bars/1d"]


def test_reading_only_reports_that_can_anchor_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``valid_events(stored, since=days[0])`` gives the rows the full reading (every report
    date, as before) gave, on random calendars over 200 sessions: moved and cancelled dates,
    past dates backfilled into one snapshot, anchors older than the window."""
    rng = np.random.default_rng(3)
    days = sessions_ending(END, 200)
    writer, reader = store()
    ids = [f"EQ:N{i}" for i in range(6)]
    write_bars(
        writer,
        {i: series(200, seed=k) for k, i in enumerate(ids)},
        volume={i: list(rng.uniform(1e5, 1e6, 200)) for i in ids},
    )
    times = ["pre_market", "after_hours", "time-not-supplied"]
    for k in range(0, 200, 5):
        back = 100 if k == 150 else 0  # one snapshot also lists past dates (a backfill)
        listed = {
            (i, days[min(199, k - back + int(rng.integers(0, back + 40)))]): times[t]
            for i in ids
            for t in rng.integers(0, 3, size=int(rng.integers(0, 3)))
        }  # one row per name and date, as the calendar stores them
        if listed:
            write_earnings(writer, days[k], [(i, d, t) for (i, d), t in listed.items()])
    picks = days[-130::2]  # every other session of the last 130
    after = [r.frame for r in compute_sessions(reader, av.GROUP, picks)]
    monkeypatch.setattr(av, "valid_events", lambda stored, since=None: valid_events(stored))
    before = [r.frame for r in compute_sessions(reader, av.GROUP, picks)]
    assert sum(f is not None and f["avwap_earnings"].notna().any() for f in after) > 40
    for a, b in zip(after, before, strict=True):
        pd.testing.assert_frame_equal(a, b)
