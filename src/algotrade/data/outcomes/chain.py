"""Read chain P&L outcomes (``outcomes/option/structure_pnl@v1``, written by the ingestion
``option-outcomes`` task; ADR 0053 amendment, EB H13) for the start sessions a harness evaluates:
one row per (underlying, start session S, structure, tenor rule, horizon). The frames carry the
columns of the price outcomes (``OUTCOME_FIELDS``, the return fields empty) beside ``CHAIN_FIELDS``
so the harness reads either grain through one path. A window not closed, or not computed, has no
row; an ``UNMEASURED`` row (a chain missing or stale on a session of the window, ``outcome_reason``)
has no P&L and is excluded by the caller, never counted a miss. ``as_of`` keeps only rows known
by then (row by row); a row's ``knowledge_ts`` is its exit chain's, so a window is known only after
its exit chain was.
"""

from collections.abc import Iterable, Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.outcomes.reading import OUTCOME_FIELDS
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import FORWARD_RETURNS, OPTION_PNL, spec_for

CHAIN_FIELDS = (
    "structure", "tenor_days", "entry_spot", "entry_mid", "entry_ask", "exit_mid", "exit_bid",
    "pnl_per_underlying", "hedged_pnl_per_underlying", "hedge_reason",
)  # fmt: skip
CHAIN_COLUMNS = ("instrument_id", "horizon_sessions", *OUTCOME_FIELDS, *CHAIN_FIELDS)
_KEY = ("instrument_id", "session_date", "horizon_sessions", "benchmark", "window_end")


def chain_sessions(reader: StoreReader) -> list[date]:
    """The start sessions with a stored chain outcome partition, ascending."""
    return list(reader.dates(OPTION_PNL))


def chain_seqs(reader: StoreReader, sessions: Iterable[date]) -> dict[date, int]:
    """The commit sequence of each start session's committed chain outcome partition (those of
    ``sessions`` that exist), read before the rows so a later commit changes it (ADR 0063)."""
    wanted = sorted(set(sessions))
    if not wanted:
        return {}
    found = reader.partition_seq(OPTION_PNL, wanted[0], wanted[-1])
    return {d: s for d, s in found.items() if d in set(wanted)}


def chain_stamps(
    reader: StoreReader, sessions: Iterable[date], as_of: datetime, names_for: Iterable[int] = ()
) -> tuple[dict[tuple[date, int], datetime], dict[tuple[date, int], frozenset[str]]]:
    """Per (start session, horizon) of ``sessions`` with a row known by ``as_of``: the latest
    ``knowledge_ts`` among them and, for the horizons in ``names_for``, the instrument ids."""
    wanted_names = set(names_for)
    latest: dict[tuple[date, int], datetime] = {}
    names: dict[tuple[date, int], set[str]] = {}
    for day in sorted(set(sessions)):
        frame = reader.table_range(
            OPTION_PNL, day, day, as_of, columns=("instrument_id", "horizon_sessions")
        )
        if frame is None:
            continue
        known = pd.to_datetime(frame["knowledge_ts"], utc=True)
        keep = known <= pd.Timestamp(as_of)
        for horizon, stamp, name in zip(
            frame.loc[keep, "horizon_sessions"],
            known[keep].dt.to_pydatetime(),
            frame.loc[keep, "instrument_id"],
            strict=True,
        ):
            key = (day, int(horizon))
            if key[1] in wanted_names:
                names.setdefault(key, set()).add(str(name))
            if key not in latest or stamp > latest[key]:
                latest[key] = stamp
    return latest, {k: frozenset(v) for k, v in names.items()}


def missing_chain(sessions: Sequence[date]) -> MissingDataError:
    """The error of start ``sessions`` none of which has a stored chain outcome."""
    wanted = sorted(set(sessions))
    hint = f"run `algotrade-ingest run option-outcomes --from ... --to ...` past {wanted[-1]}"
    return MissingDataError(OPTION_PNL, f"no chain outcomes for {wanted[0]}..{wanted[-1]}", hint)


def read_chain_stored(
    reader: StoreReader, sessions: Sequence[date], as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The stored rows of the start ``sessions``' partitions, every structure, tenor and
    horizon (None: none stored)."""
    wanted = sorted(set(sessions))
    stored = set(reader.dates(OPTION_PNL))
    parts = [reader.table(OPTION_PNL, d, as_of) for d in wanted if d in stored]
    parts = [p for p in parts if p is not None and not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else None


def select_chain(
    frame: pd.DataFrame, horizon: int, sessions: Sequence[date], as_of: datetime | None = None
) -> pd.DataFrame:
    """The ``horizon`` rows of ``frame`` for the start ``sessions`` in the shape of the price
    outcomes (``CHAIN_COLUMNS`` and the keys): the return fields empty, ``benchmark`` ``none``."""
    starts = pd.to_datetime(frame["session_date"]).dt.date
    keep = starts.isin(set(sessions)) & (frame["horizon_sessions"] == horizon)
    if as_of is not None:
        keep &= pd.to_datetime(frame["knowledge_ts"], utc=True) <= pd.Timestamp(as_of)
    out = frame.loc[keep].copy()
    for column in ("fwd_return", "fwd_excess_return", "fwd_max_return", "fwd_max_drawdown",
                   "fwd_realised_vol"):  # fmt: skip
        out[column] = np.nan
    out["benchmark"] = "none"
    for nullable in ("outcome_reason", "hedge_reason"):  # a column no row of the partitions set
        if nullable not in out.columns:
            out[nullable] = None
    kept = out[[*_KEY, *OUTCOME_FIELDS, *CHAIN_FIELDS, "knowledge_ts"]]
    return kept.sort_values(["session_date", "instrument_id"], kind="stable").reset_index(drop=True)


def read_chain(
    reader: StoreReader, horizon: int, sessions: Sequence[date], as_of: datetime | None = None
) -> pd.DataFrame:
    """The ``horizon``-session chain outcomes of the start ``sessions`` (``select_chain``'s
    columns), every structure and tenor. Raises ``MissingDataError`` when none is stored."""
    wanted = sorted(set(sessions))
    frame = read_chain_stored(reader, wanted, as_of) if wanted else None
    if frame is None:
        raise missing_chain(wanted or [date.min])
    return select_chain(frame, horizon, wanted, as_of)


def licence_frames(
    reader: StoreReader, chain: bool, sessions: Iterable[date], as_of: datetime | None = None
) -> list[pd.DataFrame]:
    """The ``licence`` column of the outcome table's (the chain grain's when ``chain``)
    partitions over the span of the start ``sessions`` (one column read; the span is stricter
    than the sessions alone). Empty for an outcome table that declares no such
    column (``forward_returns@v2``: its rows are open). The harness folds them into the
    trial's licence for every entry session it covers, a stored leg it reuses included."""
    table = OPTION_PNL if chain else FORWARD_RETURNS
    if spec_for(table).column("licence") is None:
        return []
    days = sorted(set(sessions))
    if not days:
        return []
    found = reader.table_range(table, days[0], days[-1], as_of, columns=("licence",))
    return [] if found is None else [found]
