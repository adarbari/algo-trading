"""Analyst snapshot rows as the stored table holds them, and the input a rollup session sees."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.analyst.reading import KINDS, TABLE, snapshot_window
from algotrade.features.rollups.consensus.analyst_status import LOOKBACK
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

FIRST = date(2026, 1, 1)  # the first session a window reads from


def night(session: date, hour: int = 22) -> datetime:
    """The publish instant of a nightly run for ``session``: after its close in New York."""
    return datetime(session.year, session.month, session.day, hour, 5, tzinfo=UTC)


def estimates(iid: str, periods: dict[str, float], **more: object) -> list[dict]:
    """FMP annual estimate rows: one per fiscal year end, EPS and revenue averages."""
    return [
        {
            "instrument_id": iid,
            "kind": "estimates_annual",
            "period": period,
            "eps_avg": eps,
            "revenue_avg": eps * 1e9,
            "num_analysts_eps": 12,
            "num_analysts_revenue": 9,
            **more,
        }
        for period, eps in periods.items()
    ]


def target(iid: str, consensus: float) -> dict:
    return {
        "instrument_id": iid,
        "kind": "price_target",
        "period": "current",
        "target_consensus": consensus,
        "target_median": consensus - 1,
        "target_high": consensus + 20,
        "target_low": consensus - 20,
    }


def recommendation(iid: str, months: dict[str, tuple[int, int, int, int, int]]) -> list[dict]:
    """Finnhub trend rows: one per month (its first day), the counts strong buy, buy, hold, sell,
    strong sell; store them with ``put(..., source="finnhub")``."""
    return [
        {
            "instrument_id": iid,
            "kind": "recommendation",
            "period": month,
            **dict(zip(("strong_buy", "buy", "hold", "sell", "strong_sell"), counts, strict=True)),
        }
        for month, counts in months.items()
    ]


def marker(iid: str, status: str) -> dict:
    return {"instrument_id": iid, "kind": "coverage", "period": "current", "status": status}


def put(
    writer: StoreWriter,
    session: date,
    rows: list[dict],
    run_id: str = "r",
    knowledge: datetime | None = None,
    source: str = "fmp",
) -> None:
    """One run's rows into the session's partition (``ts``: five minutes before publication)."""
    published = knowledge or night(session)
    rows = [{"ts": pd.Timestamp(published) - pd.Timedelta(minutes=5), **r} for r in rows]
    writer.write_table(
        TABLE,
        session,
        f"{run_id}{session}",
        stamped(rows, session, f"{run_id}{session}", published, source),
    )


def store() -> StoreWriter:
    return StoreWriter(MemoryBackend())


def visible(writer: StoreWriter, session: date) -> pd.DataFrame | None:
    """What the ``analyst/estimate_snapshots`` input hands a rollup of ``session``."""
    return snapshot_window(StoreReader(writer.backend), KINDS, FIRST).at(session, LOOKBACK)


def universe(*ids: str, etfs: tuple[str, ...] = ()) -> pd.DataFrame:
    rows = [{"instrument_id": i, "asset_class": "STOCK"} for i in ids]
    return pd.DataFrame(rows + [{"instrument_id": i, "asset_class": "ETF"} for i in etfs])
