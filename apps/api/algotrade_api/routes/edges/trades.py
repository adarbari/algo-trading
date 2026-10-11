"""``GET /files/edges/{edge_id}/trades.csv?period=``: the trades of an edge's verdict basis as a
CSV file (ADR 0064 decision 11, amending ADR 0037: a file, not a page read). It calls the loader
``Query.edgeTrades`` reads, so the file has the same rows, the same licence redaction and the same
withheld out-of-sample trades as the page; the caller is authenticated like every route. A
ledger that cannot be read (no official run, pruned, never stored) is a 404 naming its public
kind, never its cause."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from algotrade.services.read.edge_evidence import trades
from algotrade.services.read.edge_evidence.trades_csv import csv_lines
from algotrade.services.read.evaluation.edges import load_edge
from algotrade_api.deps import Context

router = APIRouter(prefix="/files/edges", tags=["files"])


@router.get("/{edge_id}/trades.csv", response_class=StreamingResponse)
def trades_csv(
    ctx: Context,
    edge_id: str,
    period: Annotated[
        trades.Period, Query(description="which trades: in_sample, out_of_sample, live or all")
    ] = trades.Period.ALL,
) -> StreamingResponse:
    edge = load_edge(ctx, edge_id)
    if edge is None:
        raise HTTPException(404, f"no such edge: {edge_id}")
    found = trades.load_edge_trades(ctx, edge, period, limit=None)
    if found.unknown is not None:
        raise HTTPException(404, f"no ledger to read: {found.unknown.public_reason}")
    if found.basis is None:
        raise HTTPException(404, f"no ledger to read: {found.reason}")
    return StreamingResponse(
        csv_lines(found.rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{edge_id}-trades-{period.value}.csv"'
        },
    )
