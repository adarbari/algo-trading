"""The ``rollups`` task runs rollups in dependency order (each reads what the previous one
wrote this run) and does not compute the dependents of a rollup that failed."""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from algotrade.features.registry import GROUPS
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.derived.rollups import compute_rollups
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import (
    END,
    chain_rows,
    series,
    store,
    write_bars,
    write_chains,
    write_curve,
    write_dividends,
)

NEAR, FAR = date(2026, 10, 16), date(2026, 11, 20)


def _market() -> tuple[object, object]:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(260, start=100.0)})
    spot = float(series(260, start=100.0)[-1])
    write_dividends(writer, [("EQ:A", date(2026, 6, 1), spot * 0.02, "recurring")])
    q = 0.02  # the trailing yield dividends@v1 will compute
    rows = chain_rows("EQ:A", END, spot, {NEAR: 0.3, FAR: 0.3}, 0.04, q, strikes=_strikes(spot))
    write_chains(writer, END, rows, {"EQ:A": spot})
    write_curve(writer, END, 0.04)
    return writer, reader


def _strikes(spot: float) -> tuple[float, ...]:
    base = round(spot)
    return tuple(float(base + k) for k in range(-10, 11, 2))


def test_rollups_read_the_rollups_computed_before_them() -> None:
    writer, reader = _market()
    record = compute_rollups(task_ctx(writer, reader), END)  # type: ignore[arg-type]
    assert record.items["iv30@v1"].startswith("OK") and record.items["iv_history@v1"].startswith(
        "OK"
    )
    iv = reader.table("rollups/instrument/iv30@v1", END)  # type: ignore[attr-defined]
    assert iv is not None
    a = iv.set_index("instrument_id").loc["EQ:A"]
    assert a["div_yield"] == pytest.approx(0.02)  # from dividends@v1, computed this run
    assert a["iv30"] == pytest.approx(0.30, abs=1e-6)  # q = 0.02 recovers the true vol
    hist = reader.table("rollups/instrument/iv_history@v1", END)  # type: ignore[attr-defined]
    assert hist is not None and hist["history_days"].iloc[0] == 1
    assert hist["rank_status"].iloc[0] == "UNKNOWN" and pd.notna(hist["iv_hv_spread"].iloc[0])
    liq = reader.table("rollups/instrument/liquidity_class@v1", END)  # type: ignore[attr-defined]
    assert liq is not None and liq["liquidity_class"].iloc[0] == "LOW"  # $0.1M ADV


def test_a_failed_rollup_blocks_its_dependents(monkeypatch: pytest.MonkeyPatch) -> None:
    writer, reader = _market()

    def boom(*args: object) -> pd.DataFrame:
        raise RuntimeError("boom")

    broken = dataclasses.replace(GROUPS["price_stats@v1"], compute=boom)
    monkeypatch.setitem(GROUPS, "price_stats@v1", broken)
    record = compute_rollups(task_ctx(writer, reader), END)  # type: ignore[arg-type]
    assert record.status is RunStatus.PARTIAL
    assert record.items["price_stats@v1"] == "FETCH_ERROR: boom"
    for key in ("dividends@v1", "iv30@v1", "iv_history@v1", "liquidity_class@v1"):
        assert record.items[key] == "FAILED: not computed: price_stats@v1 failed", key
    assert record.items["earnings@v1"] == "NO_INPUT"
