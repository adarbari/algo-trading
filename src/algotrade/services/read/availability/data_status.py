"""``DataStatus``: how complete the data of the session a read serves is, in one object a trader
reads without the admin's ops pages (the top bar's data-status pill, ADR 0062 amendment).

It reads run records only, never a partition: Prices and Fundamentals are the
cells (names covered of names applicable, by tier) of the ``coverage_price_stats.close`` and
``coverage_fundamentals.shares_outstanding`` checks the nightly's ``rollups`` step stored (the
newest record that holds them: a retry carries the step over without its checks); Options chains
are the chains task's coverage of the session (``run_items.chain_coverage``, the admin read's
function). Each is a ``DatasetStatus``: chains are graded by ``share_status`` (the admin
completeness grid's rule), a coverage dataset by its rule's own verdict (every tier within its
minimums and the check PASS: COMPLETE; a breach or a WARN / FAIL: PARTIAL; nothing covered:
MISSING), since a tier's minimum is not 98% (fundamentals cover about 95% of operating
companies); a dataset whose record is missing is ``UNKNOWN`` with a ``NOT_RUN``
``Unavailable``, never 0%. ``DataState`` is
decided here, on the server, from the session
(``Session.complete``, ``Session.newer``) and the datasets; ``affected_screeners`` counts the
viewer's screeners whose run for the session is missing, PARTIAL or went without a required
table (a gap in an optional table alone does not count). Describes exactly ``ctx.session.date``
(ADR 0036); ``knowledge_ts`` is ``Session.cutoff``. The cause chain behind an ``UNKNOWN`` is
admin-only (ADR 0056); the public fields name no step or table."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from algotrade.services.read.availability.cause import Unavailable, UnavailableKind, run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.runs import load_latest_runs
from algotrade.services.read.screens.screeners import load_screeners
from algotrade.services.read.session import NIGHTLY, NewerState
from algotrade.services.run_items import CHAINS_JOB, chain_coverage

__all__ = [
    "COMPLETE_SHARE",
    "DataState",
    "DataStatus",
    "DatasetName",
    "DatasetState",
    "DatasetStatus",
    "check_data",
    "check_name",
    "load_data_status",
    "share_status",
]

COMPLETE_SHARE = 0.98
ROLLUPS_STEP = "rollups"  # the nightly step whose acceptance is the coverage of the key features
# The coverage rules (sources.toml [quality.coverage.*]) the datasets are read from: the session's
# close (a bars run's items are keyed by day, not by name) and the SEC share count.
PRICES_FEATURE = "price_stats.close"
FUNDAMENTALS_FEATURE = "fundamentals.shares_outstanding"


class DatasetName(StrEnum):
    """The datasets the pill reports."""

    PRICES = "PRICES"
    OPTIONS_CHAINS = "OPTIONS_CHAINS"
    FUNDAMENTALS = "FUNDAMENTALS"


class DatasetState(StrEnum):
    """How much of a dataset the session has."""

    COMPLETE = "COMPLETE"  # within its minimums (chains: at least 98% of what was expected)
    PARTIAL = "PARTIAL"  # less, and some
    MISSING = "MISSING"  # a record, and none of it
    UNKNOWN = "UNKNOWN"  # no record for the session: not measured, never 0%


class DataState(StrEnum):
    """What the session's data amounts to, for the pill."""

    COMPLETE = "COMPLETE"  # the session is complete and every dataset is
    PARTIAL = "PARTIAL"  # the session is not complete, or a dataset is not
    NEXT_PROCESSING = "NEXT_PROCESSING"  # a newer session is being built or published
    NEXT_FAILED_SHOWING_PREVIOUS = "NEXT_FAILED_SHOWING_PREVIOUS"  # its build failed, retrying


@dataclass(frozen=True)
class DatasetStatus:
    """One dataset on the session: ``present`` of ``expected`` (``share``), graded as
    ``status``; ``unavailable`` says in public words why it is ``UNKNOWN`` (empty otherwise)."""

    name: DatasetName
    status: DatasetState
    present: int | None
    expected: int | None
    share: float | None
    unavailable: tuple[Unavailable, ...] = ()


@dataclass(frozen=True)
class DataStatus:
    """The session's data state with its datasets and how many of the viewer's
    ``total_screeners`` it ``affected_screeners``; ``knowledge_ts`` when the session completed
    (None: it has not)."""

    session: date
    state: DataState
    knowledge_ts: datetime | None
    datasets: tuple[DatasetStatus, ...]
    affected_screeners: int
    total_screeners: int


def share_status(present: int, expected: int | None) -> str:
    """COMPLETE, PARTIAL or MISSING for ``present`` rows of ``expected``: COMPLETE at
    ``COMPLETE_SHARE`` or more (or nothing to compare with), MISSING with none."""
    if present == 0:
        return "MISSING"
    if expected and present < COMPLETE_SHARE * expected:
        return "PARTIAL"
    return "COMPLETE"


def _measured(name: DatasetName, present: int, expected: int) -> DatasetStatus:
    status = DatasetState(share_status(present, expected))
    return DatasetStatus(name, status, present, expected, present / expected)


def _unknown(name: DatasetName, job: str, day: date) -> DatasetStatus:
    cause = run_cause(job, f"no {job} record for {day.isoformat()}", day)
    gap = Unavailable(UnavailableKind.NOT_RUN, (), cause)
    return DatasetStatus(name, DatasetState.UNKNOWN, None, None, None, (gap,))


def check_name(feature: str) -> str:
    """The acceptance check of a coverage rule (``<group>.<column>``): the ingestion's
    ``coverage_<feature>`` (apps/ingestion tasks/maintenance/coverage.py)."""
    return f"coverage_{feature}"


def check_data(ctx: ReadContext, feature: str, key: str) -> tuple[str, Mapping[str, Any]] | None:
    """The run id and ``data`` of the coverage check of ``feature`` in the newest nightly record
    of the session whose ``rollups`` step holds it with a ``key`` in its data (a retry carries
    the step over without its checks; a record from before ``key`` existed lacks it); None when
    no record does."""
    for record in sorted(
        ctx.reader.runs(NIGHTLY, ctx.session.date), key=lambda r: r.started_at, reverse=True
    ):
        steps = record.stats.get("steps")
        step = steps.get(ROLLUPS_STEP) if isinstance(steps, Mapping) else None
        checks = step.get("checks") if isinstance(step, Mapping) else None
        for c in checks if isinstance(checks, list) else []:
            data = c.get("data") if isinstance(c, Mapping) else None
            if c.get("name") == check_name(feature) and isinstance(data, Mapping) and key in data:
                return record.run_id, data
    return None


def _cells_of(steps: Any, name: str) -> tuple[DatasetState, int, int] | None:
    """The dataset from check ``name`` on the nightly's ``rollups`` step: ``present`` of
    ``expected`` for display, graded by the rule's own verdict (every cell ``ok`` and the check
    PASS: COMPLETE; a breaching tier or a WARN / FAIL: PARTIAL; nothing covered: MISSING). None:
    the step holds no such check (a retry carries the step over without its checks)."""
    step = steps.get(ROLLUPS_STEP) if isinstance(steps, Mapping) else None
    checks = step.get("checks") if isinstance(step, Mapping) else None
    covered = applicable = 0
    found, whole = False, True
    for c in checks if isinstance(checks, list) else []:
        data = c.get("data") if isinstance(c, Mapping) else None
        if c.get("name") != name or not isinstance(data, Mapping):
            continue
        whole = whole and c.get("status", "PASS") == "PASS"
        for cell in data.get("cells", []):
            covered += int(cell.get("covered", 0))
            applicable += int(cell.get("applicable", 0))
            whole = whole and bool(cell.get("ok", True))
            found = True
    if not found or not applicable:
        return None
    state = (
        DatasetState.MISSING
        if covered == 0
        else DatasetState.COMPLETE
        if whole
        else DatasetState.PARTIAL
    )
    return state, covered, applicable


def _from_coverage(ctx: ReadContext, name: DatasetName, feature: str) -> DatasetStatus:
    """The dataset from the coverage check of ``feature``, read from the newest nightly record
    of the session whose ``rollups`` step holds it (per name, by tier)."""
    day = ctx.session.date
    for record in sorted(ctx.reader.runs(NIGHTLY, day), key=lambda r: r.started_at, reverse=True):
        found = _cells_of(record.stats.get("steps"), check_name(feature))
        if found is not None:
            state, covered, applicable = found
            return DatasetStatus(name, state, covered, applicable, covered / applicable)
    return _unknown(name, NIGHTLY, day)


def _prices(ctx: ReadContext) -> DatasetStatus:
    return _from_coverage(ctx, DatasetName.PRICES, PRICES_FEATURE)


def _fundamentals(ctx: ReadContext) -> DatasetStatus:
    return _from_coverage(ctx, DatasetName.FUNDAMENTALS, FUNDAMENTALS_FEATURE)


def _options(ctx: ReadContext) -> DatasetStatus:
    day = ctx.session.date
    found = chain_coverage(ctx.reader.runs(CHAINS_JOB, day), [day])
    if found is None or not found.total:
        return _unknown(DatasetName.OPTIONS_CHAINS, CHAINS_JOB, day)
    return _measured(DatasetName.OPTIONS_CHAINS, found.ok, found.total)


def _screeners(ctx: ReadContext) -> tuple[int, int]:
    """-> (affected, total) over the viewer's screeners: no run for the session, a PARTIAL run,
    or a run without a required table (``missing_optional_tables`` alone is not a gap)."""
    keys = [(s.owner, s.id) for s in load_screeners(ctx)]
    if not keys:
        return 0, 0
    found = load_latest_runs(ctx, keys)
    affected = 0
    for key in keys:
        run = found[key].run
        if run is None or run.coverage == "PARTIAL" or run.missing_tables:
            affected += 1
    return affected, len(keys)


def _state(ctx: ReadContext, datasets: tuple[DatasetStatus, ...]) -> DataState:
    newer = ctx.session.newer
    if newer is not None and newer.state is NewerState.FAILED_RETRYING:
        return DataState.NEXT_FAILED_SHOWING_PREVIOUS
    if newer is not None:
        return DataState.NEXT_PROCESSING
    whole = all(d.status is DatasetState.COMPLETE for d in datasets)
    return DataState.COMPLETE if ctx.session.complete and whole else DataState.PARTIAL


def load_data_status(ctx: ReadContext) -> DataStatus:
    """The data status of exactly ``ctx.session.date``, from run records alone."""
    datasets = (_prices(ctx), _options(ctx), _fundamentals(ctx))
    affected, total = _screeners(ctx)
    return DataStatus(
        ctx.session.date, _state(ctx, datasets), ctx.session.cutoff, datasets, affected, total
    )
