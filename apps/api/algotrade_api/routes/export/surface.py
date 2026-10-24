"""``GET /files/{surface}.csv?f=&screener=&columns=``: the rows a filter-bar surface shows under the
page's ``f`` string, as a CSV file (ADR 0082 decision 6, amending ADR 0037: a file, not a page
read). It calls ``services.read.export``, which reads through the surface's own gated loader and the
filtering pass with this request's ``ReadContext``, so the file has what the viewer can see: a
personal-licence value is its public kind (``LICENCE``) to a viewer who does not hold it (ADR 0069,
as the ledger file, ADR 0064 decision 10). One audit line per export: viewer, surface, filter hash,
rows, licences held."""

import datetime as dt
import logging
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from algotrade.config.user import UserContext
from algotrade.services.read.context import open_context
from algotrade.services.read.export.file import export_file
from algotrade.services.read.export.surfaces import MAX_COLUMNS, Params
from algotrade_api.deps import Caller, Followed, Store

router = APIRouter(prefix="/files", tags=["files"])
audit = logging.getLogger("algotrade_api.export")


def configure_audit() -> None:
    """Give the audit logger its own INFO handler: the server configures only its own loggers
    and the root is WARNING with no handler, so without this no export line is ever written.
    The handler writes to stderr, which the launchd agent sends to ``var/logs/api.err.log``
    beside the API log. Idempotent; called once, when this route module is imported by the API."""
    audit.setLevel(logging.INFO)
    if not audit.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        audit.addHandler(handler)


configure_audit()


@router.get("/{surface}.csv", response_class=StreamingResponse)
def surface_csv(
    store: Store,
    caller: Caller,
    serving: Followed,
    surface: str,
    f: Annotated[str | None, Query(description="the page's filter string (ADR 0082)")] = None,
    screener: Annotated[
        str | None, Query(description="screener_results: the screener whose run to export")
    ] = None,
    columns: Annotated[
        list[str] | None,
        Query(
            description="catalogue columns to add (screener_results, universe)",
            max_length=MAX_COLUMNS,
        ),
    ] = None,
    date: Annotated[
        dt.date | None, Query(description="the session to read (default: the one pages show)")
    ] = None,
) -> StreamingResponse:
    ctx = open_context(
        store.reader,
        store.configs,
        UserContext(caller.user_id),
        date,
        cache=store.cache,
        serving=serving,
    )
    found = export_file(ctx, surface, f, Params(screener, tuple(columns or ())))
    audit.info(
        "export viewer=%s surface=%s filters=%s rows=%d licences=%s",
        found.viewer,
        found.surface,
        found.filter_hash or "none",
        found.row_count,
        ",".join(found.licences),
    )
    return StreamingResponse(
        iter(found.lines),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{surface}-{ctx.session.date}.csv"'},
    )
