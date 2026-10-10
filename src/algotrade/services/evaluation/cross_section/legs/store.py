"""The stored legs of an edge (ADR 0063): ``results/edge_legs``, the one module that names it.
``legs_frame`` stamps encoded rows (``rows.py``), ``write_legs`` stages them one partition per
decision session inside the caller's ``publishing`` block (so they are visible only with the run's
rows and record), ``read_legs`` reads an edge's rows with one range read and decodes them."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.legs.rows import StoredLegs, decode_frame
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import EDGE_LEGS, result_table

RESULT = "edge_legs"
TABLE = result_table(RESULT)
SOURCE = "edge-eval"


def legs_frame(rows: Sequence[Mapping[str, Any]], run_id: str, now: datetime) -> pd.DataFrame:
    """The ``results/edge_legs`` rows of one run, stamped (``session_date`` is each row's own)."""
    columns = {}
    for column in EDGE_LEGS.columns:
        values = [row.get(column.name) for row in rows]
        # a list column nobody filled is None, never the NaN of a float column
        columns[column.name] = (
            pd.Series(values, dtype=object) if column.type.endswith("[]") else values
        )
    frame = pd.DataFrame(columns)
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = SOURCE
    frame["run_id"] = run_id
    return frame


def write_legs(writer: ResultWriter, run_id: str, frame: pd.DataFrame) -> int:
    """Stage ``frame`` pending, one partition per decision session; the caller's ``publishing``
    block commits them. Returns the partitions written."""
    written = 0
    for day, part in frame.groupby("session_date", sort=True):
        when = pd.Timestamp(day).date()  # type: ignore[arg-type]
        writer.write_result(RESULT, when, run_id, part.reset_index(drop=True), pending=True)
        written += 1
    return written


def read_legs(
    reader: StoreReader,
    user_id: str,
    edge_id: str,
    start: date,
    end: date,
    as_of: datetime | None = None,
) -> StoredLegs:
    """One edge's rows of the decision sessions ``start..end`` (one range read; the latest run
    known at ``as_of`` wins per key), decoded; empty when none are stored."""
    frame = reader.table_range(TABLE, start, end, as_of)
    if frame is None or frame.empty:
        return StoredLegs()
    mine = frame[(frame["user_id"] == user_id) & (frame["edge_id"] == edge_id)]
    return decode_frame(mine)
