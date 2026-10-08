"""The data checks of one session for the Admin pages: the nightly data-quality checks
(``QualityReport``, from the session's ``data_quality`` run record) and the live verification
of our values against IBKR's (``Verification``, the session's ``verification/ibkr`` partition).

Both for exactly ``ctx.session.date`` (ADR 0036): no data-quality run for the session is
``NOT_RUN``, no verification partition is ``NO_PARTITION``; never an earlier session's."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.values import Unknown, UnknownCode, stored_values

QUALITY = "data_quality"  # the job of the nightly data-quality checks
VERIFICATION = "verification/ibkr"  # our values vs IBKR's (the ``verify`` task), one row per check
VERIFY_STATUSES = ("PASS", "WARN", "FAIL", "NA")
MAX_FAILING = 50


@dataclass(frozen=True)
class QualityCheck:
    """One check: ``status`` PASS, WARN or FAIL; ``detail`` what was measured, against which
    rule."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class QualityReport:
    """The session's data-quality run (the latest, when it ran twice): ``status`` the run's
    (complete, partial, failed); ``unknown`` NOT_RUN when it has none (then no run id, no
    checks)."""

    session: date
    run_id: str | None
    status: str | None
    finished_at: datetime | None
    checks: tuple[QualityCheck, ...]
    unknown: Unknown | None


def load_quality(ctx: ReadContext) -> QualityReport:
    """The data-quality checks of the latest ``data_quality`` run for ``ctx.session.date``."""
    day = ctx.session.date
    found = ctx.reader.runs(QUALITY, day)
    if not found:
        message = f"no {QUALITY} run for {day.isoformat()}"
        absent = Unknown(UnknownCode.NOT_RUN, run_cause(QUALITY, message, day))
        return QualityReport(day, None, None, None, (), absent)
    run = max(found, key=lambda r: r.started_at)
    stored = run.stats.get("checks")
    checks = tuple(
        QualityCheck(str(c.get("name", "")), str(c.get("status", "")), str(c.get("detail", "")))
        for c in (stored if isinstance(stored, list) else [])
        if isinstance(c, dict)
    ) or tuple(QualityCheck(name, str(status), "") for name, status in run.items.items())
    return QualityReport(day, run.run_id, run.status.value, run.finished_at, checks, None)


@dataclass(frozen=True)
class CheckCounts:
    """Rows per status (PASS / WARN / FAIL / NA) of one check (close, hv20, iv30, ...)."""

    check: str
    counts: dict[str, int]


@dataclass(frozen=True)
class Verification:
    """The session's live verification vs IBKR: ``counts`` rows per status over every row,
    ``by_check`` most failures first, ``failing`` FAIL then WARN rows (at most 50), largest
    diff first; ``unknown`` NO_PARTITION when it did not run for the session."""

    session: date
    run_ids: tuple[str, ...]
    instruments: int
    counts: dict[str, int]
    by_check: tuple[CheckCounts, ...]
    failing: tuple[dict[str, Any], ...]
    unknown: Unknown | None


def _counts(statuses: "pd.Series[Any]") -> dict[str, int]:
    found = statuses.astype(str).value_counts()
    return {s: int(found.get(s, 0)) for s in VERIFY_STATUSES}


def load_verification(ctx: ReadContext) -> Verification:
    """The ``verification/ibkr`` rows of ``ctx.session.date``: counts by status and by check,
    and the failing rows."""
    frame = partition(ctx, VERIFICATION)
    if isinstance(frame, Unknown):
        return Verification(ctx.session.date, (), 0, {}, (), (), frame)
    by_check = sorted(
        (CheckCounts(str(c), _counts(rows["status"])) for c, rows in frame.groupby("check")),
        key=lambda c: (-c.counts["FAIL"], -c.counts["WARN"], c.check),
    )
    rank = {"FAIL": 0, "WARN": 1}
    bad = frame[frame["status"].isin(list(rank))].assign(
        _rank=lambda f: f["status"].map(rank), _size=lambda f: f["diff"].abs()
    )
    bad = bad.sort_values(["_rank", "_size", "symbol"], ascending=[True, False, True])
    failing = bad.drop(columns=["_rank", "_size"]).head(MAX_FAILING).to_dict("records")
    return Verification(
        session=ctx.session.date,
        run_ids=tuple(sorted(map(str, frame["run_id"].unique()))),
        instruments=int(frame["instrument_id"].nunique()),
        counts=_counts(frame["status"]),
        by_check=tuple(by_check),
        failing=tuple(stored_values(r) for r in failing),
        unknown=None,
    )
