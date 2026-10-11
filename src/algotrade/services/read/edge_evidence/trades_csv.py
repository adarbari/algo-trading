"""The ledger of ``trades.load_edge_trades`` as CSV text (ADR 0064 decision 11).

The file is the page's rows with no paging: every column the GraphQL row has, in its order, a
value the viewer may not read as its public kind (``LICENCE``), one not stored empty, never 0.
It renders the rows the loader already redacted, so the file and the graph cannot disagree: same
basis, same licence rule, same hidden copy rule. Lines are yielded one at a time for streaming."""

import csv
import io
from collections.abc import Iterator

from algotrade.services.read.evaluation.runs import TradeCell, TradeRow

COLUMNS = (
    "source", "variant", "horizon_sessions", "decision_session", "entry_session", "exit_session",
    "instrument_id", "rank", "status", "excluded_reason", "hit", "delisted", "before_split",
    "score", "value", "gross_value", "max_drawdown", "adv_usd", "reference", "touch",
)  # fmt: skip


def _cell(value: object) -> str:
    if isinstance(value, TradeCell):
        return value.unknown.kind.value if value.unknown is not None else _cell(value.value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def csv_lines(rows: tuple[TradeRow, ...]) -> Iterator[str]:
    """The header, then one line per row of ``rows``."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for record in (COLUMNS, *([_cell(getattr(r, c)) for c in COLUMNS] for r in rows)):
        writer.writerow(record)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
