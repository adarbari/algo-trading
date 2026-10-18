"""Frame validation against a table's spec: point-in-time columns, key uniqueness and the per-table
value rules.
"""

import numpy as np
import pandas as pd

from algotrade.core.model.errors import DataValidationError
from algotrade.core.validation.bars import ohlcv_problems
from algotrade.core.views.series import FIELDS
from algotrade.storage.tables.schemas.events import (
    ACCESS_STATUSES,
    ANALYST_ESTIMATE_SNAPSHOTS,
    ANALYST_VENDOR_ACCESS,
    COVERAGE_STATUSES,
    MACRO_RELEASE_EVENTS,
    MACRO_SERIES,
    RELEASE_STATUSES,
    SNAPSHOT_KINDS,
    VINTAGE_KINDS,
)
from algotrade.storage.tables.schemas.outcomes import OUTCOME_STATUSES, outcome_problems
from algotrade.storage.tables.schemas.registry import spec_for, table_key
from algotrade.storage.tables.spec import (
    COMMON,
)


def validate_frame(table: str, frame: pd.DataFrame) -> None:
    spec = spec_for(table)
    missing = [c for c in (*COMMON, *spec.required) if c not in frame.columns]
    problems = [f"missing columns: {missing}"] if missing else []
    if not spec.open_ended:
        undeclared = [c for c in frame.columns if spec.column(str(c)) is None]
        if undeclared:
            problems.append(
                f"undeclared columns {undeclared}: declare them in storage/tables/schemas.py"
            )
    if not missing:
        if frame[list(COMMON)].isna().to_numpy().any():
            problems.append("point-in-time columns contain nulls")
        if "instrument_id" in spec.required and frame["instrument_id"].isna().any():
            problems.append("null instrument_id")
        if frame.duplicated(subset=table_key(spec, frame.columns)).any():
            problems.append("duplicate rows for the table key")
        if spec.grain == "bar":
            problems.extend(bar_problems(frame))
        if spec.name in VALUE_CHECKS:
            problems.extend(VALUE_CHECKS[spec.name](frame))
        if spec.grain == "outcome":
            bad = sorted({str(v) for v in frame["outcome_status"]} - OUTCOME_STATUSES)
            if bad:
                problems.append(f"outcome_status must be one of {sorted(OUTCOME_STATUSES)}: {bad}")
            problems.extend(outcome_problems(frame))
    if problems:
        raise DataValidationError(table, problems)


def bar_problems(frame: pd.DataFrame) -> list[str]:
    """OHLCV sanity checks on a bars frame (``core.validation.bars.ohlcv_problems``)."""
    return ohlcv_problems(*(frame[col].to_numpy(dtype=np.float64) for col in FIELDS))


def vintage_problems(frame: pd.DataFrame) -> list[str]:
    """``macro/series`` rows whose ``vintage_kind`` is not one of ``VINTAGE_KINDS``."""
    kinds = frame["vintage_kind"]
    bad = sorted({str(v) for v in kinds.dropna()} - VINTAGE_KINDS)
    if kinds.isna().any():
        bad.append("null")
    return [f"vintage_kind must be one of {sorted(VINTAGE_KINDS)}, got {bad}"] if bad else []


def release_status_problems(frame: pd.DataFrame) -> list[str]:
    """``events/macro_release`` rows whose ``status`` is not one of ``RELEASE_STATUSES``."""
    bad = sorted({str(v) for v in frame["status"]} - RELEASE_STATUSES)
    return [f"status must be one of {sorted(RELEASE_STATUSES)}, got {bad}"] if bad else []


def access_status_problems(frame: pd.DataFrame) -> list[str]:
    """``analyst/vendor_access`` rows whose ``status`` is not one of ``ACCESS_STATUSES``."""
    bad = sorted({str(v) for v in frame["status"]} - ACCESS_STATUSES)
    return [f"status must be one of {sorted(ACCESS_STATUSES)}, got {bad}"] if bad else []


def snapshot_kind_problems(frame: pd.DataFrame) -> list[str]:
    """``analyst/estimate_snapshots``: a known ``kind``; ``status`` only on ``coverage`` rows."""
    bad = sorted({str(v) for v in frame["kind"]} - SNAPSHOT_KINDS)
    problems = [f"kind must be one of {sorted(SNAPSHOT_KINDS)}, got {bad}"] if bad else []
    status = frame["status"] if "status" in frame.columns else pd.Series(None, index=frame.index)
    coverage = frame["kind"] == "coverage"
    wrong = sorted({str(v) for v in status[coverage]} - COVERAGE_STATUSES)
    if wrong:
        problems.append(f"coverage status must be one of {sorted(COVERAGE_STATUSES)}, got {wrong}")
    if status[~coverage].notna().any():
        problems.append("status is set only on coverage rows")
    return problems


# The value rules of the tables that restrict a column to a vocabulary, by table name.
VALUE_CHECKS = {
    MACRO_SERIES.name: vintage_problems,
    MACRO_RELEASE_EVENTS.name: release_status_problems,
    ANALYST_VENDOR_ACCESS.name: access_status_problems,
    ANALYST_ESTIMATE_SNAPSHOTS.name: snapshot_kind_problems,
}
