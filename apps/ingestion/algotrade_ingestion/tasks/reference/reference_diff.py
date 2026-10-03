"""Turn the difference between two reference snapshots into events (ADR 0016).

- ``events/reference_change``: ``added``, ``removed`` (no longer listed), ``renamed``,
  ``type_changed``, ``optionable_changed``, ``exchange_changed``
- ``events/index_change``: ``sp500_added`` / ``sp500_removed``
- ``id_changed`` rows from the session's ``instruments/id_map`` upgrades (``id_change_rows``)

**One event per table key** (``instrument_id``, ``ts``, ``change``; the table rejects a run
holding two). The id map may hold several changes *into* one id on a session: 2026-10-02,
DFAC was upgraded ``EQ:DFAC -> EQ:BBG011DXY5J0`` at 05:05Z, a later run followed a vendor
flip to ``EQ:BBG0132J6C32``, and the owner's override moved it back
(``EQ:BBG0132J6C32 -> EQ:BBG011DXY5J0``). That is one instrument changing id once on the
session, so ``id_change_rows`` merges such rows into one event: ``old`` is the id it held
before the session's first recorded change into the id (earliest ``known_at``), ``new`` the
id; the intermediate ids stay in ``id_map`` for ``migrate-ids``. ``one_per_key`` is the last
guard: with ``STRICT`` (tests) a duplicate raises; otherwise it keeps one row per key
deterministically and the build reports the count in its run stats.
"""

from datetime import date

import pandas as pd

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.tables.schemas import spec_for, table_key

REFERENCE_CHANGE = "events/reference_change"
# Tests turn this on (tests/conftest.py): a duplicate event is a bug to fix, not to hide.
STRICT = False

_TRACKED = {
    "name": "renamed",
    "security_type": "type_changed",
    "optionable": "optionable_changed",
    "exchange": "exchange_changed",
}


def _row(iid: object, symbol: object, change: str, old: object, new: object) -> dict[str, object]:
    return {
        "instrument_id": iid,
        "symbol": symbol,
        "change": change,
        "old": None if old is None else str(old),
        "new": None if new is None else str(new),
    }


def diff_reference(
    previous: pd.DataFrame | None, current: pd.DataFrame, session: date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (reference_change rows, index_change rows), each with a UTC ``ts`` at the session."""
    ts = pd.Timestamp(session, tz="UTC")
    changes: list[dict[str, object]] = []
    index: list[dict[str, object]] = []
    cur = current.set_index("instrument_id")
    active_now = set(cur.index[cur["status"] == "ACTIVE"])
    if previous is None:
        changes = [
            _row(i, cur.at[i, "symbol"], "added", None, cur.at[i, "name"])
            for i in sorted(active_now)
        ]
    else:
        prev = previous.set_index("instrument_id")
        active_before = set(prev.index[prev["status"] == "ACTIVE"])
        for iid in sorted(active_now - active_before):
            changes.append(_row(iid, cur.at[iid, "symbol"], "added", None, cur.at[iid, "name"]))
        for iid in sorted(active_before - active_now):
            changes.append(_row(iid, prev.at[iid, "symbol"], "removed", prev.at[iid, "name"], None))
        for iid in sorted(active_now & active_before):
            for column, change in _TRACKED.items():
                old, new = prev.at[iid, column], cur.at[iid, column]
                if column in prev.columns and str(old) != str(new):
                    changes.append(_row(iid, cur.at[iid, "symbol"], change, old, new))
        before = set(
            prev.index[
                prev.get("in_sp500", pd.Series(False, index=prev.index)).fillna(False).astype(bool)
            ]
        )
        now = set(cur.index[cur["in_sp500"].fillna(False).astype(bool)])
        index = [
            _row(i, cur.at[i, "symbol"], "sp500_added", None, "S&P 500")
            for i in sorted(now - before)
        ]
        index += [
            _row(i, prev.at[i, "symbol"], "sp500_removed", "S&P 500", None)
            for i in sorted(before - now)
        ]
    columns = ["instrument_id", "symbol", "change", "old", "new"]
    out = [pd.DataFrame(rows, columns=columns).assign(ts=ts) for rows in (changes, index)]
    return out[0], out[1]


def id_change_rows(upgrades: pd.DataFrame, session: date) -> pd.DataFrame:
    """One ``id_changed`` event per new id among the session's id-map rows (``upgrades``:
    ``old_id``, ``new_id``, ``symbol``, ``known_at``). Several rows into one id merge: ``old``
    from the earliest known row (ties: smallest ``old_id``), ``symbol`` from the latest."""
    columns = ["instrument_id", "symbol", "change", "old", "new", "ts"]
    if upgrades.empty:
        return pd.DataFrame(columns=columns)
    known = pd.to_datetime(upgrades["known_at"], utc=True)
    ordered = upgrades.assign(_known=known).sort_values(
        ["new_id", "_known", "old_id"], kind="stable", na_position="last"
    )
    rows = [
        _row(new_id, group["symbol"].iloc[-1], "id_changed", group["old_id"].iloc[0], new_id)
        for new_id, group in ordered.groupby("new_id", sort=True)
    ]
    return pd.DataFrame(rows).assign(ts=pd.Timestamp(session, tz="UTC"))[columns]


def one_per_key(changes: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """-> (``changes`` with one row per table key, rows dropped). Raises with ``STRICT``.
    Otherwise the first row per key in (key, ``old``, ``new``, ``symbol``) order is kept."""
    key = table_key(spec_for(REFERENCE_CHANGE), changes.columns)
    duplicated = changes.duplicated(key, keep=False)
    if not duplicated.any():
        return changes, 0
    if STRICT:
        clash = changes[duplicated].sort_values(key).to_dict("records")
        raise DataValidationError(REFERENCE_CHANGE, [f"two events for one key: {clash}"])
    order = [*key, "old", "new", "symbol"]
    kept = changes.sort_values(order, kind="stable", na_position="last").drop_duplicates(key)
    return kept.sort_index().reset_index(drop=True), len(changes) - len(kept)
