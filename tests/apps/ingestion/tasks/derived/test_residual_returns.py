"""The ``residual-returns`` task on a store of bars, a universe, a reference snapshot and
``factor_betas@v1`` partitions: each window lands in its start session's partition with the
return minus the loadings times the factor returns; the betas are those of the session BEFORE
the start session (never a later partition: a window never sees its own returns); a window the
factor ETFs do not cover is UNMEASURED ``NO_FACTOR_HISTORY``; no betas stored is ``NO_BETAS``;
horizons come from the open edges' residual outcomes plus the default."""

from datetime import date

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.core.time.calendar import previous_session, sessions_ending
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.outcomes import DEFAULT_HORIZON, compute_outcomes
from algotrade_ingestion.tasks.derived.residual_returns import (
    FACTOR_BETAS,
    TABLE,
    check_residual_returns,
    compute_residual_returns,
    residual_horizons,
)
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import END, series, store, write_bars, write_rows
from tests.helpers.stored_frames import universe_rows

N = 40
SYMBOLS = ("A", "SPY", "IWM", "MTUM", "VLUE")
H = DEFAULT_HORIZON


def _reference() -> list[dict[str, object]]:
    return [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ",
         "security_type": "COMMON_STOCK", "multiplier": 1.0, "status": "ACTIVE",
         "delisted_on": None}
        for s in SYMBOLS
    ]  # fmt: skip


def _betas(day: date, mkt: float) -> list[dict[str, object]]:
    return [
        {"instrument_id": "EQ:A", "beta_mkt": mkt, "beta_size": 0.5, "beta_mom": -0.3,
         "beta_value": 0.2, "beta_sector": None, "ivol_252d": 0.2, "factor_obs": 250,
         "factor_status": "NO_SECTOR"}
    ]  # fmt: skip


def _store(
    betas: bool = True, skip: dict[str, list[int]] | None = None
) -> tuple[StoreWriter, StoreReader, list[date]]:
    writer, reader = store()
    closes = {f"EQ:{s}": series(N, seed=i + 1) for i, s in enumerate(SYMBOLS)}
    days = write_bars(writer, closes, skip=skip)
    write_rows(writer, "instruments/reference", days[0], _reference())
    write_rows(writer, "universe", days[0], universe_rows(list(SYMBOLS)))
    start = sessions_ending(END, H + 1)[0]
    if betas:
        write_rows(writer, FACTOR_BETAS, previous_session(start), _betas(start, 1.0))
        write_rows(writer, FACTOR_BETAS, start, _betas(start, 99.0))  # the window's own: unseen
    return writer, reader, days


def _a(reader: StoreReader) -> pd.Series:
    start = sessions_ending(END, H + 1)[0]
    part = reader.table(TABLE, start)
    assert part is not None
    rows = part[(part["instrument_id"] == "EQ:A") & (part["horizon_sessions"] == H)]
    assert len(rows) == 1
    return rows.iloc[0]


def _ret(days: list[date], seed: int, start: date) -> float:
    closes = dict(zip(days, series(N, seed=seed), strict=True))
    return closes[END] / closes[start] - 1


def test_horizons_are_the_default_plus_the_residual_edges_open_horizons() -> None:
    assert DEFAULT_HORIZON in residual_horizons()


def test_the_row_is_the_return_minus_the_loadings_of_the_session_before_s() -> None:
    writer, reader, days = _store()
    record = compute_residual_returns(task_ctx(writer), END)
    assert record.status == RunStatus.COMPLETE, record.stats
    start = sessions_ending(END, H + 1)[0]
    own = _ret(days, 1, start)
    spy, iwm, mtum, vlue = (_ret(days, k, start) for k in (2, 3, 4, 5))
    explained = 1.0 * spy + 0.5 * (iwm - spy) - 0.3 * (mtum - spy) + 0.2 * (vlue - spy)
    row = _a(reader)
    assert row["fwd_residual_return"] == pytest.approx(own - explained)  # beta 1.0, never 99
    assert row["outcome_status"] == "COMPLETE" and row["window_end"] == END
    assert row["beta_session"] == previous_session(start)
    assert pd.Timestamp(row["ts"]).date() == start


def test_a_window_before_the_factor_etfs_exist_is_unmeasured_not_market_only() -> None:
    first_etf_bar = N - 10  # the momentum and value ETFs start inside the window
    skip = {f"EQ:{t}": list(range(first_etf_bar)) for t in ("MTUM", "VLUE")}
    writer, reader, _ = _store(skip=skip)
    compute_residual_returns(task_ctx(writer), END)
    row = _a(reader)
    assert row["outcome_status"] == "UNMEASURED"
    assert row["outcome_reason"] == "NO_FACTOR_HISTORY"
    assert pd.isna(row["fwd_residual_return"])


def test_no_betas_stored_before_s_is_unmeasured_no_betas_never_zero() -> None:
    writer, reader, _ = _store(betas=False)
    record = compute_residual_returns(task_ctx(writer), END)
    row = _a(reader)
    assert (row["outcome_status"], row["outcome_reason"]) == ("UNMEASURED", "NO_BETAS")
    assert pd.isna(row["fwd_residual_return"]) and pd.isna(row["fwd_factor_return"])
    assert record.stats[f"h{H}"]["betas_stored"] is False


def test_a_backfill_writes_one_run_per_window_end_and_the_nightly_agrees() -> None:
    nightly_writer, nightly_reader, days = _store()
    compute_residual_returns(task_ctx(nightly_writer), END)
    backfill_writer, backfill_reader, _ = _store()
    compute_residual_returns(task_ctx(backfill_writer), END, END, END)
    drop = ["run_id", "knowledge_ts"]
    start = sessions_ending(END, H + 1)[0]
    one, two = (r.table(TABLE, start) for r in (nightly_reader, backfill_reader))
    assert one is not None and two is not None
    mine = lambda f: f[f["window_end"] == END].drop(columns=drop).reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(mine(one), mine(two))
    assert days[-1] == END


def test_a_window_not_closed_is_refused() -> None:
    writer, _, _ = _store()
    with pytest.raises(ValueError, match="not closed"):
        compute_residual_returns(
            task_ctx(writer, clock=lambda: pd.Timestamp("2026-10-02T12:00Z")), END
        )


def test_the_acceptance_check_warns_on_gaps_and_fails_on_a_missing_row() -> None:
    writer, reader, _ = _store()
    assert check_residual_returns(reader, END, SourcesSettings())[0].status == "FAIL"  # no run
    ctx = task_ctx(writer)
    compute_outcomes(ctx, END)
    compute_residual_returns(ctx, END)
    (warn,) = check_residual_returns(reader, END, SourcesSettings())
    assert warn.status == "WARN" and "NO_BETAS" in warn.detail  # the ETFs have no betas rows
    start = sessions_ending(END, H + 1)[0]
    extra = reader.table(FORWARD_RETURNS, start)
    assert extra is not None
    extra = extra[extra["horizon_sessions"] == H].head(1).assign(instrument_id="EQ:ZZ")
    extra = extra.assign(
        run_id="late", knowledge_ts=pd.Timestamp(END, tz="UTC") + pd.Timedelta(days=2)
    )
    writer.write_table(FORWARD_RETURNS, start, "late", extra)  # a forward row the run never saw
    (fail,) = check_residual_returns(reader, END, SourcesSettings())
    assert fail.status == "FAIL" and "without a residual row" in fail.detail
