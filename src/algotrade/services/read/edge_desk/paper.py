"""The paper trades of the edges a user sees, as ``ctx.session`` knew them (ADR 0053 amendment
2026-10-10, ADR 0036's one session).

Paper trades follow the edge's OWNER: a site edge has ONE record, the ``site``'s, which every
follower and every other reader sees alike; a user's own edge has the user's, which no one else
reads (``record_owner``). The trades are the stored record of ``results/edge_paper``
(``data.paper``: written by the nightly ``edge-signals`` job, never derived here: re-deriving
history from today's edge documents would rewrite the record when the user edits an edge). Point
in time by business dates, not by when a row was written: a trade signalled after the session is
not read, and one whose sell session is after the session is OPEN whatever a later night recorded
(its result was not known yet). A trade that is open, settled or skipped is shown as the record
says for the session; a number not known (an open trade's return) is None, never zero.

Knowledge too (ADR 0064 decision 9): a session that finished is read as its nightly left it. A row
a later night wrote or rewrote (``knowledge_ts`` after the moment the session's workflow first
completed, ADR 0062) is not read, so the latest row per trade at the cutoff is the record: a
settlement recorded afterwards cannot change a past session's live state."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.config.user import SITE_USER
from algotrade.data.paper import LOOKBACK_DAYS, read_paper
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.instruments.identity import Instrument, load_instruments
from algotrade.services.read.session import NIGHTLY
from algotrade.services.read.values import to_scalar
from algotrade.storage.runs import published

OPEN, WON, LOST, SKIPPED = "open", "won", "lost", "skipped"


@dataclass(frozen=True)
class PaperTrade:
    """One paper trade of an edge: ``rank`` 1 is the screener's best name; ``status`` open, won,
    lost or skipped (``reason`` says why: never a loss); ``excess_return`` only for a settled one
    (the outcome's measure); ``delisted``: measured to the name's last bar."""

    edge_id: str
    edge_name: str
    instrument_id: str
    instrument: Instrument | None
    screener: str
    rank: int
    signal_session: date
    buy_session: date
    sell_session: date
    horizon_sessions: int
    status: str
    reason: str
    excess_return: float | None
    delisted: bool


def _text(value: object) -> str:
    found = to_scalar(value)
    return found if isinstance(found, str) else ""


def _number(value: object) -> float | None:
    found = to_scalar(value)
    return None if found is None or pd.isna(found) else float(found)


def _trade(row: dict[str, object], session: date, names: Mapping[str, str]) -> PaperTrade:
    sell = row["sell_session"]
    known = isinstance(sell, date) and sell <= session  # its window had closed by the session
    status = str(row["status"]) if known else OPEN
    return PaperTrade(
        edge_id=str(row["edge_id"]),
        edge_name=names.get(str(row["edge_id"]), str(row["edge_id"])),
        instrument_id=str(row["instrument_id"]),
        instrument=None,
        screener=_text(row.get("screener")),
        rank=int(row["rank"]),  # type: ignore[call-overload]
        signal_session=row["signal_session"],  # type: ignore[arg-type]
        buy_session=row["buy_session"],  # type: ignore[arg-type]
        sell_session=sell,  # type: ignore[arg-type]
        horizon_sessions=int(row["horizon_sessions"]),  # type: ignore[call-overload]
        status=status,
        reason=_text(row.get("reason")) if known else "",
        excess_return=_number(row.get("excess_return")) if status in (WON, LOST) else None,
        delisted=bool(to_scalar(row.get("delisted"))) if known else False,
    )


def record_owner(edge: Edge, user_id: str) -> str:
    """Whose record holds the edge's paper trades: ``site`` for a site edge, else the user's."""
    return user_id if edge.mine else SITE_USER


def session_cutoff(ctx: ReadContext) -> datetime | None:
    """When ``ctx.session``'s nightly workflow first completed (ADR 0062), the moment a read of
    the session could first have been served; None: it has not completed (a requested date still
    running or never run), so nothing is cut off."""
    done = [
        r.finished_at
        for r in ctx.reader.runs(NIGHTLY)
        if r.session_date == ctx.session.date and published(r) and r.finished_at is not None
    ]
    return min(done) if done else None


def load_trades(ctx: ReadContext, edges: Mapping[str, Edge]) -> tuple[PaperTrade, ...]:
    """Every paper trade of ``edges`` (by id; a trade of an edge the user does not see is left out,
    and so is a follower's old row of a site edge: only the record owner's rows count) signalled
    in the window up to ``ctx.session``, oldest signal first, as the rows stood at the session's
    cutoff (``session_cutoff``)."""
    day = ctx.session.date
    owners = {i: record_owner(e, ctx.user.user_id) for i, e in edges.items()}
    frame = read_paper(
        ctx.reader, owners, day - timedelta(days=LOOKBACK_DAYS), day, session_cutoff(ctx)
    )
    names = {i: e.name for i, e in edges.items()}
    records = [{str(k): v for k, v in r.items()} for r in frame.to_dict("records")]
    return tuple(_trade(r, day, names) for r in records)


def with_instruments(ctx: ReadContext, trades: tuple[PaperTrade, ...]) -> tuple[PaperTrade, ...]:
    """``trades`` with their instrument (identity in the session's reference snapshot)."""
    found = load_instruments(ctx, [t.instrument_id for t in trades])
    return tuple(replace(t, instrument=found.get(t.instrument_id)) for t in trades)
