"""Rule-screen rows as the ``results/rule_screen`` and ``results/rule_screen_values`` frames
(ADR 0029), stamped with the run's point-in-time columns and the config's identity; the
screen rows also carry the session's ``regime`` and ``size_multiplier`` (ADR 0049). The same
frames' run objects, ``results/screen_runs`` (ScreenRun: the summary and the changes against the
previous run, frozen at write) and ``results/screen_picks`` (ScreenPick: the picked and PAUSED
rows), are framed here from the same rows, so the three published together cannot differ. Also
the one rule for what a pick is (``is_picked``)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.predicates import FieldValue
from algotrade.services.views import to_value
from algotrade.storage.tables.schemas import (
    DISPLAY_COLUMN_MODE,
    GROUP_MODE,
)
from algotrade.storage.tables.schemas import (
    SCREEN_PICKS as SCREEN_PICKS_SPEC,
)
from algotrade.strategies.screeners.base import Decision
from algotrade.strategies.screeners.rules import RULES, RuleRow, RuleScreenResult
from algotrade.strategies.screeners.rules.groups import Gate, GroupResult

RULE_SCREEN = "rule_screen"  # results/<name> (storage/tables/schemas.py)
RULE_SCREEN_VALUES = "rule_screen_values"
SCREEN_RUNS = "screen_runs"
SCREEN_PICKS = "screen_picks"

PAUSED = Decision.PAUSED.value  # the regime gate held the pick back (ADR 0049)
# Never a pick: rejected, not processed (SKIPPED, UNKNOWN), held back by the gate, or left out of
# the run with a reason (EXCLUDED, a stale chain the chains gate tolerated, ADR 0054).
NOT_PICKED = frozenset(
    d.value
    for d in (
        Decision.REJECT, Decision.SKIPPED, Decision.UNKNOWN, Decision.PAUSED, Decision.EXCLUDED
    )
)  # fmt: skip


def is_picked(decision: str) -> bool:
    """Whether a row with ``decision`` is one of the screener's picks."""
    return decision not in NOT_PICKED


@dataclass(frozen=True)
class Stamp:
    """Who and what produced the rows, and when (the run's point-in-time columns)."""

    session_date: date
    run_id: str
    knowledge_ts: datetime
    user_id: str
    config_id: str
    config_hash: str
    config_version: int | None
    regime: str | None = None  # the session's regime label (ADR 0049; None: gate off / unknown)
    size_multiplier: float = 1.0  # the regime's size for this screener (1.0 with the gate off)

    def apply(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame["user_id"], frame["config_id"] = self.user_id, self.config_id
        frame["session_date"] = self.session_date
        frame["knowledge_ts"] = pd.Timestamp(self.knowledge_ts)
        frame["source"] = f"screener:{RULES}:{self.config_id}"
        frame["run_id"] = self.run_id
        return frame


def _num(value: FieldValue) -> float | None:
    """The value as stored in ``value_num`` (None: not a number; a flag is not one)."""
    found = to_value(value)
    if isinstance(found, bool) or not isinstance(found, int | float):
        return None
    return float(found)


def _str(value: FieldValue) -> str | None:
    return None if value is None or _num(value) is not None else str(value)


def _ids(row: RuleRow, outcome: str) -> str:
    """The gates (ungrouped criteria and top-level groups, ADR 0071) that ended ``outcome``."""
    return ",".join(g.id for g in row.gate_results if g.gating and g.outcome.value == outcome)


def _groups(gates: tuple[Gate, ...]) -> list[GroupResult]:
    """Every group result of the row's gate tree, a group before its nested ones."""
    found: list[GroupResult] = []
    for gate in gates:
        if isinstance(gate, GroupResult):
            found.append(gate)
            found.extend(_groups(gate.members))
    return found


def _parents(result: RuleScreenResult) -> dict[str, str]:
    """Each criterion's and group's parent group id (gates have none)."""
    return {m: g.id for g in result.spec.groups for m in g.members}


def screen_frame(result: RuleScreenResult, stamp: Stamp) -> pd.DataFrame:
    records = [
        {
            "instrument_id": row.instrument_id,
            "config_version": stamp.config_version,
            "config_hash": stamp.config_hash,
            "decision": row.decision.value,
            "score": row.score,
            "rank": row.rank,
            "tie_break": row.tie_break,
            "flags": ",".join(row.flags),
            "reasons": "; ".join(row.reasons),
            "failed": _ids(row, "FAIL"),
            "near_missed": _ids(row, "NEAR"),
            "missing": _ids(row, "MISSING"),
            "regime": stamp.regime,
            "size_multiplier": stamp.size_multiplier,
        }
        for row in result.rows
    ]
    frame = pd.DataFrame.from_records(records)
    frame["config_version"] = frame["config_version"].astype("Int64")
    return stamp.apply(frame)


def values_frame(result: RuleScreenResult, stamp: Stamp) -> pd.DataFrame:
    parent = _parents(result)
    records: list[dict[str, object]] = []
    for row in result.rows:
        for r in row.results:
            records.append(
                {
                    "instrument_id": row.instrument_id,
                    "criterion_id": r.criterion.id,
                    "field": r.criterion.field,
                    "mode": r.criterion.mode.value,
                    "value_num": _num(r.value),
                    "value_str": _str(r.value),
                    "outcome": r.outcome.value,
                    "distance": r.distance,
                    "normalised": r.normalised,
                    "penalty": r.penalty,
                    "group_id": parent.get(r.criterion.id),
                }
            )
        for found in _groups(row.gate_results):
            g = found.as_written  # a group under a none is stored as written, not negated
            records.append(
                {
                    "instrument_id": row.instrument_id,
                    "criterion_id": g.id,
                    "field": g.group.kind,
                    "mode": GROUP_MODE,
                    "value_num": None,
                    "value_str": g.decided_by,
                    "outcome": g.outcome.value,
                    "distance": None,
                    "normalised": None,
                    "penalty": g.verdict.penalty,
                    "group_id": parent.get(g.id),
                }
            )
        for (name, value), (_, field) in zip(row.columns, result.spec.columns, strict=True):
            records.append(
                {
                    "instrument_id": row.instrument_id,
                    "criterion_id": name,
                    "field": field,
                    "mode": DISPLAY_COLUMN_MODE,
                    "value_num": _num(value),
                    "value_str": _str(value),
                    "outcome": "INFO",
                    "distance": None,
                    "normalised": None,
                    "penalty": None,
                    "group_id": None,
                }
            )
    return stamp.apply(pd.DataFrame.from_records(records))


@dataclass(frozen=True)
class Lineage:
    """What a run's ``results/screen_runs`` row records beside its own rows: the config's run in
    the previous stored session it is compared with (None: there was none, or no row of it is
    stored) and when the run started and finished (None: not recorded)."""

    previous_run_id: str | None = None
    previous_session: date | None = None
    previous_version: int | None = None
    previous_decisions: Mapping[str, str] | None = None  # that run's decision per instrument
    started_at: datetime | None = None
    finished_at: datetime | None = None


def change_of(decision: str, was: str | None) -> str | None:
    """``"new"`` (picked now, not before), ``"dropped"`` (picked before, not now) or None, for a
    name's ``decision`` and its previous run's (None: not in it): the one rule of the frozen
    counts and of the read model's per-name tags."""
    now_picked, was_picked = is_picked(decision), was is not None and is_picked(was)
    if now_picked and not was_picked:
        return "new"
    return "dropped" if was_picked and not now_picked else None


def change_counts(decisions: Mapping[str, str], before: Mapping[str, str]) -> tuple[int, int]:
    """``(new, dropped)`` of a run's ``decisions`` (per instrument) against ``before`` (the
    previous run's): new = picked now and not before, dropped = picked before and not now,
    counted over the names of this run (the read model's per-name tags)."""
    new = dropped = 0
    for instrument, decision in decisions.items():
        change = change_of(decision, before.get(instrument))
        new += change == "new"
        dropped += change == "dropped"
    return new, dropped


def picks_frame(screen: pd.DataFrame) -> pd.DataFrame:
    """The picked and PAUSED rows of the run's ``screen_frame``, ScreenPick's columns, sorted by
    instrument (equal bytes for equal runs)."""
    decisions = screen["decision"].astype(str)
    kept = screen[decisions.map(is_picked) | (decisions == PAUSED)]
    columns = [c.name for c in SCREEN_PICKS_SPEC.columns]
    return kept[columns].sort_values("instrument_id", kind="stable").reset_index(drop=True)


def runs_frame(
    result: RuleScreenResult, screen: pd.DataFrame, stamp: Stamp, lineage: Lineage
) -> pd.DataFrame:
    """The run's one ``results/screen_runs`` row: ``result.summary`` (the run record's), the
    picked and PAUSED counts, and the changes against ``lineage``'s previous run, frozen here."""
    decisions = dict(result.summary.decisions)
    picked = sum(n for d, n in decisions.items() if is_picked(d))
    before = lineage.previous_decisions
    new = dropped = None
    if before is not None:
        new, dropped = change_counts(
            {r.instrument_id: r.decision.value for r in result.rows}, before
        )
    record = {
        "user_id": stamp.user_id,
        "config_id": stamp.config_id,
        "config_hash": stamp.config_hash,
        "config_version": stamp.config_version,
        "rows": result.summary.rows,
        "passed": result.summary.passed,
        "picked": picked,
        "paused": decisions.get(PAUSED, 0),
        "decision_names": list(decisions),
        "decision_counts": list(decisions.values()),
        "regime": stamp.regime,
        "size_multiplier": stamp.size_multiplier,
        "previous_run_id": lineage.previous_run_id,
        "previous_session": lineage.previous_session,
        "previous_version": lineage.previous_version,
        "new_picks": new,
        "dropped": dropped,
        "started_at": None if lineage.started_at is None else pd.Timestamp(lineage.started_at),
        "finished_at": None if lineage.finished_at is None else pd.Timestamp(lineage.finished_at),
    }
    frame = pd.DataFrame.from_records([record])
    for name in ("config_version", "previous_version", "new_picks", "dropped"):
        frame[name] = frame[name].astype("Int64")
    for name in ("started_at", "finished_at"):
        frame[name] = pd.to_datetime(frame[name], utc=True)
    return stamp.apply(frame)


def rule_frames(
    result: RuleScreenResult, stamp: Stamp, lineage: Lineage | None = None
) -> dict[str, pd.DataFrame]:
    """``{result name: frame}`` for ``ResultWriter.write_result``: the rule screen's two tables
    and its run objects, all from the same rows (published in one block, ADR 0022)."""
    screen = screen_frame(result, stamp)
    return {
        RULE_SCREEN: screen,
        RULE_SCREEN_VALUES: values_frame(result, stamp),
        SCREEN_RUNS: runs_frame(result, screen, stamp, lineage or Lineage()),
        SCREEN_PICKS: picks_frame(screen),
    }
