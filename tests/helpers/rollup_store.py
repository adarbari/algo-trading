"""Builders for rollup tests: a memory store with daily bars, splits and earnings snapshots,
and a toy market-entity group (``MARKET_COUNTS``, ADR 0047) that task tests run in place of
the site's market groups (``only_market_counts``)."""

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs
from algotrade.features.framework.feature import Feature
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, universe_rows, write_reference

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
    highs: Mapping[str, Sequence[float]] | None = None,
    lows: Mapping[str, Sequence[float]] | None = None,
) -> list[date]:
    """One bar per session for each instrument, the last on ``end``; open = previous close
    (or ``opens``), high / low 1% around (or ``highs`` / ``lows``). ``skip``: session indexes
    with no bar. -> the sessions."""
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
                    "high": _given(highs, iid, i - offset, max(opened, close) * 1.01),
                    "low": _given(lows, iid, i - offset, min(opened, close) * 0.99),
                    "close": close,
                    "volume": vol,
                }
            )
        if rows:
            writer.write_table("bars/1d", day, f"bars-{day}", stamped(rows, day, f"bars-{day}"))
    return days


def _given(values: Mapping[str, Sequence[float]] | None, iid: str, i: int, default: float) -> float:
    return float(values[iid][i]) if values and iid in values else default


def write_split(writer: StoreWriter, iid: str, ex_date: date, ratio: float, stored: date) -> None:
    row = {"instrument_id": iid, "ts": pd.Timestamp(ex_date, tz="UTC"), "ratio": ratio}
    writer.write_table("events/split", stored, f"split-{stored}", stamped([row], stored, "s"))


def write_earnings(
    writer: StoreWriter, snapshot: date, rows: Sequence[tuple[str, date, str]]
) -> None:
    """One calendar snapshot stored on ``snapshot``: (instrument, report date, time), every
    row a forecast known from ``snapshot``."""
    frame = [
        {
            "instrument_id": iid,
            "symbol": iid[3:],
            "ts": pd.Timestamp(day, tz="UTC"),
            "time": t,
            "known_from": snapshot,
        }
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


def quote_row(
    underlying: str,
    session: date,
    expiry: date,
    right: str,
    strike: float,
    bid: float,
    ask: float,
    volume: float | None = 0.0,
    oi: float | None = 0.0,
) -> dict[str, object]:
    """One hand-priced option quote in ``chain_rows``' shape (volume / OI ``None``: null)."""
    return {
        "instrument_id": f"OPT:{underlying}:{expiry}:{right}{strike}",
        "underlying_id": underlying,
        "ts": pd.Timestamp(session, tz="UTC") + pd.Timedelta(hours=21),
        "expiry": expiry,
        "right": right,
        "strike": float(strike),
        "bid": bid,
        "ask": ask,
        "volume": volume,
        "open_interest": oi,
        "iv": 30.0,
        "delta": 0.5,
    }


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


def write_rows(
    writer: StoreWriter, table: str, day: date, rows: Sequence[Mapping[str, object]]
) -> None:
    """Stored rows of a group table (e.g. a rollup's output) for one session."""
    run = f"{table.rsplit('/', 1)[-1]}-{day}"
    writer.write_table(table, day, run, stamped([dict(r) for r in rows], day, run))


def features(columns: Mapping[str, str]) -> tuple[Feature, ...]:
    """Placeholder feature declarations for test groups: ``{"col": "float"}``."""
    return tuple(Feature(c, t, "text", f"test {c}", "test") for c, t in columns.items())


def _market_counts(frames: Inputs, session: date, params: None) -> pd.DataFrame:
    """The market's one row: how many names the session's universe holds and how many of them
    have a bar on the session (null before the first universe snapshot), and SPY's close
    (found through the symbol -> id map, never a built id)."""
    universe, bars, ids = frames["universe"], frames["bars/1d"], frames["instruments/symbol_ids"]
    assert bars is not None
    today = bars[bars["session_date"] == session]
    names = covered = None
    if universe is not None:
        names = len(universe)
        covered = int(today["instrument_id"].isin(universe["instrument_id"]).sum())
    spy = None
    if ids is not None:
        closes = today.loc[
            today["instrument_id"].isin(ids.loc[ids["symbol"] == "SPY", "instrument_id"]), "close"
        ]
        spy = float(closes.iloc[0]) if len(closes) else None
    row = {"instrument_id": market_id("US"), "names": names, "with_bars": covered, "spy_close": spy}
    return pd.DataFrame([row])


MARKET_COUNTS = FeatureGroup(
    "market_counts",
    1,
    "test market group",
    (
        Input("bars/1d"),
        Input("universe", required=False),
        Input("instruments/symbol_ids", required=False),
    ),
    features({"names": "int", "with_bars": "int", "spy_close": "float"}),
    _market_counts,
    entity="market",
)


def without_market_groups(monkeypatch: pytest.MonkeyPatch, *sites: FeatureSet) -> None:
    """Remove the site's market groups from each feature set for the test."""
    for site in sites:
        for key in [k for k, g in site.groups.items() if g.entity == "market"]:
            monkeypatch.delitem(site.groups, key)


def only_market_counts(monkeypatch: pytest.MonkeyPatch, *sites: FeatureSet) -> None:
    """``MARKET_COUNTS`` as the one market group of each feature set for the test."""
    without_market_groups(monkeypatch, *sites)
    for site in sites:
        monkeypatch.setitem(site.groups, MARKET_COUNTS.key, MARKET_COUNTS)


SPY = "EQ:BBG000BDTBL9"


def market_store() -> tuple[StoreWriter, StoreReader, list[date]]:
    """A store for ``MARKET_COUNTS``: six sessions of bars for A, SPY and B (3 sessions), a
    reference snapshot and universe snapshots that change on the 3rd and 5th session."""
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(6), SPY: series(6, seed=3), "EQ:B": series(3)})
    write_reference(writer, days[0], {"A": "EQ:A", "SPY": SPY, "B": "EQ:B"})
    write_rows(writer, "universe", days[2], universe_rows(["A", "B", "C"]))
    write_rows(writer, "universe", days[4], universe_rows(["A", "B"]))
    return writer, reader, days
