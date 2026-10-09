"""The paper trades a user's followed edges made, as ``ctx.session`` knew them (ADR 0053 amendment
2026-10-09, ADR 0036's one session).

The trades are the stored record of ``results/edge_paper`` (``data.paper``: written by the nightly
``edge-signals`` job, never derived here: re-deriving history from today's edge documents would
rewrite the record when the user edits an edge). Point in time by business dates, not by when a
row was written: a trade signalled after the session is not read, and one whose sell session is
after the session is OPEN whatever a later night recorded (its result was not known yet). A
trade that is open, settled or skipped is shown as the record says for the session; a number
not known (an open trade's return) is None, never zero."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta

import pandas as pd

from algotrade.data.paper import LOOKBACK_DAYS, read_paper
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.identity import Instrument, load_instruments
from algotrade.services.read.values import to_scalar

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


def load_trades(ctx: ReadContext, names: Mapping[str, str]) -> tuple[PaperTrade, ...]:
    """Every paper trade of the user's edges (``names``: edge id -> name; a trade of an edge the
    user no longer has is left out) signalled in the window up to ``ctx.session``, oldest signal
    first."""
    day = ctx.session.date
    frame = read_paper(ctx.reader, ctx.user.user_id, day - timedelta(days=LOOKBACK_DAYS), day)
    records = [{str(k): v for k, v in r.items()} for r in frame.to_dict("records")]
    return tuple(_trade(r, day, names) for r in records if str(r["edge_id"]) in names)


def with_instruments(ctx: ReadContext, trades: tuple[PaperTrade, ...]) -> tuple[PaperTrade, ...]:
    """``trades`` with their instrument (identity in the session's reference snapshot)."""
    found = load_instruments(ctx, [t.instrument_id for t in trades])
    return tuple(replace(t, instrument=found.get(t.instrument_id)) for t in trades)
