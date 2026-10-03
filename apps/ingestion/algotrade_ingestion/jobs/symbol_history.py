"""``instruments/symbol_history``: which symbol each FIGI has used, and when (ADR 0016).

A FIGI identifies the security itself, so it survives ticker changes (FB -> META) and ticker
reuse. Each universe build carries the history forward:

- same FIGI, same symbol      -> the open row stays open
- same FIGI, new symbol       -> close the old row, open a new one, emit ``ticker_changed``
- FIGI no longer listed       -> close its row
- new FIGI                    -> open a row

This is the groundwork for FIGI-based instrument ids (roadmap); today instrument ids are
still ``EQ:<symbol>``.
"""

from datetime import date

import pandas as pd

COLUMNS = ["instrument_id", "ts", "figi", "symbol", "valid_from", "valid_to"]


def update_history(
    previous: pd.DataFrame | None, reference: pd.DataFrame, session: date
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """-> (full history as of ``session``, ``ticker_changed`` reference-change rows)."""
    active = reference[reference["status"].eq("ACTIVE") & reference["figi"].notna()]
    current = dict(zip(active["figi"], active["symbol"], strict=True))
    rows: list[dict[str, object]] = []
    changes: list[dict[str, object]] = []
    seen: set[str] = set()
    if previous is not None and not previous.empty:
        for r in previous.to_dict("records"):
            row = {c: r.get(c) for c in COLUMNS}
            figi = str(row["figi"])
            still_open = row["valid_to"] is None or pd.isna(row["valid_to"])
            if still_open:
                seen.add(figi)
                symbol = current.get(figi)
                if symbol != row["symbol"]:
                    row["valid_to"] = session
                    if symbol is not None:
                        changes.append(
                            {
                                "instrument_id": f"EQ:{symbol}",
                                "symbol": symbol,
                                "change": "ticker_changed",
                                "old": row["symbol"],
                                "new": symbol,
                            }
                        )
                        rows.append(_open(figi, symbol, session))
            rows.append(row)
    rows.extend(
        _open(figi, symbol, session) for figi, symbol in current.items() if figi not in seen
    )
    history = pd.DataFrame(rows, columns=COLUMNS)
    return history.sort_values(["figi", "valid_from"]).reset_index(drop=True), changes


def _open(figi: str, symbol: str, session: date) -> dict[str, object]:
    return {
        "instrument_id": f"EQ:{symbol}",
        "ts": pd.Timestamp(session, tz="UTC"),
        "figi": figi,
        "symbol": symbol,
        "valid_from": session,
        "valid_to": None,
    }
