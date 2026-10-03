"""Builders for rollup tests: a memory store with daily bars, splits and earnings snapshots."""

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.storage_helpers import stamped

END = date(2026, 10, 2)


def store() -> tuple[StoreWriter, StoreReader]:
    backend = MemoryBackend()
    return StoreWriter(backend), StoreReader(backend)


def series(n: int, seed: int = 1, start: float = 100.0) -> np.ndarray:
    """A deterministic positive close series (a seeded random walk)."""
    steps = np.random.default_rng(seed).normal(0.0005, 0.015, n)
    return start * np.exp(np.cumsum(steps))


def write_bars(
    writer: StoreWriter,
    closes: Mapping[str, Sequence[float]],
    end: date = END,
    volume: Mapping[str, Sequence[float]] | None = None,
    skip: Mapping[str, Sequence[int]] | None = None,
    opens: Mapping[str, Sequence[float]] | None = None,
) -> list[date]:
    """One bar per session for each instrument, the last on ``end``; open = previous close
    (or ``opens``), high / low 1% around. ``skip``: session indexes with no bar.
    -> the sessions."""
    n = max(len(c) for c in closes.values())
    days = sessions_ending(end, n)
    for i, day in enumerate(days):
        rows = []
        for iid, c in closes.items():
            offset = n - len(c)
            if i < offset or i in (skip or {}).get(iid, ()):
                continue
            close = float(c[i - offset])
            opened = float(c[i - offset - 1]) if i > offset else close
            if opens and iid in opens:
                opened = float(opens[iid][i - offset])
            vol = float((volume or {}).get(iid, [1000.0] * len(c))[i - offset])
            rows.append(
                {
                    "instrument_id": iid,
                    "ts": pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=20),
                    "open": opened,
                    "high": max(opened, close) * 1.01,
                    "low": min(opened, close) * 0.99,
                    "close": close,
                    "volume": vol,
                }
            )
        if rows:
            writer.write_table("bars/1d", day, f"bars-{day}", stamped(rows, day, f"bars-{day}"))
    return days


def write_split(writer: StoreWriter, iid: str, ex_date: date, ratio: float, stored: date) -> None:
    row = {"instrument_id": iid, "ts": pd.Timestamp(ex_date, tz="UTC"), "ratio": ratio}
    writer.write_table("events/split", stored, f"split-{stored}", stamped([row], stored, "s"))


def write_earnings(
    writer: StoreWriter, snapshot: date, rows: Sequence[tuple[str, date, str]]
) -> None:
    """One calendar snapshot stored on ``snapshot``: (instrument, report date, time)."""
    frame = [
        {"instrument_id": iid, "symbol": iid[3:], "ts": pd.Timestamp(day, tz="UTC"), "time": t}
        for iid, day, t in rows
    ]
    run = f"earnings-{snapshot}"
    writer.write_table("events/earnings", snapshot, run, stamped(frame, snapshot, run))
