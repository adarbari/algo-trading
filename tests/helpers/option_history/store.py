"""A synthetic option-history store (ADR 0084): per session the quotes of a few underlyings priced
by Black-Scholes at a known vol, and each underlying's day, one committed ``option-history-session``
run per session (what ``option-history-import`` leaves). Invented rows, never the vendor's."""

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data.option_history.reading import SESSION_TASK
from algotrade.quant.black_scholes import price
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import IngestRun
from tests.helpers.ingest_fakes import task_ctx

SOURCE = "historicaloptiondata"
VOL, HALF = 0.30, 0.05
STRIKES = (80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0)


def imported_at(day: date) -> datetime:
    """The write instant of a session's import: a day after it (a history is bought later)."""
    return datetime.combine(day, datetime.min.time(), UTC) + timedelta(days=1, hours=3)


def day_frames(
    day: date, expiry: date, names: Mapping[str, tuple[str, float]], strikes: Sequence[float]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Quotes and underlyings of one session; ``names``: symbol -> (underlying id, spot)."""
    quotes, unders = [], []
    stamp = pd.Timestamp(datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=20))
    for symbol, (uid, spot) in names.items():
        t = (expiry - day).days / 365
        unders.append({"symbol": symbol, "underlying_id": uid, "open": spot, "high": spot,
                       "low": spot, "close": spot, "volume": 1e6})  # fmt: skip
        for strike in strikes:
            for right in ("C", "P"):
                mid = float(price(spot, strike, t, 0.0, 0.0, VOL, right == "C"))
                quotes.append({
                    "instrument_id": f"OPT:{symbol}{expiry:%y%m%d}{right}{int(strike * 1000):08d}",
                    "symbol": symbol, "ts": stamp, "expiry": expiry, "right": right,
                    "strike": strike, "underlying_id": uid, "root": symbol,
                    "bid": max(mid - HALF, 0.01), "ask": mid + HALF, "last": mid,
                    "underlying_price": spot, "volume": 10.0, "open_interest": 100.0,
                    "iv": VOL, "delta": 0.5,
                })  # fmt: skip
    return pd.DataFrame(quotes), pd.DataFrame(unders)


def write_history(
    backend: MemoryBackend,
    days: Sequence[date],
    names: Mapping[str, tuple[str, float]],
    expiry: date,
    drift: float = 1.0,
    strikes: Sequence[float] = STRIKES,
    clock: Callable[[date], datetime] = imported_at,
) -> None:
    """Every day of ``days`` as a committed import run; spots rise ``drift`` a session."""
    writer = StoreWriter(backend)
    for i, day in enumerate(days):
        moved = {s: (uid, spot + i * drift) for s, (uid, spot) in names.items()}
        quotes, unders = day_frames(day, expiry, moved, strikes)
        ctx = task_ctx(writer, clock=lambda d=day: clock(d))
        with IngestRun(ctx, SESSION_TASK, day) as run:
            run.write("option_history/quotes", quotes, SOURCE, session=day)
            run.write("option_history/underlying", unders, SOURCE, session=day)
