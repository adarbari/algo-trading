"""``instruments/symbol_history``: which symbol each FIGI has used, and when (ADR 0016).

A FIGI identifies the security itself, so it survives ticker changes (FB -> META) and ticker
reuse. Each universe build carries the history forward:

- same FIGI, same symbol      -> the open row stays open
- same FIGI, new symbol       -> close the old row, open a new one, emit ``ticker_changed``
- FIGI no longer listed       -> close its row
- new FIGI                    -> open a row

**One row per key** (``figi``, ``symbol``, ``valid_from``; the table merges its runs on it,
ADR 0007). Re-runs of a session start from the earlier run's history, so a FIGI that flips
A -> B -> A within the session (2026-10-02: DFAC's vendor FIGI) finds its own row closed
*today*. Re-listing a (FIGI, symbol) whose row was closed on ``session`` therefore reopens
that row (``valid_to`` back to null) instead of opening a second one under the same key.
As a last guard the output keeps one row per key: this build's decision for the key wins
(an open row made now over a carried row; otherwise the later row).

``instrument_id`` is the instrument's id in the reference (``EQ:<FIGI>``, ADR 0018); rows of
FIGIs no longer listed keep the id they had. Only the listing that **holds** a FIGI's id has
an open row: when several listings share a FIGI (MMED / MMEDV, 2026-10-02), the ones that
kept symbol ids are not in the history (a row opened for one earlier is closed, no event).
"""

from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.instruments import is_figi_id

COLUMNS = ["instrument_id", "ts", "figi", "symbol", "valid_from", "valid_to"]
KEY = ["figi", "symbol", "valid_from"]
Row = dict[str, Any]


def _is_open(row: Row) -> bool:
    return row["valid_to"] is None or bool(pd.isna(row["valid_to"]))


def update_history(
    previous: pd.DataFrame | None, reference: pd.DataFrame, session: date
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """-> (full history as of ``session``, ``ticker_changed`` reference-change rows)."""
    with_figi = reference[reference["status"].eq("ACTIVE") & reference["figi"].notna()]
    pairs = zip(with_figi["instrument_id"], with_figi["figi"], strict=True)
    holds = pd.Series([is_figi_id(str(i), str(f)) for i, f in pairs], with_figi.index, bool)
    active = with_figi[holds]
    # A listing of a shared FIGI that kept its symbol id: a row a build opened for it before
    # (the FIGI's last listing used to win) is closed without a ``ticker_changed`` event.
    losers = {(str(f), s) for f, s in zip(with_figi["figi"], with_figi["symbol"], strict=True)}
    losers -= set(zip(active["figi"].astype(str), active["symbol"], strict=True))
    current = dict(zip(active["figi"], active["symbol"], strict=True))
    ids = dict(zip(active["figi"], active["instrument_id"], strict=True))
    carried: list[Row] = []
    changes: list[dict[str, object]] = []
    if previous is not None and not previous.empty:
        for r in previous.to_dict("records"):
            row = {c: r.get(c) for c in COLUMNS}
            figi = str(row["figi"])
            row["instrument_id"] = ids.get(figi, row["instrument_id"])
            if _is_open(row) and current.get(figi) != row["symbol"]:
                row["valid_to"] = session
                symbol = current.get(figi)
                if symbol is not None and (figi, row["symbol"]) not in losers:
                    changes.append(
                        {
                            "instrument_id": ids[figi],
                            "symbol": symbol,
                            "change": "ticker_changed",
                            "old": row["symbol"],
                            "new": symbol,
                        }
                    )
            carried.append(row)
    listed = {(str(r["figi"]), r["symbol"]) for r in carried if _is_open(r)}
    closed_today = {
        (str(r["figi"]), r["symbol"]): n
        for n, r in sorted(enumerate(carried), key=lambda p: str(p[1]["valid_from"]))
        if not _is_open(r) and pd.Timestamp(str(r["valid_to"])).date() == session
    }  # the latest valid_from wins when a pair has several
    opened: list[Row] = []
    for figi, symbol in current.items():
        if (figi, symbol) in listed:
            continue
        if (figi, symbol) in closed_today:  # closed earlier this session: reopen it
            carried[closed_today[figi, symbol]]["valid_to"] = None
        else:
            opened.append(_open(ids[figi], figi, symbol, session))
    return _one_per_key(pd.DataFrame(carried + opened, columns=COLUMNS)), changes


def _one_per_key(history: pd.DataFrame) -> pd.DataFrame:
    """One row per ``KEY``: rows made by this build come last, so the last row wins."""
    unique = history.drop_duplicates(KEY, keep="last")
    return unique.sort_values(["figi", "valid_from", "symbol"]).reset_index(drop=True)


def _open(instrument: str, figi: str, symbol: str, session: date) -> dict[str, object]:
    return {
        "instrument_id": instrument,
        "ts": pd.Timestamp(session, tz="UTC"),
        "figi": figi,
        "symbol": symbol,
        "valid_from": session,
        "valid_to": None,
    }
