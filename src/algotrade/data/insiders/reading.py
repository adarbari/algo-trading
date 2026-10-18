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
``amends_date`` drop out of the result, and so does an earlier 4/A of the same report and
``amends_date`` once a later one (by acceptance) is known: amended shares count once.
(Two Form 4s of one owner, issuer and period filed on the same day are one original here: a
4/A naming that day replaces both, the conservative reading.)
A 4/A with no ``amends_date`` replaces nothing.

``buyer_histories`` hands the feature group ``insider_buys@v1`` the owners with a recent purchase
and their open-market history, one point-in-time view per session.

``ts`` is the acceptance instant (UTC). The columns are the table's; the roles, the transaction
code (``P`` open-market purchase, ``S`` sale, ...) and the 10b5-1 flag are the caller's to
interpret.
"""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.data.events import ALL_TIME
from algotrade.storage.tables.readers import StoreReader

TABLE = "events/insider_transaction"
LINE_KEY = ["instrument_id", "accession", "line", "owner_cik"]
REPORT_KEY = ["instrument_id", "owner_cik", "period_of_report"]


def _superseded(frame: pd.DataFrame) -> pd.Series:
    """Which rows a known 4/A replaces (module doc): the originals it names, and any earlier 4/A
    of the same report and original filing date (a later amendment restates the earlier one)."""
    amended = (frame["form"] == "4/A") & frame["amends_date"].notna()
    if not amended.any():
        return pd.Series(False, index=frame.index)

    def keys(rows: pd.DataFrame, filed: str) -> pd.MultiIndex:
        columns = [rows[c].astype(str) for c in REPORT_KEY]
        return pd.MultiIndex.from_arrays([*columns, pd.to_datetime(rows[filed]).dt.strftime("%F")])

    amendments = frame[amended]
    original = (frame["form"] == "4") & keys(frame, "filing_date").isin(
        keys(amendments, "amends_date")
    )
    latest = (
        amendments.assign(
            _key=list(keys(amendments, "amends_date")),
            _ts=pd.to_datetime(amendments["ts"], utc=True),
        )
        .groupby("_key")["_ts"]
        .transform("max")
    )
    older = pd.Series(False, index=frame.index)
    older[amendments.index] = (pd.to_datetime(amendments["ts"], utc=True) < latest).to_numpy()
    return pd.Series(original.to_numpy() | older.to_numpy(), index=frame.index)


def known_lines(frame: pd.DataFrame, through: date | None) -> pd.DataFrame:
    """The lines of the raw ``frame`` known on or before ``through`` (None: all), each line's
    latest version, without the originals a known 4/A replaced (module doc), sorted by
    (``instrument_id``, ``ts``, ``accession``, ``line``, ``owner_cik``)."""
    if through is not None:
        frame = frame[pd.to_datetime(frame["known_from"]) <= pd.Timestamp(through)]
    frame = frame.sort_values(["known_from", "knowledge_ts"], kind="stable")
    frame = frame.drop_duplicates(LINE_KEY, keep="last").reset_index(drop=True)
    frame = frame[~_superseded(frame)]
    order = ["instrument_id", "ts", "accession", "line", "owner_cik"]
    return frame.sort_values(order, kind="stable").reset_index(drop=True)


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
    return known_lines(frame, through)


BUY_WINDOW_DAYS = 30  # calendar days of known_from a purchase counts as recent (the cluster window)
HISTORY_COLUMNS = [
    "instrument_id", "owner_cik", "transaction_date", "transaction_code", "derivative",
    "plan_10b5_1", "known_from",
]  # fmt: skip
OPEN_MARKET = ("P", "S")  # an open-market purchase or sale (Form 4 transaction codes)


def buyer_histories(reader: StoreReader, sessions: Sequence[date]) -> pd.DataFrame:
    """For each session, the open-market history of the owners who bought lately: every
    non-derivative open-market line (code P or S) known by that session of each (issuer, owner)
    with a purchase known within ``BUY_WINDOW_DAYS`` calendar days up to it, with ``as_of`` the
    session. Each session is read as the one rule says (``known_lines``: a restated line shows its
    old version until its own ``known_from``), so a backfill sees what each night saw. Empty
    (``HISTORY_COLUMNS`` + ``as_of``) when nothing is stored or nobody bought."""
    empty = pd.DataFrame(columns=[*HISTORY_COLUMNS, "as_of"])
    raw = reader.table_range(TABLE, *ALL_TIME, None, None)
    if raw is None or raw.empty:
        return empty
    parts = []
    for session in sessions:
        lines = known_lines(raw, session)
        lines = lines[(lines["transaction_code"].isin(OPEN_MARKET)) & ~lines["derivative"]]
        recent = pd.to_datetime(lines["known_from"]) > pd.Timestamp(session) - pd.Timedelta(
            days=BUY_WINDOW_DAYS
        )
        buyers = lines.loc[
            recent & (lines["transaction_code"] == "P"), ["instrument_id", "owner_cik"]
        ]
        if buyers.empty:
            continue
        kept = lines.merge(buyers.drop_duplicates(), on=["instrument_id", "owner_cik"])
        parts.append(kept[HISTORY_COLUMNS].assign(as_of=session))
    return pd.concat(parts, ignore_index=True) if parts else empty
