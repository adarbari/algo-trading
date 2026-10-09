"""One night of the forward paper record: tonight's signals of every edge a user follows, the
open trades their outcomes close, both published atomically into ``results/edge_paper`` with one
run record ``edge-paper:<user>`` (ADR 0053 amendment 2026-10-09, ADR 0015).

Rows land in the partition of their signal session, so a settled trade replaces its own open row
(runs merge per key; ``as_of`` still gives the book as an earlier night saw it). The night is
idempotent: an edge that already has rows for the session is not signalled again, and a settled
trade is not open any more, so a re-run writes the same rows. A due signal that could not be made
is listed in the run record's ``skipped`` with its reason (never as an empty record)."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.paper import LOOKBACK_DAYS, read_paper
from algotrade.services.evaluation.forward.settle import OPEN, outcome_hash, settle_group
from algotrade.services.evaluation.forward.signals import edge_signals, paper_traded
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.runs import RunRecord, start_run
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import EDGE_PAPER

RESULT = "edge_paper"
SOURCE = "edge-signals"


def paper_users(configs: ConfigStore) -> list[UserContext]:
    """The users with an edge they follow, try or have retired (a retired edge's open trades are
    still settled): the users the nightly signals for."""
    return [
        UserContext(owner)
        for owner in configs.users()
        if any(
            e.follow.state != "researching" for e in load_edges(configs, owner) if e.follow.since
        )
    ]


def job_name(user_id: str) -> str:
    """The run-record ``job`` of one user's nightly paper record."""
    return f"edge-paper:{user_id}"


@dataclass(frozen=True)
class PaperNight:
    """What one night wrote for one user, by edge id."""

    session: date
    signalled: dict[str, int] = field(default_factory=dict)
    settled: dict[str, int] = field(default_factory=dict)
    skipped: list[dict[str, str]] = field(default_factory=list)
    rows: int = 0


def _group(trades: pd.DataFrame) -> list[pd.DataFrame]:
    keys = ["edge_id", "signal_session", "buy_session", "horizon_sessions"]
    return [g for _, g in trades.groupby(keys, sort=True)]


def _settlements(
    reader: StoreReader,
    edges: dict[str, Edge],
    book: pd.DataFrame,
    session: date,
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    open_rows = book[(book["status"] == OPEN) & (book["sell_session"] <= session)]
    rows: list[dict[str, Any]] = []
    counted: dict[str, int] = defaultdict(int)
    for group in _group(open_rows):
        edge = edges.get(str(group.iloc[0]["edge_id"]))
        if edge is None:  # deleted since: its trades stay open, nothing judges them
            continue
        by_name = group.set_index("instrument_id")
        for done in settle_group(reader, edge, group, session, now):
            row: dict[str, Any] = {str(k): v for k, v in by_name.loc[done.instrument_id].items()}
            row["instrument_id"] = done.instrument_id
            row.update(
                status=done.status, reason=done.reason, delisted=done.delisted,
                excess_return=float("nan") if done.excess_return is None else done.excess_return,
            )  # fmt: skip
            rows.append(row)
            counted[edge.id] += 1
    return rows, dict(counted)


def _signals(
    reader: StoreReader,
    configs: ConfigStore,
    user: UserContext,
    edges: list[Edge],
    book: pd.DataFrame,
    session: date,
    user_id: str,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    made: dict[str, int] = {}
    skipped: list[dict[str, str]] = []
    done = set(book.loc[book["signal_session"] == session, "edge_id"])
    for edge in edges:
        if edge.id in done:
            continue
        try:
            found = edge_signals(reader, configs, user, edge, session)
        except ConfigurationError as error:
            skipped.append({"edge": edge.id, "reason": str(error)})
            continue
        if found.skipped:
            skipped.append({"edge": edge.id, "reason": found.skipped})
        for s in found.signals:
            rows.append(
                {
                    "user_id": user_id, "edge_id": edge.id, "signal_session": session,
                    "instrument_id": s.instrument_id, "config_hash": found.config_hash,
                    "outcome_hash": outcome_hash(edge), "screener": found.screener,
                    "status": OPEN, "reason": "", "buy_session": s.buy_session,
                    "sell_session": s.sell_session, "horizon_sessions": found.horizon,
                    "rank": s.rank, "delisted": False, "excess_return": float("nan"),
                }
            )  # fmt: skip
        if found.signals:
            made[edge.id] = len(found.signals)
    return rows, made, skipped


def paper_frame(rows: list[dict[str, Any]], run_id: str, now: datetime) -> pd.DataFrame:
    """The ``results/edge_paper`` rows, stamped (partition: each row's signal session)."""
    frame = pd.DataFrame(rows)
    frame["session_date"] = frame["signal_session"]
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = SOURCE
    frame["run_id"] = run_id
    return frame[[c.name for c in EDGE_PAPER.columns if c.name in frame.columns]]


def run_night(
    reader: StoreReader,
    writer: ResultWriter,
    configs: ConfigStore,
    user: UserContext,
    session: date,
    now: datetime,
) -> tuple[PaperNight, RunRecord]:
    """Settle ``user``'s open trades and make tonight's signals at ``session``; publish both."""
    user_id = user.user_id
    edges = {e.id: e for e in load_edges(configs, user_id)}
    book = read_paper(reader, user_id, session - timedelta(days=LOOKBACK_DAYS), session, now)
    settled, settled_n = _settlements(reader, edges, book, session, now)
    signals, signalled, skipped = _signals(
        reader, configs, user, [e for e in edges.values() if paper_traded(e)], book, session,
        user_id,
    )  # fmt: skip
    rows = [*settled, *signals]
    record = start_run(job_name(user_id), session, now)
    night = PaperNight(session, signalled, settled_n, skipped, len(rows))
    stats = {
        "signalled": night.signalled, "settled": night.settled, "skipped": night.skipped,
        "rows": night.rows,
    }  # fmt: skip
    with writer.publishing(record.run_id, now):
        if rows:
            frame = paper_frame(rows, record.run_id, now)
            for day in sorted(set(frame["signal_session"])):
                part = frame[frame["signal_session"] == day].reset_index(drop=True)
                writer.write_result(RESULT, day, record.run_id, part, pending=True)
        writer.save_run(record.finish(now, complete=True, stats=stats))
    return night, record
