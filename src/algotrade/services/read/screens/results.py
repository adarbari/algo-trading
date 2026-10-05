"""What a screener's run stored for an instrument (``ScreenResult``): rank, decision, score,
reasons, the flags that hold, every criterion's outcome with the value it judged, and the
screen's display columns, from ``results/rule_screen`` and ``results/rule_screen_values`` for
exactly the run's session (``runs.ScreenerRun``). Nothing is recomputed.

``load_results`` reads the values of the asked instruments once for every run asked (one
column-pruned read of the values partition) and names the instruments in one identity read."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.instruments.identity import Instrument, load_instruments
from algotrade.services.read.screens.runs import ScreenerRun, run_rows
from algotrade.services.read.values import Unknown, to_scalar
from algotrade.storage.tables.schemas import result_table

RULE_SCREEN_VALUES = result_table("rule_screen_values")
VALUE_COLUMNS = (
    "user_id", "config_id", "criterion_id", "mode", "field", "outcome", "value_num", "value_str",
    "distance",
)  # fmt: skip
COLUMN_MODE = "column"  # a display column's rows (outcome INFO), not a criterion's

ResultKey = tuple[str, str]  # (run id, instrument id)


@dataclass(frozen=True)
class CriterionResult:
    """What one criterion judged: the value (None: missing), PASS / NEAR / FAIL / MISSING
    and, for a near miss or a fail, how far from passing."""

    id: str
    field: str
    mode: str
    outcome: str
    value: Scalar
    distance: float | None


@dataclass(frozen=True)
class ResultColumn:
    """One of the screen's display columns (``[columns]``) for the instrument."""

    name: str
    value: Scalar


@dataclass(frozen=True)
class ScreenResult:
    """One instrument's row of one run. ``instrument``: who it is in the session's reference
    snapshot (None: not in it); ``criteria`` in the order stored."""

    run_id: str
    config_id: str
    instrument_id: str
    instrument: Instrument | None
    rank: int
    decision: str
    score: float | None
    tie_break: float | None
    reasons: str
    flags: tuple[str, ...]
    criteria: tuple[CriterionResult, ...]
    columns: tuple[ResultColumn, ...]


def _records(frame: pd.DataFrame) -> list[Mapping[str, Any]]:
    return [{str(k): v for k, v in r.items()} for r in frame.to_dict("records")]


def _float(value: object) -> float | None:
    found = to_scalar(value)
    return None if found is None else float(found)


def _value(row: Mapping[str, Any]) -> Scalar:
    number = to_scalar(row.get("value_num"))
    return number if number is not None else to_scalar(row.get("value_str"))


def _values(
    ctx: ReadContext, runs: Sequence[ScreenerRun], ids: Sequence[str]
) -> dict[ResultKey, list[Mapping[str, Any]]]:
    """The stored value rows of ``ids`` in each run, by (run id, instrument id)."""
    stored = partition(ctx, RULE_SCREEN_VALUES, VALUE_COLUMNS, ids)
    if isinstance(stored, Unknown) or stored.empty:
        return {}
    out: dict[ResultKey, list[Mapping[str, Any]]] = {}
    for run in runs:
        mine = stored[
            (stored["user_id"] == run.owner)
            & (stored["config_id"] == run.config_id)
            & (stored["run_id"] == run.run_id)
        ]
        for row in _records(mine):
            out.setdefault((run.run_id, str(row["instrument_id"])), []).append(row)
    return out


def _result(
    run: ScreenerRun,
    row: Mapping[str, Any],
    values: Sequence[Mapping[str, Any]],
    instrument: Instrument | None,
) -> ScreenResult:
    criteria = tuple(
        CriterionResult(
            str(v["criterion_id"]),
            str(v["field"]),
            str(v["mode"]),
            str(v["outcome"]),
            _value(v),
            _float(v.get("distance")),
        )
        for v in values
        if v["mode"] != COLUMN_MODE
    )
    columns = tuple(
        ResultColumn(str(v["criterion_id"]), _value(v)) for v in values if v["mode"] == COLUMN_MODE
    )
    flags = str(to_scalar(row.get("flags")) or "")
    return ScreenResult(
        run_id=run.run_id,
        config_id=run.config_id,
        instrument_id=str(row["instrument_id"]),
        instrument=instrument,
        rank=int(row["rank"]),
        decision=str(row["decision"]),
        score=_float(row.get("score")),
        tie_break=_float(row.get("tie_break")),
        reasons=str(to_scalar(row.get("reasons")) or ""),
        flags=tuple(f for f in flags.split(",") if f),
        criteria=criteria,
        columns=columns,
    )


def load_results(
    ctx: ReadContext, wanted: Mapping[str, Sequence[str]], runs: Sequence[ScreenerRun]
) -> dict[ResultKey, ScreenResult]:
    """The results of ``wanted`` (``{run id: instrument ids}``) among ``runs``, by (run id,
    instrument id); an instrument the run has no row for is left out."""
    ids = sorted({i for found in wanted.values() for i in found})
    if not ids:
        return {}
    values = _values(ctx, runs, ids)
    instruments = load_instruments(ctx, ids)
    out: dict[ResultKey, ScreenResult] = {}
    for run in runs:
        asked = set(wanted.get(run.run_id, ()))
        if not asked:
            continue
        rows: pd.DataFrame = run_rows(ctx, run)
        for row in _records(rows[rows["instrument_id"].isin(asked)]):
            iid = str(row["instrument_id"])
            found = values.get((run.run_id, iid), [])
            out[(run.run_id, iid)] = _result(run, row, found, instruments.get(iid))
    return out
