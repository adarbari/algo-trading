"""Compute nightly features from stored chains (currently ``option_liquidity@v1``)."""

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any, cast

import pandas as pd

from algotrade.features import option_liquidity as liq
from algotrade.features.registry import FEATURES
from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.common import stamp
from algotrade_ingestion.jobs.option_chains import OPTIONS, STATUS, UNDERLYINGS

TABLE = f"rollups/instrument/{liq.NAME}@v{liq.VERSION}"
HINT = "algotrade-ingest chains --date {d}"


def liquidity_rows(
    status: pd.DataFrame,
    options: pd.DataFrame | None,
    underlyings: pd.DataFrame | None,
    session: date,
    params: liq.LiquidityParams,
) -> pd.DataFrame:
    chains = dict(tuple(options.groupby("underlying_id"))) if options is not None else {}
    quotes = underlyings.set_index("instrument_id") if underlyings is not None else pd.DataFrame()
    rows = []
    for record in status.to_dict("records"):
        iid, fetch_status = record["instrument_id"], str(record["status"])
        if fetch_status not in ("OK", "NO_STANDARD_SERIES"):
            row = {"liq_status": fetch_status, "put_tier": "D", "call_tier": "D"}
        else:
            frame = chains.get(iid)
            contracts = (
                liq.contracts_from_rows(cast(list[Mapping[str, Any]], frame.to_dict("records")))
                if frame is not None
                else []
            )
            row = liq.assess(contracts, session, params)
        if iid in quotes.index:
            q = quotes.loc[iid]
            row.update(
                underlying_price=q["price"],
                iv30=q["iv30"],
                chain_asof=q["ts"],
                stock_volume=q["volume"],
            )
        rows.append({"instrument_id": iid, **row})
    return pd.DataFrame(rows)


def compute_option_liquidity(
    reader: StoreReader,
    writer: StoreWriter,
    session_date: date,
    params: liq.LiquidityParams | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    assert TABLE in FEATURES
    now = clock()
    hint = HINT.format(d=session_date.isoformat())
    status = reader.require(STATUS, session_date, hint)
    frame = liquidity_rows(
        status,
        reader.table(OPTIONS, session_date),
        reader.table(UNDERLYINGS, session_date),
        session_date,
        params or liq.LiquidityParams(),
    )
    run_id = new_run_id("features-option_liquidity", session_date, now)
    writer.write_table(
        TABLE, session_date, run_id, stamp(frame, session_date, now, "features", run_id)
    )
    stats = {"rows": len(frame), "liq_status": frame["liq_status"].value_counts().to_dict()}
    record = RunRecord(
        run_id, "features-option_liquidity", session_date, now, RunStatus.COMPLETE, now, stats=stats
    )
    writer.save_run(record)
    return record
