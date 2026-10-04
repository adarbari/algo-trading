"""The Builder's live preview (ADR 0029): an unsaved rule-screen draft resolved for a user and
evaluated on the latest closed session by the SAME ``RuleScreener.evaluate`` (``evaluate_screen``)
the nightly ``screen`` job runs, over the same selection, fields and coverage rules. Saves
nothing.

``preview_screen`` returns the run summary (passed, skipped by reason, narrow misses), the
decision counts, the funnel per gating criterion in spec order, the coverage, the session used
and the top ``limit`` rows. The field frame is cached (``preview.frame``), so an edit that
keeps the field set re-evaluates in memory.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.core.model.screen_spec import ScreenSpec
from algotrade.core.time.calendar import last_closed_session
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_rule_draft
from algotrade.services.explore.preview.frame import field_frame
from algotrade.services.explore.store import BARS, MAX_PAGE_SIZE, ReadStore, partition_for
from algotrade.services.features import config_features
from algotrade.services.screening.run import rule_run, settle_coverage
from algotrade.services.views import to_value
from algotrade.strategies.screeners.rules import Outcome, RuleRow, RuleScreener

DRAFT_ID = "preview"  # the screen id of a draft that names none
UNMANAGED = ("schedule",)  # when a screen runs never changes what it computes


@dataclass(frozen=True)
class FunnelStep:
    """One gating criterion, in spec order: of the rows still in (every earlier gating
    criterion PASS or NEAR), how many pass, miss narrowly, fail or have no value."""

    criterion_id: str
    field: str
    mode: str
    label: str | None
    entering: int
    passed: int
    near: int
    failed: int
    missing: int
    remaining: int  # passed + near: what the next step sees


@dataclass(frozen=True)
class CriterionValue:
    criterion_id: str
    field: str
    mode: str
    value: Any
    outcome: str  # PASS / NEAR / FAIL / MISSING
    distance: float | None
    normalised: float | None
    penalty: float


@dataclass(frozen=True)
class PreviewRow:
    instrument_id: str
    symbol: str | None
    rank: int
    decision: str
    score: float | None
    tier: str | None
    classification: str | None  # the spec's ``classify`` field (``class`` in the results)
    flags: list[str]
    reasons: list[str]
    columns: dict[str, Any]  # display name -> value
    criteria: list[CriterionValue]


@dataclass(frozen=True)
class NarrowMissRow:
    instrument_id: str
    criterion_id: str
    field: str
    value: Any
    threshold: float | None
    distance: float | None
    normalised: float | None


@dataclass(frozen=True)
class PreviewSummary:
    rows: int
    passed: int
    skipped: int
    skipped_reasons: dict[str, int]
    narrow_misses: list[NarrowMissRow]


@dataclass(frozen=True)
class PreviewCoverage:
    coverage: str  # COMPLETE / PARTIAL / UNIVERSE_INCOMPLETE / EMPTY_SELECTION
    base: int  # instruments the selection saw
    selected: int
    processed: int
    skipped: int
    coverage_pct: float
    min_coverage: float
    selection: dict[str, Any]  # the selection's audit (rules, unknown excluded, truncated)
    missing_tables: list[str]
    pre_snapshot: bool
    universe_snapshot: date


@dataclass(frozen=True)
class ScreenPreview:
    screener_id: str
    user: str
    config_hash: str
    session: date  # the session evaluated
    last_closed: date  # the latest closed exchange session (core.time.calendar)
    summary: PreviewSummary
    decisions: dict[str, int]
    funnel: list[FunnelStep]
    coverage: PreviewCoverage
    total: int  # rows evaluated (one per selected instrument)
    rows: list[PreviewRow]  # the top ``limit`` by rank
    cached: bool  # the field frame came from the in-process cache


def preview_session(store: ReadStore, now: datetime | None = None) -> tuple[date, date]:
    """(the session to preview, the latest closed session): the latest session with daily
    bars on or before the last closed one (a session whose nightly has not landed yet falls
    back to the previous stored one). ``NotFoundError`` before the first stored session."""
    closed = last_closed_session(now or datetime.now(UTC))
    return partition_for(store.reader, BARS, closed), closed


def draft_spec(document: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """The draft's screen id and the document to resolve (without the schedule)."""
    if not isinstance(document, Mapping):
        raise ConfigurationError("spec: a draft is a table")
    raw_id = document.get("id", DRAFT_ID)
    if not isinstance(raw_id, str):
        raise ConfigurationError("spec.id: expected a string")
    name = validate_id("screener", raw_id)
    return name, {k: v for k, v in document.items() if k not in UNMANAGED} | {"id": name}


def funnel(spec: ScreenSpec, rows: Sequence[RuleRow]) -> list[FunnelStep]:
    """Each gating criterion in spec order over the rows still in after the ones before."""
    remaining = list(rows)
    steps = []
    for index, criterion in enumerate(spec.criteria):
        if not criterion.mode.gating:
            continue
        outcomes = [row.results[index].outcome for row in remaining]
        passed, near = outcomes.count(Outcome.PASS), outcomes.count(Outcome.NEAR)
        steps.append(
            FunnelStep(
                criterion.id,
                criterion.field,
                criterion.mode.value,
                criterion.label,
                entering=len(remaining),
                passed=passed,
                near=near,
                failed=outcomes.count(Outcome.FAIL),
                missing=outcomes.count(Outcome.MISSING),
                remaining=passed + near,
            )
        )
        keep = (Outcome.PASS, Outcome.NEAR)
        remaining = [r for r in remaining if r.results[index].outcome in keep]
    return steps


def _row(row: RuleRow, symbol: str | None) -> PreviewRow:
    return PreviewRow(
        instrument_id=row.instrument_id,
        symbol=symbol,
        rank=row.rank,
        decision=row.decision.value,
        score=row.score,
        tier=row.tier,
        classification=row.klass,
        flags=list(row.flags),
        reasons=list(row.reasons),
        columns={name: to_value(value) for name, value in row.columns},
        criteria=[
            CriterionValue(
                r.criterion.id,
                r.criterion.field,
                r.criterion.mode.value,
                to_value(r.value),
                r.outcome.value,
                r.distance,
                r.normalised,
                r.penalty,
            )
            for r in row.results
        ],
    )


def preview_screen(
    store: ReadStore,
    spec: Mapping[str, Any],
    user: str | None = None,
    limit: int = 50,
    on: date | None = None,
    now: datetime | None = None,
) -> ScreenPreview:
    """``spec`` (an unsaved draft rule screen, resolved for ``user``: default the store's)
    evaluated on ``on`` (default: ``preview_session``). Fails closed: an invalid draft is a
    ``ConfigurationError`` naming its path, and nothing is evaluated."""
    who = UserContext(validate_id("user", user if user is not None else store.user.user_id))
    name, document = draft_spec(spec)
    config = resolve_rule_draft(store.configs, name, who, document)
    rules, selection, screening = config.screen_spec, config.selection, config.screening
    if selection is None:  # a rule screen always resolves with one; never run without it
        raise ConfigurationError(f"{who.user_id}/{name}: a screener needs a selection")
    if on is None:
        session, closed = preview_session(store, now)
    else:
        session, closed = on, last_closed_session(now or datetime.now(UTC))
    fields = {r.field for r in selection.where.rules()} | set(rules.fields())
    if selection.order_by:
        fields.add(selection.order_by)
    frame, cached = field_frame(
        store.reader,
        store.preview_cache,
        session,
        sorted(fields),
        config_features(config),
        config.features,
    )
    selected = frame.selected(selection)
    ids = list(selected.instruments)
    view = FeatureView(session, {i: frame.view.row(i) for i in ids})
    result = RuleScreener(rules).evaluate(view, frame.memo_for())
    run = rule_run(result, ids, screening)
    run = settle_coverage(run, selected, frame.universe, session, screening)
    symbols = frame.symbols
    top = result.rows[: max(0, min(limit, MAX_PAGE_SIZE))]
    summary = result.summary
    return ScreenPreview(
        screener_id=name,
        user=who.user_id,
        config_hash=config.hash,
        session=session,
        last_closed=closed,
        summary=PreviewSummary(
            rows=summary.rows,
            passed=summary.passed,
            skipped=summary.skipped,
            skipped_reasons=dict(summary.skipped_reasons),
            narrow_misses=[
                NarrowMissRow(
                    m.instrument_id,
                    m.criterion_id,
                    m.field,
                    to_value(m.value),
                    m.threshold,
                    m.distance,
                    m.normalised,
                )
                for m in summary.narrow_misses
            ],
        ),
        decisions=dict(summary.decisions),
        funnel=funnel(rules, result.rows),
        coverage=PreviewCoverage(
            coverage=run.coverage.value,
            base=selected.base,
            selected=len(ids),
            processed=run.processed,
            skipped=run.unique_instruments - run.processed,
            coverage_pct=round(run.coverage_pct, 4),
            min_coverage=screening.min_coverage,
            selection=selected.as_dict(),
            missing_tables=list(frame.missing),
            pre_snapshot=frame.pre_snapshot,
            universe_snapshot=frame.universe.snapshot_date,
        ),
        total=len(result.rows),
        rows=[_row(r, symbols.get(r.instrument_id)) for r in top],
        cached=cached,
    )
