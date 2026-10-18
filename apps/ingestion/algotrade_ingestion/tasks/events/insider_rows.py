"""The rows of ``events/insider_transaction``: what makes a Form 4 line a stored row (EB D6) -
its id, its ``known_from`` and its place beside a stored version. Pure functions over frames;
``insider.py`` fetches and stages.

**known_from** (ADR 0050 decision 3 and its amendment of EB H4; one rule with ``events/filing``):
``calendar.acceptance_session`` of SEC's acceptance time: the first session whose CLOSE is
strictly after it. A Form 4 accepted before the close counts from that session; one accepted at
or after 16:00 New York time (EDGAR takes filings until 22:00), on a weekend or on a holiday
counts from the next session, so a reader of session S never sees a filing made public after S's
close (a 16:30 acceptance on S is known from S+1). ``known_from`` is always a trading session.
The acceptance time is SEC's own (the submissions JSON), never the time we fetched it: a 2012
filing backfilled in 2026 is known from 2012.

**Restatements.** A line (key) we already stored that is fetched again with DIFFERENT content is
known no earlier than the fetch allows: ``max(own acceptance session, FLOOR)`` with ``FLOOR`` the
session after the fetch's (``next_session(exchange_date(run.clock()))``, the run's own session,
never a ``--to``), so a reader of a past session keeps the version it would have seen. The same
line with the same content keeps its stored ``known_from`` (a rerun changes nothing; nor does a
re-extraction that only adds or respells ``owner_name``, which is no restated fact). A 4/A is
its own filing with its own keys: it is known from its own acceptance session, and the reader
(``data.insiders``) drops the original it names from then on. Stored means before this run.

**One source per accession.** The bulk sets and the XML give the same lines, but a difference in
how either is read could key one transaction twice and double-count it. Each row's ``source`` is
the dataset it came from (``form345_bulk`` / ``form4_xml``); an accession already stored by the
other source is skipped and counted (``other_source``).

**Ids**: the issuer's ticker in the filing (the first of several that resolves) to an
``instrument_id`` through the listing history AS OF THE FILING DATE
(``SymbolResolver.from_listings``): a recycled ticker is two ids by date, and a delisted issuer
keeps its own. A ticker no listing of that date carries is dropped and counted, never
resolved to today's holder or to ``EQ:<SYMBOL>``.
"""

import re
from collections.abc import Callable
from datetime import date, datetime

import pandas as pd

from algotrade.core.time.calendar import exchange_date, next_session
from algotrade.data.events import acceptance_sessions
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.tables.schemas import INSIDER_EVENTS

TABLE = "events/insider_transaction"  # the table this module's rows go to (tables.toml)
LINE_KEY = ["instrument_id", "accession", "line", "owner_cik"]
COLUMNS = [c.name for c in INSIDER_EVENTS.columns if c.name not in (
    "session_date", "knowledge_ts", "source", "run_id")]  # fmt: skip
KEY_COLUMNS = [*LINE_KEY, "known_from", "filing_date"]  # all the nightly needs of what is stored
NOT_CONTENT = (*LINE_KEY, "known_from", "owner_name")  # owner_name: a spelling, not a restated fact
CONTENT = [c for c in COLUMNS if c not in NOT_CONTENT]  # what a restatement changes
SYMBOL_SEPARATORS = re.compile(r"[,;/\s]+")


def known_session(ts: pd.Series) -> pd.Series:
    """The ``known_from`` of each acceptance instant (UTC): ``acceptance_session`` (module doc)."""
    return acceptance_sessions(ts)


def restatement_floor(now: datetime) -> date:
    """The earliest ``known_from`` of a row that replaces a stored one: the session after the
    New York date of ``now`` (the fetch's clock)."""
    return next_session(exchange_date(now))


def symbol_candidates(symbol: object) -> list[str]:
    """The tickers a filing's ``issuerTradingSymbol`` may mean, in order: each listed symbol,
    as written and in the other class-share style (``BRK-B`` / ``BRK.B``)."""
    out: list[str] = []
    for token in SYMBOL_SEPARATORS.split(str(symbol or "").strip().upper()):
        if token and token != "NONE":
            out += [token, token.replace("-", "."), token.replace(".", "-")]
    return list(dict.fromkeys(out))


def resolve_ids(
    rows: pd.DataFrame, resolver_on: Callable[[date], SymbolResolver]
) -> tuple[pd.DataFrame, int]:
    """``rows`` with ``instrument_id`` from each row's ``issuer_symbol`` as of its ``filing_date``
    (module doc) -> (the rows that resolved, the number of rows that did not)."""
    ids: list[str | None] = []
    for symbol, filed in zip(rows["issuer_symbol"], rows["filing_date"], strict=True):
        known = resolver_on(pd.Timestamp(filed).date()).ids
        ids.append(next((known[s] for s in symbol_candidates(symbol) if s in known), None))
    out = rows.assign(instrument_id=pd.Series(ids, index=rows.index, dtype=object))
    resolved = out["instrument_id"].notna()
    return out[resolved].reset_index(drop=True), int((~resolved).sum())


def _signature(frame: pd.DataFrame) -> pd.Series:
    """One hash per row of its ``CONTENT`` (text of each cell: ``NaN`` and ``None`` agree)."""
    cells = frame[CONTENT].astype(object).where(frame[CONTENT].notna(), "").astype(str)
    return pd.Series(pd.util.hash_pandas_object(cells, index=False).to_numpy(), index=frame.index)


def _later(own: pd.Series, floor: date, replaces: pd.Series) -> pd.Series:
    """``own`` where nothing is replaced, else the later of ``own`` and ``floor``."""
    later = [max(o, floor) if r else o for o, r in zip(own, replaces, strict=True)]
    return pd.Series(later, index=own.index, dtype=object)


def stamp_known_from(rows: pd.DataFrame, stored: pd.DataFrame, floor: date) -> pd.DataFrame:
    """``rows`` (``COLUMNS`` but ``known_from``; ``ts`` the acceptance) with ``known_from`` set
    by the module doc's rules against the ``stored`` rows (their ``COLUMNS``; ``KEY_COLUMNS``
    suffice when no line of ``rows`` is stored)."""
    own = known_session(pd.to_datetime(rows["ts"], utc=True))
    if stored.empty or rows.empty:
        return rows.assign(known_from=own)
    latest = stored.sort_values("known_from", kind="stable").drop_duplicates(LINE_KEY, keep="last")
    kept = latest[LINE_KEY].assign(kept=latest["known_from"])
    joined = rows.merge(kept, on=LINE_KEY, how="left")
    joined.index = rows.index  # a left merge on a unique key keeps the rows and their order
    held = joined["kept"].notna()
    same = pd.Series(False, index=rows.index)
    if held.any():  # a line stored before: unchanged, or restated (needs the stored content)
        kept = kept.assign(kept_sig=_signature(latest))
        sig = rows.assign(sig=_signature(rows)).merge(kept, on=LINE_KEY, how="left")
        same = pd.Series((sig["sig"] == sig["kept_sig"]).to_numpy(), index=rows.index) & held
    replaces = held & ~same
    known = _later(own, floor, replaces)
    return rows.assign(known_from=known.where(~same, joined["kept"]))


def table_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """``rows`` with exactly the table's columns, one row per stored key."""
    return rows[COLUMNS].drop_duplicates([*LINE_KEY, "known_from"]).reset_index(drop=True)
