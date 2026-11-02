"""Read option trade outcomes (``outcomes/option/structure_pnl@v2``, written by the ingestion
``option-outcomes`` task; ADR 0088, design 2.5) for the start sessions a harness evaluates: one row
per (underlying, start session S, ``position_key``). The frames carry the columns of the price
outcomes (``OUTCOME_FIELDS``, the return fields empty) beside ``CHAIN_FIELDS``, the stored
``hold_sessions`` read as ``horizon_sessions``, so the harness reads either grain through one path.
A window not closed, or not computed, has no row; an ``UNMEASURED`` row (a chain missing or stale
on a session of the trade, ``outcome_reason``) has no P&L and is excluded by the caller, never
counted a miss. ``as_of`` keeps only rows known by then (row by row); a row's ``knowledge_ts`` is
its exit's, so a trade is known only after its exit chain was.

One source per S (H6): Cboe rows are read only from ``FIRST_CBOE_CHAIN_SESSION`` and bought-history
rows only before it; the other source's rows are dropped here, on every read path (rows of both
sources exist only for the owner's one-off comparison).
"""

from collections.abc import Iterable, Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.data.outcomes.reading import OUTCOME_FIELDS
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import FORWARD_RETURNS, STRUCTURE_PNL, spec_for

CBOE = "cboe"
CHAIN_FIELDS = (
    "position_key", "entry_spot", "entry_half_spread", "exit_half_spread", "pnl_mid",
    "exit_unknown_closes", "exit_session", "exit_kind", "collateral", "max_adverse",
    "price_source", "licence", "exit_basis", "leg_kinds", "leg_qty",
)  # fmt: skip
CHAIN_COLUMNS = ("instrument_id", "horizon_sessions", *OUTCOME_FIELDS, *CHAIN_FIELDS)
_KEY = ("instrument_id", "session_date", "horizon_sessions", "benchmark", "window_end")


def one_source(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` (stored trades with ``price_source`` and ``session_date``) without the rows of the
    source that does not own their session: Cboe from ``FIRST_CBOE_CHAIN_SESSION``, bought history
    before it (H6)."""
    if frame.empty:
        return frame
    after = pd.to_datetime(frame["session_date"]).dt.date >= FIRST_CBOE_CHAIN_SESSION
    cboe = frame["price_source"].astype(str) == CBOE
    return frame[(cboe == after).to_numpy()]


def chain_sessions(reader: StoreReader) -> list[date]:
    """The start sessions with a stored chain outcome partition, ascending."""
    return list(reader.dates(STRUCTURE_PNL))


def chain_seqs(reader: StoreReader, sessions: Iterable[date]) -> dict[date, int]:
    """The commit sequence of each start session's committed chain outcome partition (those of
    ``sessions`` that exist), read before the rows so a later commit changes it (ADR 0063)."""
    wanted = sorted(set(sessions))
    if not wanted:
        return {}
    found = reader.partition_seq(STRUCTURE_PNL, wanted[0], wanted[-1])
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
            STRUCTURE_PNL, day, day, as_of,
            columns=("instrument_id", "hold_sessions", "price_source"),
        )  # fmt: skip
        if frame is None:
            continue
        frame = one_source(frame)
        known = pd.to_datetime(frame["knowledge_ts"], utc=True)
        keep = known <= pd.Timestamp(as_of)
        for horizon, stamp, name in zip(
            frame.loc[keep, "hold_sessions"],
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
    return MissingDataError(STRUCTURE_PNL, f"no chain outcomes for {wanted[0]}..{wanted[-1]}", hint)


def read_chain_stored(
    reader: StoreReader, sessions: Sequence[date], as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The stored rows of the start ``sessions``' partitions, every position key and hold, one
    source per session (None: none stored)."""
    wanted = sorted(set(sessions))
    stored = set(reader.dates(STRUCTURE_PNL))
    read = [reader.table(STRUCTURE_PNL, d, as_of) for d in wanted if d in stored]
    kept = [one_source(p) for p in read if p is not None and not p.empty]
    parts = [p for p in kept if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else None


def select_chain(
    frame: pd.DataFrame, horizon: int, sessions: Sequence[date], as_of: datetime | None = None
) -> pd.DataFrame:
    """The ``horizon`` rows of ``frame`` for the start ``sessions`` in the shape of the price
    outcomes (``CHAIN_COLUMNS`` and the keys): the return fields empty, ``benchmark`` ``none``."""
    frame = frame.rename(columns={"hold_sessions": "horizon_sessions"})
    starts = pd.to_datetime(frame["session_date"]).dt.date
    keep = starts.isin(set(sessions)) & (frame["horizon_sessions"] == horizon)
    if as_of is not None:
        keep &= pd.to_datetime(frame["knowledge_ts"], utc=True) <= pd.Timestamp(as_of)
    out = frame.loc[keep].copy()
    for column in ("fwd_return", "fwd_excess_return", "fwd_max_return", "fwd_max_drawdown",
                   "fwd_realised_vol"):  # fmt: skip
        out[column] = np.nan
    out["benchmark"] = "none"
    for nullable in ("outcome_reason", "exit_session", "exit_kind", "collateral", "max_adverse"):
        # a column no row of the partitions set (an all-UNMEASURED set has no exit)
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
    table = STRUCTURE_PNL if chain else FORWARD_RETURNS
    if spec_for(table).column("licence") is None:
        return []
    days = sorted(set(sessions))
    if not days:
        return []
    columns = ("licence", "price_source") if chain else ("licence",)
    found = reader.table_range(table, days[0], days[-1], as_of, columns=columns)
    if found is not None and chain:
        found = one_source(found)
    return [] if found is None or found.empty else [found]
