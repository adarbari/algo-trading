"""Read share path outcomes (``outcomes/instrument/share_path@v1``, written by the ingestion
``share-outcomes`` task; ADR 0088, E3c-2) for the start sessions a harness evaluates: one row per
(name, start session S, ``position_key``, benchmark) of a share setup that declares an
``[outcome.exit]``. The frames carry the columns of the price outcomes (``OUTCOME_FIELDS``) beside
``SHARE_FIELDS``, the stored ``hold_sessions`` read as ``horizon_sessions``, so the harness reads
every grain through one path (``grains.py``).

Every read takes the run's ``keys``, the (``position_key``, benchmark) of its setups, and drops any
other row at read time: a partition holds every setup's keys at the same hold, so another setup's
row must never make S look closed for this one (a missing own row waits or is excluded with its
reason, the fixed-horizon rows are never read in its place). A window not closed has no row; an
``UNMEASURED`` row (``outcome_reason``) has no return and is excluded by the caller, never counted
a miss. ``as_of`` keeps only rows known by then (row by row); a row's ``knowledge_ts`` is its
exit's.

The price fields are mapped so the stock grain's code reads the rows unchanged: ``fwd_return`` is
the underlying's return to the exit (long-oriented, as the stock grain's; a short's sign and
borrow are applied by the caller, never read from ``gross_return``), ``fwd_excess_return`` that
less the benchmark's over the same sessions, ``fwd_max_drawdown`` the dip to the exit at closes
(null for a short); the favourable excursion and the realised vol are not stored (NaN).
"""

from collections.abc import Collection, Iterable, Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.outcomes.reading import OUTCOME_FIELDS
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import SHARE_PATH

SHARE_FIELDS = (
    "position_key", "exit_session", "exit_index", "exit_kind", "gross_return", "max_adverse",
    "exit_unknown_closes", "licence",
)  # fmt: skip
SHARE_COLUMNS = ("instrument_id", "horizon_sessions", "benchmark", *OUTCOME_FIELDS, *SHARE_FIELDS)
_KEY = ("instrument_id", "session_date", "horizon_sessions", "benchmark", "window_end")
_NULLABLE = (
    "outcome_reason", "exit_session", "exit_index", "exit_kind", "gross_return", "max_adverse",
    "underlying_return", "benchmark_return",
)  # a column no row of the partitions set (an all-UNMEASURED set has no exit)  # fmt: skip

ShareKeys = Collection[tuple[str, str]]  # (position_key, benchmark) of the run's setups


def own_rows(frame: pd.DataFrame, keys: ShareKeys) -> pd.DataFrame:
    """The rows of ``frame`` (``position_key`` and ``benchmark`` columns) of the run's ``keys``."""
    if frame.empty:
        return frame
    pairs = pd.MultiIndex.from_arrays(
        [frame["position_key"].astype(str), frame["benchmark"].astype(str)]
    )
    return frame[pairs.isin(set(keys))]


def share_path_sessions(reader: StoreReader) -> list[date]:
    """The start sessions with a stored share path partition, ascending."""
    return list(reader.dates(SHARE_PATH))


def share_path_seqs(reader: StoreReader, sessions: Iterable[date]) -> dict[date, int]:
    """The commit sequence of each start session's committed share path partition (those of
    ``sessions`` that exist), read before the rows so a later commit changes it (ADR 0063)."""
    wanted = sorted(set(sessions))
    if not wanted:
        return {}
    found = reader.partition_seq(SHARE_PATH, wanted[0], wanted[-1])
    return {d: s for d, s in found.items() if d in set(wanted)}


def share_path_stamps(
    reader: StoreReader,
    sessions: Iterable[date],
    as_of: datetime,
    keys: ShareKeys,
    names_for: Iterable[int] = (),
) -> tuple[dict[tuple[date, int], datetime], dict[tuple[date, int], frozenset[str]]]:
    """Per (start session, horizon) of ``sessions`` with a row of ``keys`` known by ``as_of``: the
    latest ``knowledge_ts`` among them and, for the horizons in ``names_for``, the instrument
    ids. Another setup's rows are not counted."""
    wanted_names = set(names_for)
    latest: dict[tuple[date, int], datetime] = {}
    names: dict[tuple[date, int], set[str]] = {}
    for day in sorted(set(sessions)):
        frame = reader.table_range(
            SHARE_PATH, day, day, as_of,
            columns=("instrument_id", "hold_sessions", "position_key", "benchmark"),
        )  # fmt: skip
        if frame is None:
            continue
        frame = own_rows(frame, keys)
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


def missing_share_path(sessions: Sequence[date]) -> MissingDataError:
    """The error of start ``sessions`` none of which has a stored share path outcome."""
    wanted = sorted(set(sessions))
    hint = f"run `algotrade-ingest run share-outcomes --from ... --to ...` past {wanted[-1]}"
    return MissingDataError(
        SHARE_PATH, f"no share path outcomes for {wanted[0]}..{wanted[-1]}", hint
    )


def read_share_path_stored(
    reader: StoreReader, sessions: Sequence[date], keys: ShareKeys, as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The stored rows of the start ``sessions``' partitions, of ``keys`` only, every hold (None:
    none stored)."""
    wanted = sorted(set(sessions))
    stored = set(reader.dates(SHARE_PATH))
    read = [reader.table(SHARE_PATH, d, as_of) for d in wanted if d in stored]
    kept = [own_rows(p, keys) for p in read if p is not None and not p.empty]
    parts = [p for p in kept if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else None


def select_share_path(
    frame: pd.DataFrame, horizon: int, sessions: Sequence[date], as_of: datetime | None = None
) -> pd.DataFrame:
    """The ``horizon`` rows of ``frame`` for the start ``sessions`` in the shape of the price
    outcomes (``SHARE_COLUMNS`` and the keys), the return fields mapped as the module doc says."""
    frame = frame.rename(columns={"hold_sessions": "horizon_sessions"})
    starts = pd.to_datetime(frame["session_date"]).dt.date
    keep = starts.isin(set(sessions)) & (frame["horizon_sessions"] == horizon)
    if as_of is not None:
        keep &= pd.to_datetime(frame["knowledge_ts"], utc=True) <= pd.Timestamp(as_of)
    out = frame.loc[keep].copy()
    for column in _NULLABLE:
        if column not in out.columns:
            out[column] = np.nan if column.endswith(("return", "adverse", "index")) else None
    underlying = pd.to_numeric(out["underlying_return"], errors="coerce")
    benchmark = pd.to_numeric(out["benchmark_return"], errors="coerce")
    out["fwd_return"] = underlying
    out["fwd_excess_return"] = underlying - benchmark
    out["fwd_max_drawdown"] = pd.to_numeric(out["max_adverse"], errors="coerce")
    out["fwd_max_return"] = np.nan
    out["fwd_realised_vol"] = np.nan
    kept = out[[*_KEY, *OUTCOME_FIELDS, *SHARE_FIELDS, "knowledge_ts"]]
    return kept.sort_values(["session_date", "instrument_id"], kind="stable").reset_index(drop=True)


def read_share_path(
    reader: StoreReader,
    horizon: int,
    sessions: Sequence[date],
    keys: ShareKeys,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The ``horizon``-session share path outcomes of ``keys`` for the start ``sessions``
    (``select_share_path``'s columns). Raises ``MissingDataError`` when none is stored."""
    wanted = sorted(set(sessions))
    frame = read_share_path_stored(reader, wanted, keys, as_of) if wanted else None
    if frame is None:
        raise missing_share_path(wanted or [date.min])
    return select_share_path(frame, horizon, wanted, as_of)


def share_path_licences(
    reader: StoreReader, sessions: Iterable[date], keys: ShareKeys, as_of: datetime | None = None
) -> list[pd.DataFrame]:
    """The ``licence`` column of the run's ``keys`` over the span of the start ``sessions`` (one
    narrow read; the span is stricter than the sessions alone), as ``chain.licence_frames``: the
    harness folds it into the trial's licence, a stored leg it reuses included."""
    days = sorted(set(sessions))
    if not days:
        return []
    found = reader.table_range(
        SHARE_PATH, days[0], days[-1], as_of, columns=("licence", "position_key", "benchmark")
    )
    if found is None:
        return []
    found = own_rows(found, keys)
    return [] if found.empty else [found]
