"""The catalogue fields an option trade's exit rules name, read one close at a time (ADR 0088,
design 2.4a, 2.13): ``FieldLoader`` reads each field of a close from that close's own partition
only (``data.rollups.group_view``; a rule observed at close t acts at t + 1, so t's partition is
the latest a decision may use), once per session and field set a run, and returns the latest
``knowledge_ts`` of the partitions it read so a row's ``knowledge_ts`` stops at its own exit.
``refuse_unstored`` names the fields a window cannot read at all (an expression feature, an
instrument fact, or a feature group with no partition anywhere in S..T): the writer refuses
that position (recorded, the others still write) rather than run a rule as one that never fires.
A close whose partition lacks a name's row (or holds NaN) gives it a None: the rule is UNKNOWN
there, never filled from another session."""

import math
from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import field_source, group_of_table
from algotrade.core.model.predicates import FieldValue
from algotrade.data import StoreReader
from algotrade.data.rollups import group_stamp, group_view

type Closes = dict[str, dict[str, FieldValue]]  # name -> field -> value at one close


def _plain(value: object) -> FieldValue:
    """A stored cell as a rule value: NaN / NA are missing (UNKNOWN), numpy scalars are Python."""
    if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return None
    item = getattr(value, "item", None)
    out: FieldValue = item() if callable(item) else value  # type: ignore[assignment]
    return None if isinstance(out, float) and math.isnan(out) else out


class FieldLoader:
    """The fields of closes from the store, cached for a run (one partition read a session)."""

    def __init__(self, reader: StoreReader) -> None:
        self.reader = reader
        self._frames: dict[tuple[date, tuple[str, ...]], tuple[pd.DataFrame, frozenset[str]]] = {}
        self._stamps: dict[tuple[date, tuple[str, ...]], datetime | None] = {}

    def __call__(
        self, day: date, fields: Sequence[str], names: Sequence[str]
    ) -> tuple[Closes, datetime | None]:
        """``name -> field -> value`` at ``day``'s close for ``names`` (None where the partition
        has no value; a field whose table has no partition that day is absent) and the latest
        ``knowledge_ts`` read (None: nothing read)."""
        if not fields:
            return {}, None
        key = (day, tuple(sorted(fields)))
        wanted = frozenset(names)
        cached = self._frames.get(key)
        if cached is None or not wanted <= cached[1]:
            ids = sorted(wanted | (cached[1] if cached else frozenset()))
            frame, _ = group_view(self.reader, day, key[1], ids)
            self._frames[key] = (frame.set_index("instrument_id"), frozenset(ids))
            self._stamps[key] = group_stamp(self.reader, day, key[1])
        frame = self._frames[key][0]
        out: Closes = {}
        for name in wanted:
            if name in frame.index:
                row = frame.loc[name]
                values = {f: _plain(row[f]) for f in key[1] if f in frame.columns}
                if values:  # a table with no partition for the day leaves no column at all
                    out[name] = values
        return out, self._stamps[key]


def refuse_unstored(
    reader: StoreReader, fields: Sequence[str], closes: Sequence[date]
) -> list[str]:
    """The reasons (one per field) a window cannot read ``fields`` at its ``closes``: a field
    that is not a stored feature group column, or whose table has no partition on any close."""
    problems = []
    stored: dict[str, set[date]] = {}
    for name in sorted(set(fields)):
        try:
            table, _ = field_source(name)
        except ConfigurationError:  # a computed or unknown field has no stored column
            problems.append(f"{name}: not a stored feature column")
            continue
        if group_of_table(table) is None:
            problems.append(f"{name}: not a stored feature group column")
            continue
        if table not in stored:
            stored[table] = set(reader.dates(table))
        if not stored[table] & set(closes):
            problems.append(f"{name}: no stored partition of {table} in {closes[0]}..{closes[-1]}")
    return problems
