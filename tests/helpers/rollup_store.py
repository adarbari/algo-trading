"""Builders for rollup tests: a memory store with daily bars, splits and earnings snapshots."""

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

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


def write_dividends(
    writer: StoreWriter, rows: Sequence[tuple[str, date, float, str]], stored: date = END
) -> None:
    """Dividends stored in one run on ``stored``: (instrument, ex-date, amount, type)."""
    frame = [
        {
            "instrument_id": iid,
            "symbol": iid[3:],
            "ts": pd.Timestamp(ex_date, tz="UTC"),
            "cash_amount": amount,
            "distribution_type": kind,
        }
        for iid, ex_date, amount, kind in rows
    ]
    run = f"div-{stored}"
    writer.write_table("events/dividend", stored, run, stamped(frame, stored, run))


def write_curve(writer: StoreWriter, day: date, rate: float) -> None:
    """A flat Treasury curve (continuous ``rate`` at every tenor) stored on ``day``."""
    rows = [
        {
            "instrument_id": f"RATE:UST-{tenor}",
            "ts": pd.Timestamp(day, tz="UTC"),
            "tenor": tenor,
            "tenor_days": days,
            "rate_par": rate,
            "rate_cont": rate,
        }
        for tenor, days in (("1M", 30), ("3M", 91), ("1Y", 365))
    ]
    writer.write_table("rates/treasury", day, f"rates-{day}", stamped(rows, day, f"rates-{day}"))


def chain_rows(
    underlying: str,
    session: date,
    spot: float,
    vols: Mapping[date, float],
    r: float,
    q: float = 0.0,
    strikes: Sequence[float] = tuple(range(80, 125, 5)),
    spread: float = 0.02,
    oi: float = 500.0,
) -> list[dict[str, object]]:
    """Option quotes priced by Black-Scholes with a flat vol per expiry: mid = model price,
    bid / ask = mid -+ ``spread`` / 2 (floored at 0.01)."""
    from algotrade.quant import black_scholes  # noqa: PLC0415

    rows: list[dict[str, object]] = []
    for expiry, sigma in vols.items():
        t = (expiry - session).days / 365
        for k in strikes:
            for right in ("C", "P"):
                mid = float(black_scholes.price(spot, k, t, r, q, sigma, right == "C"))
                rows.append(
                    {
                        "instrument_id": f"OPT:{underlying}:{expiry}:{right}{k}",
                        "underlying_id": underlying,
                        "ts": pd.Timestamp(session, tz="UTC") + pd.Timedelta(hours=21),
                        "expiry": expiry,
                        "right": right,
                        "strike": float(k),
                        "bid": max(mid - spread / 2, 0.0),
                        "ask": mid + spread / 2,
                        "volume": 10.0,
                        "open_interest": oi,
                        "iv": sigma * 100,
                        "delta": 0.5,
                    }
                )
    return rows


def write_chains(
    writer: StoreWriter,
    session: date,
    options: Sequence[Mapping[str, object]],
    spots: Mapping[str, float],
    cboe_iv30: float = 25.0,
) -> None:
    run = f"chains-{session}"
    if options:
        writer.write_table(
            "chains/option_quotes", session, run, stamped(list(options), session, run)
        )
    quotes = [
        {
            "instrument_id": iid,
            "symbol": iid[3:],
            "ts": pd.Timestamp(session, tz="UTC") + pd.Timedelta(hours=21),
            "price": price,
            "close": price,
            "volume": 1e6,
            "iv30": cboe_iv30,
        }
        for iid, price in spots.items()
    ]
    writer.write_table("chains/underlying_quotes", session, run, stamped(quotes, session, run))
