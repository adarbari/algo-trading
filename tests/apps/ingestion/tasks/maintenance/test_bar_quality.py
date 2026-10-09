from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.data.prices import bars
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.bar_quality import (
    BAD_OHLC,
    BELOW_FLOOR,
    CLEARED,
    UNEXPLAINED_JUMP,
    bad_bars,
    changes,
    run_bar_quality,
)
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped

S = SourcesSettings()
START = date(2020, 1, 6)


def series(iid: str, closes: list[float], sources: list[str], start: date = START) -> pd.DataFrame:
    days = [pd.Timestamp(start + timedelta(days=i), tz="UTC") for i in range(len(closes))]
    return pd.DataFrame(
        {
            "instrument_id": iid,
            "ts": days,
            "high": closes,
            "low": closes,
            "close": closes,
            "source": sources,
        }
    )


NO_SPLITS = pd.DataFrame(columns=["instrument_id", "ts"])


def flagged(frame: pd.DataFrame, splits: pd.DataFrame = NO_SPLITS) -> dict[str, dict[int, str]]:
    """instrument -> {bar index within the series: reason}."""
    out = bad_bars(frame, splits, S)
    first = frame.groupby("instrument_id")["ts"].min()
    return {
        str(i): {
            int((pd.Timestamp(t) - first[i]).days): r
            for t, r in zip(g["ts"], g["reason"], strict=True)
        }
        for i, g in out.groupby("instrument_id")
    }


def test_bad_bars_shapes() -> None:
    """The four observed shapes, a real reverse split and a single spike."""
    tiingo, massive = ["tiingo"] * 5, ["massive"] * 5
    frame = pd.concat(
        [
            # EQ:TIINGO:US000000045374: 0.0015 -> 42.7 (13,777x): the floor and the jump
            series("EQ:TIINGO:US000000045374", [0.0015] * 5 + [42.7] * 5, tiingo + massive),
            # EQ:BBG009NMGXS6: 0.001332 -> 15.78 (about 11,850x)
            series("EQ:BBG009NMGXS6", [0.001332] * 5 + [15.78] * 5, tiingo + massive),
            # EQ:BBG02029KQD1: 2,000x above the floor: only the jump finds it
            series("EQ:BBG02029KQD1", [0.0125] * 5 + [25.0] * 5, tiingo + massive),
            # EQ:BBG021DN5TF5: 20,000x
            series("EQ:BBG021DN5TF5", [0.05] * 5 + [1000.0] * 5, tiingo + massive),
            # a real 1:20 reverse split with its event: not flagged
            series("EQ:REVERSE", [1.0] * 5 + [20.0] * 5, tiingo + massive),
            # one-day spike inside a long series: only the spike
            series("EQ:SPIKE", [10.0] * 4 + [250.0] + [10.0] * 5, massive + massive),
            # high below low, close outside the range
            series("EQ:OHLC", [10.0] * 6, massive + massive[:1]).assign(
                high=[10, 10, 9, 10, 10, 10], low=[10, 10, 11, 10, 10, 10]
            ),
        ],
        ignore_index=True,
    )
    split = pd.DataFrame(
        {
            "instrument_id": ["EQ:REVERSE"],
            "ts": [pd.Timestamp(START + timedelta(days=5), tz="UTC")],
            "ratio": [0.05],
        }
    )
    got = flagged(frame, split)
    early = dict.fromkeys(range(5), BELOW_FLOOR)
    assert got["EQ:TIINGO:US000000045374"] == early
    assert got["EQ:BBG009NMGXS6"] == early
    assert got["EQ:BBG02029KQD1"] == dict.fromkeys(range(5), UNEXPLAINED_JUMP)
    assert got["EQ:BBG021DN5TF5"] == dict.fromkeys(range(5), UNEXPLAINED_JUMP)
    assert "EQ:REVERSE" not in got
    assert got["EQ:SPIKE"] == {4: UNEXPLAINED_JUMP}
    assert got["EQ:OHLC"] == {2: BAD_OHLC}


def test_no_massive_bars_trusts_the_latest_segment_and_zero_volume_is_not_a_flag() -> None:
    frame = series("EQ:T", [5.0] * 3 + [500.0] * 3, ["tiingo"] * 6)
    assert flagged(frame) == {
        "EQ:T": {0: UNEXPLAINED_JUMP, 1: UNEXPLAINED_JUMP, 2: UNEXPLAINED_JUMP}
    }
    assert bad_bars(frame.iloc[3:], NO_SPLITS, S).empty


def test_changes_writes_only_what_differs_and_clears_the_fixed() -> None:
    found = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:A"],
            "ts": pd.to_datetime(["2020-01-06", "2020-01-07"], utc=True),
            "reason": [BELOW_FLOOR, BELOW_FLOOR],
            "detail": ["d", "d"],
        }
    )
    stored = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B"],
            "ts": pd.to_datetime(["2020-01-06", "2020-01-06"], utc=True),
            "reason": [BELOW_FLOOR, BAD_OHLC],
            "detail": ["d", "d"],
            "status": ["FLAGGED", "FLAGGED"],
        }
    )
    out = changes(found, stored)
    assert sorted(zip(out["instrument_id"], out["status"], strict=True)) == [
        ("EQ:A", "FLAGGED"),
        ("EQ:B", CLEARED),
    ]


def test_task_writes_flags_once_and_reads_them_back(tmp_path: Path) -> None:

    backend = LocalBackend(tmp_path)
    writer = StoreWriter(backend)
    days = [date(2026, 9, 28) + timedelta(days=i) for i in range(6)]  # Mon..Sat: weekdays only
    days = [d for d in days if d.weekday() < 5]
    closes = [0.05, 0.05, 50.0, 50.0]
    for day, close in zip(days, closes, strict=False):
        row = {"instrument_id": "EQ:A", "ts": pd.Timestamp(day, tz="UTC"), "open": close,
               "high": close, "low": close, "close": close, "volume": 1.0}  # fmt: skip
        writer.write_table(
            "bars/1d", day, f"b{day}", stamped([row], day, f"b{day}", source="tiingo")
        )
    reader = StoreReader(backend)
    strict = run_bar_quality(task_ctx(writer, reader), days[-1], days[0], days[-1])
    assert strict.status is RunStatus.FAILED and "flagged" in strict.stats["failed_because"][0]
    assert len(bars(StoreReader(backend), "1d", days[0], days[-1])) == 4  # nothing published
    ctx = task_ctx(writer, reader, settings=replace(SourcesSettings(), max_bad_bar_share=1.0))
    record = run_bar_quality(ctx, days[-1], days[0], days[-1])
    assert record.stats["flagged"] == 2 and record.stats["written"] == 2
    assert len(bars(StoreReader(backend), "1d", days[0], days[-1])) == 2
    again = run_bar_quality(ctx, days[-1], days[0], days[-1])
    assert again.stats["written"] == 0  # a rerun writes only changes


def test_partial_rerun_keeps_jump_flags() -> None:
    """A jump flag outside a short range is not cleared (the range shows one segment); the same
    instrument read from its first bar clears it; a floor flag clears on any run."""
    stored = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:A"],
            "ts": pd.to_datetime(["2020-01-06", "2020-01-07"], utc=True),
            "reason": [UNEXPLAINED_JUMP, BELOW_FLOOR],
            "detail": ["d", "d"],
            "status": ["FLAGGED", "FLAGGED"],
        }
    )
    none = pd.DataFrame(columns=["instrument_id", "ts", "reason", "detail"])
    kept = changes(none, stored, frozenset({"EQ:A"}))
    assert list(zip(kept["reason"], kept["status"], strict=True)) == [(BELOW_FLOOR, CLEARED)]
    full = changes(none, stored, frozenset())
    assert sorted(full["reason"]) == [BELOW_FLOOR, UNEXPLAINED_JUMP]


def test_split_like_jumps_are_tagged_and_kept() -> None:
    frame = pd.concat(
        [
            series("EQ:REV", [1.0] * 4 + [20.1] * 4, ["tiingo"] * 8),  # near 20x: split-like
            series("EQ:JUNK", [1.0] * 4 + [500.0] * 4, ["tiingo"] * 8),
        ],
        ignore_index=True,
    )
    out = bad_bars(frame, NO_SPLITS, S)
    detail = out.groupby("instrument_id")["detail"].first()
    assert "split_like=20" in detail["EQ:REV"]
    assert "split_like" not in detail["EQ:JUNK"]
    assert set(out["instrument_id"]) == {"EQ:REV", "EQ:JUNK"}  # still flagged
