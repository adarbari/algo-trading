"""Turn the difference between two reference snapshots into events (ADR 0016).

- ``events/reference_change``: ``added``, ``removed`` (no longer listed), ``renamed``,
  ``type_changed``, ``optionable_changed``, ``exchange_changed``
- ``events/index_change``: ``sp500_added`` / ``sp500_removed``
"""

from datetime import date

import pandas as pd

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
