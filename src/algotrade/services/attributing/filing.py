"""Attribute a big move from the 8-K filed for its reaction session (ADR 0050 decision 5, no model).

A filing accepted before the open or during the day of session S, or after the close of the session
before it, is the first news S's trading could price: the data layer's acceptance session
(``events_by_acceptance``'s ``event_date``) is S exactly then. For a mover with such a filing the
item codes name the cause (``taxonomy.ITEM_CLASS``): one class gives confidence 0.9, several 0.7
(the most specific by ``PRIORITY`` is the row's class, the others are in its text). A filing with no
item that names a cause (an exhibit alone) gives no row. ``known_from`` is the reaction session: the
filing was public from it, so a past session sees what it could have seen (a backfill is not
hindsight). One row per (instrument, session): a mover with several qualifying filings takes the
one with the highest class, then the latest accepted.
"""

from datetime import date

import pandas as pd

from algotrade.services.attributing import taxonomy

COLUMNS = (
    "instrument_id",
    "ts",
    "known_from",
    "cause_class",
    "cause_text",
    "confidence",
    "evidence",
    "evidence_ref",
)
SINGLE, MIXED = 0.9, 0.7  # confidence of one cause class / several


def _classes(items: object) -> list[str]:
    """The cause classes of an SEC items list ("2.02,9.01"), most specific first, no repeats."""
    codes = [c.strip() for c in str(items or "").split(",") if c.strip()]
    found = {taxonomy.ITEM_CLASS[c] for c in codes if c in taxonomy.ITEM_CLASS}
    return [c for c in taxonomy.PRIORITY if c in found]


def attribute_from_filings(
    movers: set[str], filings: pd.DataFrame | None, session: date
) -> pd.DataFrame:
    """The ``COLUMNS`` rows of the ``movers`` (instrument ids that moved big on ``session``) that
    have an 8-K whose acceptance session is ``session`` (``filings``: ``instrument_id``, ``items``,
    ``accession``, ``ts``, ``event_date``, the 8-K rows of ``events/filing``)."""
    if filings is None or filings.empty or not movers:
        return pd.DataFrame(columns=list(COLUMNS))
    mine = filings[filings["instrument_id"].isin(movers)]
    mine = mine[pd.to_datetime(mine["event_date"]).dt.date == session]
    rows = []
    for _, f in mine.sort_values("ts", kind="stable").iterrows():
        classes = _classes(f.get("items"))
        if not classes:
            continue
        rows.append(
            {
                "instrument_id": str(f["instrument_id"]),
                "ts": pd.Timestamp(session, tz="UTC"),
                "known_from": session,
                "cause_class": classes[0],
                "cause_text": f"8-K items {f.get('items')}"
                + (f" (also {', '.join(classes[1:])})" if len(classes) > 1 else ""),
                "confidence": SINGLE if len(classes) == 1 else MIXED,
                "evidence": f"8-K accepted {pd.Timestamp(f['ts']).isoformat()}, "
                f"items {f.get('items')}",
                "evidence_ref": str(f.get("accession") or ""),
            }
        )
    if not rows:
        return pd.DataFrame(columns=list(COLUMNS))
    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    rank = {c: i for i, c in enumerate(taxonomy.PRIORITY)}
    frame["_rank"] = frame["cause_class"].map(rank)
    best = frame.sort_values(["instrument_id", "_rank"], kind="stable").drop_duplicates(
        "instrument_id", keep="first"
    )
    return best.drop(columns="_rank").reset_index(drop=True)
