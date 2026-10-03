"""Read-only storage facade handed to backtests, screening, the API and features."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.core.errors import MissingDataError
from algotrade.core.fields import (
    COMPANY_TABLE,
    REFERENCE_TABLE,
    field_source,
    instrument_field,
)
from algotrade.core.instruments import AssetClass, Instrument
from algotrade.storage.interfaces import Backend
from algotrade.storage.runs import RunRecord


def _present[T](value: object, default: T) -> T:
    """``default`` when a column is absent, None or NaN (Parquet fills gaps with NaN)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class InstrumentView:
    """L1 for one date: reference facts + rollups, one row per instrument (ADR 0016).

    Columns are field names (``instrument.<col>``, ``rollup.<name>@vN.<col>``) plus
    ``instrument_id``. A rollup with no partition for ``session`` is listed in ``missing``
    and its fields are absent, which selections treat as UNKNOWN (never as a pass).
    """

    session: date
    reference_snapshot: date
    frame: pd.DataFrame
    missing: tuple[str, ...]


class StoreReader:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        return self._backend.tables.read(table, session_date, as_of, instruments)

    def require(
        self, table: str, session_date: date, hint: str, as_of: datetime | None = None
    ) -> pd.DataFrame:
        """Like ``table`` but raises ``MissingDataError`` instead of returning ``None``."""
        frame = self.table(table, session_date, as_of)
        if frame is None:
            raise MissingDataError(table, f"no data for {session_date.isoformat()}", hint)
        return frame

    def table_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        return self._backend.tables.read_range(table, start, end, as_of, instruments)

    # ------------------------------------------------------------------ L2: bars
    def bars(
        self,
        interval: str,
        start: date,
        end: date,
        instruments: Sequence[str] | None = None,
        as_of: datetime | None = None,
    ) -> pd.DataFrame:
        """Bars for ``start <= session_date <= end``, sorted by (instrument_id, ts).

        Raises ``MissingDataError`` when nothing is stored; backtests never fetch (ADR 0008).
        """
        table = f"bars/{interval}"
        frame = self.table_range(table, start, end, as_of, instruments)
        if frame is None:
            hint = f"run the ingestion job that loads {table} for {start}..{end}"
            raise MissingDataError(table, f"no bars between {start} and {end}", hint)
        return frame.sort_values(["instrument_id", "ts"], kind="stable").reset_index(drop=True)

    # ------------------------------------------------------------------ L1: instruments
    def instruments(
        self,
        on_or_before: date,
        instruments: Sequence[str] | None = None,
        as_of: datetime | None = None,
    ) -> pd.DataFrame:
        """The latest ``instruments/reference`` snapshot on or before ``on_or_before``."""
        table = "instruments/reference"
        snapshot = self.latest_date(table, on_or_before)
        if snapshot is None:
            hint = "run the ingestion job that loads instrument reference data"
            raise MissingDataError(table, f"no snapshot on or before {on_or_before}", hint)
        frame = self.table(table, snapshot, as_of, instruments)
        if frame is None:  # pragma: no cover - a listed date always has a run
            raise MissingDataError(table, f"snapshot {snapshot} unreadable", "re-run ingestion")
        return frame

    def instrument_view(
        self,
        session: date,
        fields: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
        as_of: datetime | None = None,
    ) -> InstrumentView:
        """Reference snapshot on or before ``session`` joined with rollups *for* ``session``.

        Company fields (``instrument.sector``…) come from the latest ``instruments/company``
        snapshot on or before ``session``; without one they are ``missing`` (UNKNOWN).

        ``fields`` limits the columns (and the rollup tables read); ``None`` means every
        reference column and no rollups.
        """
        reference = self.instruments(session, instruments, as_of)
        snapshot = self.latest_date(REFERENCE_TABLE, session)
        assert snapshot is not None  # instruments() raised otherwise
        wanted: dict[str, list[tuple[str, str]]] = {}
        for name in fields if fields is not None else [instrument_field(str(c)) for c in reference]:
            table, column = field_source(name)
            wanted.setdefault(table, []).append((name, column))
        out = pd.DataFrame({"instrument_id": reference["instrument_id"].astype(str)})
        missing: list[str] = []
        for table, columns in wanted.items():
            if table == REFERENCE_TABLE:
                frame: pd.DataFrame | None = reference
            elif table == COMPANY_TABLE:  # a snapshot table, like the reference
                company = self.latest_date(table, session)
                frame = self.table(table, company, as_of) if company is not None else None
            else:
                frame = self.table(table, session, as_of)
            if frame is None:
                missing.append(table)
                continue
            # Build the joined columns by name so the join key itself is never renamed.
            picked = pd.DataFrame({"instrument_id": frame["instrument_id"].astype(str)})
            for name, column in columns:
                if column in frame.columns:
                    picked[name] = frame[column].to_numpy()
            out = out.merge(picked, on="instrument_id", how="left")
        return InstrumentView(session, snapshot, out, tuple(sorted(missing)))

    def instrument_terms(
        self, on_or_before: date, instruments: Sequence[str] | None = None
    ) -> dict[str, Instrument]:
        """Contract terms (multiplier, tick size, asset class) for engines."""
        frame = self.instruments(on_or_before, instruments)
        return {
            str(r.instrument_id): Instrument(
                instrument_id=str(r.instrument_id),
                symbol=str(r.symbol),
                asset_class=AssetClass(str(r.asset_class)),
                multiplier=float(r.multiplier),  # type: ignore[arg-type]
                currency=str(_present(getattr(r, "currency", None), "USD")),
                tick_size=float(_present(getattr(r, "tick_size", None), 0.01)),
            )
            for r in frame.itertuples(index=False)
        }

    def dates(self, table: str) -> list[date]:
        return self._backend.tables.dates(table)

    def latest_date(self, table: str, on_or_before: date | None = None) -> date | None:
        dates = [d for d in self.dates(table) if on_or_before is None or d <= on_or_before]
        return dates[-1] if dates else None

    def runs(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        return self._backend.runs.find(job, session_date)
