"""``export_file``: a surface's rows as CSV lines (ADR 0082 decision 6), what the viewer can see
and nothing else.

The file is built here from the surface's own loader (``surfaces.SURFACES``), under the ``f``
string the page shows (``filtering.codec``) and the request's ``ReadContext`` (so the viewer's data
licences, ADR 0069: a personal value is ``LICENCE`` to a viewer who does not hold it, the full
value to the holder), never from rows the browser holds. First line: a ``#`` notice that names the
session, the viewer and the licences held, and says personal-licence values are for the holder's own
use; a list cut at ``ROW_CAP`` says so on the second. The file is built whole (so the audit line
carries the row count) and the route sends its lines. Every non-header cell goes through ``cell``
(CSV injection)."""

import csv
import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from algotrade.services.read.context import NotFoundError, ReadContext
from algotrade.services.read.export.cells import cell
from algotrade.services.read.export.surfaces import ROW_CAP, SURFACES, Exported, Params
from algotrade.services.read.filtering.codec import decode_filters
from algotrade.services.read.filtering.masks import filter_hash
from algotrade.services.read.filtering.served import load_served_filters

NOTICE = "personal-licence values are for the holder's own use, not for redistribution"


@dataclass(frozen=True)
class ExportFile:
    """The file and what the audit line records: ``surface``, the viewer, the hash of the filters
    that narrowed it (``""``: none), the rows written, the licences held."""

    surface: str
    viewer: str
    filter_hash: str
    row_count: int
    licences: tuple[str, ...]
    lines: tuple[str, ...]


def notice(ctx: ReadContext) -> str:
    """The first line of every file."""
    held = ", ".join(sorted(ctx.licences))
    return (
        f"# algotrade export, session {ctx.session.date.isoformat()}, "
        f"viewer {ctx.user.user_id}, licences held: [{held}]; {NOTICE}\r\n"
    )


def _csv(records: Sequence[Sequence[str]]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for n, record in enumerate(records):
        writer.writerow(record if n == 0 else [cell(c) for c in record])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()


def export_file(
    ctx: ReadContext, surface: str, f: str | None, params: Params | None = None
) -> ExportFile:
    """The file of ``surface`` under ``f``. ``NotFoundError`` for a surface not registered;
    ``FilterRefusedError`` for a filter the viewer is not offered (nothing is read first)."""
    load = SURFACES.get(surface)
    if load is None:
        raise NotFoundError(f"no such surface to export: {surface}")
    filters = decode_filters(f)
    # a More-filters ``feature:<field>`` is offered only when it is asked for, as in the page's read
    resolved = load_served_filters(ctx, surface, ctx.session.date, [i.id for i in filters]).resolved
    resolved.check(i.id for i in filters)
    found: Exported = load(ctx, filters, params or Params())
    cut = (
        [f"# cut at {ROW_CAP} of {found.total} rows: narrow the filters for the rest\r\n"]
        if found.total > len(found.rows)
        else []
    )
    lines = (notice(ctx), *cut, *_csv((found.headers, *found.rows)))
    return ExportFile(
        surface,
        ctx.user.user_id,
        filter_hash(resolved, filters),
        len(found.rows),
        tuple(sorted(ctx.licences)),
        lines,
    )
