"""Compute nightly features from stored chains (currently ``option_liquidity@v1``)."""

from collections.abc import Mapping
from datetime import date
from typing import Any, cast

import pandas as pd

from algotrade.data.chains import chain_status, option_quotes, underlying_quotes
from algotrade.features import option_liquidity as liq
from algotrade.features.registry import FEATURES
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TABLE = f"rollups/instrument/{liq.NAME}@v{liq.VERSION}"
HINT = "algotrade-ingest chains --date {d}"
TASK = "features-option_liquidity"
SOURCE = "features"


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
    ctx: TaskContext, session_date: date, params: liq.LiquidityParams | None = None
) -> RunRecord:
    assert TABLE in FEATURES
    reader = ctx.reader
    with IngestRun(ctx, TASK, session_date) as run:
        hint = HINT.format(d=session_date.isoformat())
        status = chain_status(reader, session_date, hint=hint)
        assert status is not None  # chain_status raises with a hint
        frame = liquidity_rows(
            status,
            option_quotes(reader, session_date),
            underlying_quotes(reader, session_date),
            session_date,
            params or liq.LiquidityParams(),
        )
        run.write(TABLE, frame, SOURCE)
        run.stats.update(rows=len(frame), liq_status=frame["liq_status"].value_counts().to_dict())
    return run.record
