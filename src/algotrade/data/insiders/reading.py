"""Insider transactions (``events/insider_transaction``, EB D6) as a session may see them.

A row is a Form 4 line of one reporting owner (``instrument_id``, ``accession``, ``line``,
``owner_cik``) with ``known_from``, the trading session its filing was public on (the
``calendar.acceptance_session`` of SEC's acceptance time; for a line restated with different
content, no earlier than the fetch's next session: ``tasks/events/insider_rows.py``). The one
read rule of ADR 0050 decision 3 applies first: keep the rows with ``known_from <= S``
(``through``). Then, per line, the version with the latest ``known_from`` (ties: the latest
``knowledge_ts``): a restated line shows its old version until its own ``known_from`` and its
new one after, never the new one early.

**Amendments.** A 4/A replaces the originals it names, once the 4/A itself is known: the rows of
form ``4`` with the same issuer, owner and report period and a ``filing_date`` equal to the 4/A's
``amends_date`` drop out of the result. (Two Form 4s of one owner, issuer and period filed on the
same day are one original here: a 4/A naming that day replaces both, the conservative reading.)
A 4/A with no ``amends_date`` replaces nothing.

``ts`` is the acceptance instant (UTC). The columns are the table's; the roles, the transaction
code (``P`` open-market purchase, ``S`` sale, ...) and the 10b5-1 flag are the caller's to
interpret.
"""

from datetime import date, datetime

import pandas as pd

from algotrade.data.events import ALL_TIME
from algotrade.storage.tables.readers import StoreReader

TABLE = "events/insider_transaction"
LINE_KEY = ["instrument_id", "accession", "line", "owner_cik"]
REPORT_KEY = ["instrument_id", "owner_cik", "period_of_report"]


def _superseded(frame: pd.DataFrame) -> pd.Series:
    """Which rows of form ``4`` a known 4/A replaces (module doc)."""
    amendments = frame[(frame["form"] == "4/A") & frame["amends_date"].notna()]
    originals = frame["form"] == "4"
    if amendments.empty or not originals.any():
        return pd.Series(False, index=frame.index)

    def keys(rows: pd.DataFrame, filed: str) -> pd.MultiIndex:
        columns = [rows[c].astype(str) for c in REPORT_KEY]
        return pd.MultiIndex.from_arrays([*columns, pd.to_datetime(rows[filed]).dt.strftime("%F")])

    hit = keys(frame, "filing_date").isin(keys(amendments, "amends_date"))
    return pd.Series(hit & originals.to_numpy(), index=frame.index)


def read_insider_transactions(
    reader: StoreReader,
    instruments: list[str] | None = None,
    through: date | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The insider transaction lines known on or before ``through`` (None: every row), the latest
    version of each, without the originals a known 4/A replaced, sorted by (``instrument_id``,
    ``ts``, ``accession``, ``line``, ``owner_cik``). Empty (no columns guaranteed) when nothing
    is stored."""
    frame = reader.table_range(TABLE, *ALL_TIME, as_of, instruments)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=[*LINE_KEY, "known_from"])
    if through is not None:
        frame = frame[pd.to_datetime(frame["known_from"]) <= pd.Timestamp(through)]
    frame = frame.sort_values(["known_from", "knowledge_ts"], kind="stable")
    frame = frame.drop_duplicates(LINE_KEY, keep="last").reset_index(drop=True)
    frame = frame[~_superseded(frame)]
    order = ["instrument_id", "ts", "accession", "line", "owner_cik"]
    return frame.sort_values(order, kind="stable").reset_index(drop=True)
