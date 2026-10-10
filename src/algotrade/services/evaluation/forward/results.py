"""One night of the forward paper record of one RECORD OWNER: tonight's signals of every edge
the owner has recording (``site`` for the site's edges, else a user's own), the open trades their
outcomes close, both published atomically into ``results/edge_paper`` with one run record
``edge-paper:<owner>`` (ADR 0053 amendment 2026-10-10, ADR 0015). A follower of a site edge
trades nothing: its job only settles the open rows it wrote while followers traded, until none is
left (readers leave those rows out of the shared record, ``data.paper.read_paper``).

Rows land in the partition of their signal session, so a settled trade replaces its own open row
(runs merge per key; ``as_of`` still gives the book as an earlier night saw it). The night is
idempotent: an edge that already has rows for the session is not signalled again, and a settled
trade is not open any more, so a re-run writes the same rows. An edge's record starts on the first
night this job sees it recording (``_since``), never backfilled to when its status changed; a due
signal that could not be made is listed in the run record's ``skipped`` with its reason (never as
an empty record), and a session between two nights that nobody signalled in ``missed``."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.data.paper import LOOKBACK_DAYS, job_name, read_stored
from algotrade.services.evaluation.forward.settle import OPEN, outcome_hash, settle_group
from algotrade.services.evaluation.forward.signals import (
    edge_signals,
    legs_between,
    paper_traded,
)
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.runs import RunRecord, RunStatus, start_run
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import EDGE_PAPER

RESULT = "edge_paper"
SOURCE = "edge-signals"
SIGNALLED, NO_PICKS, NOT_DUE, SKIPPED_TONIGHT = "signalled", "no_picks", "not_due", "skipped"
MISSED = "the nightly did not run edge-signals for this session"


def paper_owners(reader: StoreReader, configs: ConfigStore, session: date) -> list[UserContext]:
    """The record owners the nightly works for, ``site`` first: those with an edge of their own
    recording (evidenced or live), and those who still have open paper trades (they settle after
    the edge stopped recording or is gone; a follower's old rows of a site edge count)."""
    since = session - timedelta(days=LOOKBACK_DAYS)
    owners = []
    for owner in dict.fromkeys([SITE_USER, *configs.users()]):
        recording = any(e.owner == owner and paper_traded(e) for e in load_edges(configs, owner))
        if recording or (read_stored(reader, owner, since, session)["status"] == OPEN).any():
            owners.append(UserContext(owner))
    return owners


@dataclass(frozen=True)
class PaperNight:
    """What one night wrote for one record owner, by edge id."""

    session: date
    signalled: dict[str, int] = field(default_factory=dict)
    settled: dict[str, int] = field(default_factory=dict)
    skipped: list[dict[str, str]] = field(default_factory=list)
    rows: int = 0
    tonight: dict[str, dict[str, str]] = field(default_factory=dict)
    missed: list[dict[str, str]] = field(default_factory=list)


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
    since: dict[str, date],
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, str]], dict[str, dict[str, str]]]:
    tonight: dict[str, dict[str, str]] = {}
    rows: list[dict[str, Any]] = []
    made: dict[str, int] = {}
    skipped: list[dict[str, str]] = []
    done = set(book.loc[book["signal_session"] == session, "edge_id"])
    for edge in edges:
        if edge.id in done:
            tonight[edge.id] = {"state": SIGNALLED, "reason": ""}
            continue
        try:
            found = edge_signals(reader, configs, user, edge, since.get(edge.id, session), session)
        except ConfigurationError as error:
            skipped.append({"edge": edge.id, "reason": str(error)})
            tonight[edge.id] = {"state": SKIPPED_TONIGHT, "reason": str(error)}
            continue
        if found.skipped:
            skipped.append({"edge": edge.id, "reason": found.skipped})
            tonight[edge.id] = {"state": SKIPPED_TONIGHT, "reason": found.skipped}
        elif found.signals:
            tonight[edge.id] = {"state": SIGNALLED, "reason": ""}
        elif found.screener is not None:
            tonight[edge.id] = {"state": NO_PICKS, "reason": ""}
        else:
            tonight[edge.id] = {"state": NOT_DUE, "reason": ""}
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
    return rows, made, skipped, tonight


def _nights(writer: ResultWriter, user: UserContext, session: date) -> list[RunRecord]:
    """The owner's complete nights up to ``session``, oldest first."""
    found = [
        r
        for r in writer.runs_for(job_name(user.user_id))
        if r.session_date <= session and r.status is RunStatus.COMPLETE
    ]
    return sorted(found, key=lambda r: r.session_date)


def _since(nights: list[RunRecord]) -> dict[str, date]:
    """Where each edge's record started: the first night whose run listed it as recording."""
    first: dict[str, date] = {}
    for night in nights:
        for edge_id in night.stats.get("tonight", {}):
            first.setdefault(edge_id, night.session_date)
    return first


def _missed(
    reader: StoreReader,
    configs: ConfigStore,
    user: UserContext,
    edges: list[Edge],
    nights: list[RunRecord],
    since: dict[str, date],
    session: date,
) -> list[dict[str, str]]:
    """The due sessions between the previous night and ``session`` that no night signalled (the
    step is latest-only: a catch-up skips sessions) for the edges that night had recording:
    recorded, never a silent gap, and never before the record began."""
    before = [n for n in nights if n.session_date < session]
    if not before:
        return []
    last = max(before, key=lambda n: n.session_date)
    between = sessions_between(last.session_date, session)[1:-1]
    missed: list[dict[str, str]] = []
    for e in edges:
        if not between or e.id not in last.stats.get("tonight", {}):
            continue
        try:
            legs, _ = legs_between(reader, configs, user, e, since[e.id], between[0], between[-1])
        except (MissingDataError, ConfigurationError) as error:
            missed.append({"edge": e.id, "session": between[0].isoformat(), "reason": str(error)})
            continue
        missed += [
            {"edge": e.id, "session": leg.decision.isoformat(), "reason": MISSED} for leg in legs
        ]
    return missed


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
    """Settle the open trades ``user`` (a record owner: ``site`` or a user) wrote and make tonight's
    signals of the edges it owns that are recording, at ``session``; publish both."""
    user_id = user.user_id
    edges = {e.id: e for e in load_edges(configs, user_id)}
    book = read_stored(reader, user_id, session - timedelta(days=LOOKBACK_DAYS), session, now)
    settled, settled_n = _settlements(reader, edges, book, session, now)
    recording = [e for e in edges.values() if e.owner == user_id and paper_traded(e)]
    nights = _nights(writer, user, session)
    since = _since(nights)
    signals, signalled, skipped, tonight = _signals(
        reader, configs, user, recording, book, session, user_id, since
    )
    rows = [*settled, *signals]
    record = start_run(job_name(user_id), session, now)
    missed = _missed(reader, configs, user, recording, nights, since, session)
    night = PaperNight(session, signalled, settled_n, skipped, len(rows), tonight, missed)
    stats = {
        "signalled": night.signalled, "settled": night.settled, "skipped": night.skipped,
        "rows": night.rows, "tonight": night.tonight, "missed": night.missed,
    }  # fmt: skip
    with writer.publishing(record.run_id, now):
        if rows:
            frame = paper_frame(rows, record.run_id, now)
            for day in sorted(set(frame["signal_session"])):
                part = frame[frame["signal_session"] == day].reset_index(drop=True)
                writer.write_result(RESULT, day, record.run_id, part, pending=True)
        writer.save_run(record.finish(now, complete=True, stats=stats))
    return night, record
