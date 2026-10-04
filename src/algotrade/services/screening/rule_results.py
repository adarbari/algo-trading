"""Rule-screen rows as the ``results/rule_screen`` and ``results/rule_screen_values`` frames
(ADR 0029), stamped with the run's point-in-time columns and the config's identity."""

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.predicates import FieldValue
from algotrade.strategies.screeners.rules import RULES, RuleRow, RuleScreenResult

RULE_SCREEN = "rule_screen"  # results/<name> (storage/tables/schemas.py)
RULE_SCREEN_VALUES = "rule_screen_values"
COLUMN_MODE = "column"  # a display column's row in the values table


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

    def apply(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame["user_id"], frame["config_id"] = self.user_id, self.config_id
        frame["session_date"] = self.session_date
        frame["knowledge_ts"] = pd.Timestamp(self.knowledge_ts)
        frame["source"] = f"screener:{RULES}:{self.config_id}"
        frame["run_id"] = self.run_id
        return frame


def _num(value: FieldValue) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _str(value: FieldValue) -> str | None:
    return None if value is None or _num(value) is not None else str(value)


def _ids(row: RuleRow, outcome: str) -> str:
    return ",".join(r.criterion.id for r in row.results if r.gating and r.outcome == outcome)


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
            "tier": row.tier,
            "class": row.klass,
            "flags": ",".join(row.flags),
            "reasons": "; ".join(row.reasons),
            "failed": _ids(row, "FAIL"),
            "near_missed": _ids(row, "NEAR"),
            "missing": _ids(row, "MISSING"),
        }
        for row in result.rows
    ]
    frame = pd.DataFrame.from_records(records)
    frame["config_version"] = frame["config_version"].astype("Int64")
    return stamp.apply(frame)


def values_frame(result: RuleScreenResult, stamp: Stamp) -> pd.DataFrame:
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
                }
            )
        for (name, value), (_, field) in zip(row.columns, result.spec.columns, strict=True):
            records.append(
                {
                    "instrument_id": row.instrument_id,
                    "criterion_id": name,
                    "field": field,
                    "mode": COLUMN_MODE,
                    "value_num": _num(value),
                    "value_str": _str(value),
                    "outcome": "INFO",
                    "distance": None,
                    "normalised": None,
                    "penalty": None,
                }
            )
    return stamp.apply(pd.DataFrame.from_records(records))


def rule_frames(result: RuleScreenResult, stamp: Stamp) -> dict[str, pd.DataFrame]:
    """``{result name: frame}`` for ``ResultWriter.write_result``."""
    return {
        RULE_SCREEN: screen_frame(result, stamp),
        RULE_SCREEN_VALUES: values_frame(result, stamp),
    }
