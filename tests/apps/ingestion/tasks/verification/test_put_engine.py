"""Cboe's PUT index through the engine's trade rows (ADR 0084 decision 6, E5): a monthly short put
on rows of ``structure_pnl@v2`` compounds with the bill carry into a level that matches a published
one built the same way, and a published level that drifts a year away from it is outside the
tolerance; overlapping trades (a ladder) are refused."""

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.verification import put_engine
from tests.helpers.ingest_fakes import task_ctx

RATE = 0.02


def _rows(n: int = 24, pnl: float = 30.0) -> pd.DataFrame:
    start = date(2018, 1, 17)
    out = []
    for i in range(n):
        entry = start + timedelta(days=28 * i)
        out.append({
            "ts": pd.Timestamp(datetime.combine(entry, datetime.min.time()), tz="UTC"),
            "exit_session": entry + timedelta(days=28), "collateral": 2800.0,
            "entry_net_mid": -60.0, "pnl_mid": pnl * (1 + 0.5 * (i % 3)),
            "outcome_status": "COMPLETE",
        })  # fmt: skip
    return pd.DataFrame(out)


def _published(levels: pd.Series, drift_per_year_bp: float = 0.0) -> pd.Series:
    years = pd.Series([(d - levels.index[0]).days / 365.25 for d in levels.index], levels.index)
    return levels * (1 + drift_per_year_bp / 1e4 * years)


def test_a_published_level_built_the_same_way_matches_within_tolerance() -> None:
    rows = _rows()
    levels = put_engine.level_series(rows, lambda d: RATE)
    assert levels.iloc[0] == 1.0 and len(levels) == 25
    stats = put_engine.engine_replication(rows, lambda d: RATE, _published(levels))
    assert stats["within_tolerance"] and abs(stats["annual_gap_bp"]) < 1e-6
    carry = RATE * 28 / 360 * (1 + 60 / 2800)
    assert levels.iloc[1] == pytest.approx(1 + 30 / 2800 + carry)  # the first trade: i = 0


def test_a_level_that_drifts_a_year_away_is_outside_the_tolerance() -> None:
    rows = _rows()
    levels = put_engine.level_series(rows, lambda d: RATE)
    stats = put_engine.engine_replication(rows, lambda d: RATE, _published(levels, 150.0))
    assert not stats["within_tolerance"] and stats["annual_gap_bp"] < -100


def test_overlapping_trades_are_refused() -> None:
    rows = _rows(3)
    rows["exit_session"] = rows["exit_session"] + timedelta(days=30)
    with pytest.raises(ValueError, match="overlap"):
        put_engine.level_series(rows, lambda d: RATE)


class FakeReader:
    """The main store's reader as the check uses it: the rows of one partition."""

    def __init__(self, rows: pd.DataFrame) -> None:
        self.rows = rows

    def dates(self, table: str) -> list[date]:
        return [date(2018, 1, 17)]

    def table(self, table: str, day: date) -> pd.DataFrame:
        return self.rows

    def including(self, run_id: str) -> "FakeReader":
        return self


def _check(rows: pd.DataFrame, drift_bp: float, monkeypatch: pytest.MonkeyPatch, **kw: object):  # type: ignore[no-untyped-def]
    stored = rows.assign(
        instrument_id=put_engine.UNDERLYING, price_source=put_engine.HISTORY, position_key="k"
    )
    levels = put_engine.level_series(rows, lambda d: RATE)
    monkeypatch.setattr(put_engine, "three_month_rate", lambda reader, d: RATE)
    monkeypatch.setattr(put_engine, "published_levels", lambda reader: _published(levels, drift_bp))
    ctx = task_ctx(StoreWriter(MemoryBackend()), reader=FakeReader(stored))  # type: ignore[arg-type]
    return put_engine.put_engine_check(ctx, date(2026, 11, 3), None, None, kw.get("position"))  # type: ignore[arg-type]


def test_the_check_passes_a_matching_level_and_fails_a_drifting_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok = _check(_rows(), 0.0, monkeypatch)
    assert ok.status == RunStatus.COMPLETE and ok.stats["within_tolerance"], ok.stats
    bad = _check(_rows(), 150.0, monkeypatch)
    assert bad.status == RunStatus.FAILED and not bad.stats["within_tolerance"]


def test_the_check_asks_for_a_position_that_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _check(_rows(3), 0.0, monkeypatch, position="nope")
    assert record.status == RunStatus.FAILED
