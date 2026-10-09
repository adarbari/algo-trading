"""The Builder's live preview (ADR 0029): an unsaved rule-screen draft resolved for a user and
evaluated on the request's session (``ReadContext.session``: the latest with daily bars unless a
date is asked for, ADR 0036) by the SAME ``RuleScreener.evaluate`` (``evaluate_screen``)
the nightly ``screen`` job runs, over the same selection, fields and coverage rules. Saves
nothing.

``preview_screen`` returns the run summary (passed, missing data by field, narrow misses), the
decision counts, the funnel per gating criterion in spec order, the coverage, the session used,
the top rows (every row that is not rejected and at least ``limit``, at most ``MAX_ROWS``,
so a screen with more picks than ``limit`` still shows each one; each with who the instrument
is, as the review table's rows: one table widget renders both) and, for a screener with a saved
run for that session, who the draft would pick that the run did not and the reverse
(``changes``, over every row; picked as ``read.screens.runs.is_picked`` says). The field frame
is cached (``preview.frame``), so an edit that keeps the field set re-evaluates in memory.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.core.model.screen_spec import Mode, ScreenSpec
from algotrade.core.time.calendar import last_closed_session
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_rule_draft
from algotrade.services.features import config_features
from algotrade.services.preview.frame import field_frame
from algotrade.services.read.context import ReadContext, ResultCache, open_context
from algotrade.services.read.screens.runs import is_picked, latest_run, run_rows
from algotrade.services.read.screens.screeners import (
    ScreenColumn,
    ScreenCriterion,
    load_screener,
)
from algotrade.services.screening.run import rule_run, settle_coverage
from algotrade.services.views import to_value
from algotrade.strategies.screeners.base import Decision
from algotrade.strategies.screeners.rules import Outcome, RuleRow, RuleScreener

MAX_ROWS = 1000  # the most rows one preview returns
DRAFT_ID = "preview"  # the screen id of a draft that names none
UNMANAGED = ("schedule",)  # a legacy key (ADR 0033), dropped from a draft


@dataclass(frozen=True)
class FunnelStep:
    """One gating criterion, in spec order: of the rows still in (every earlier gating
    criterion PASS or NEAR, or SOFT with no value), how many pass, miss narrowly, fail or have no
    value (a HARD criterion rejects it, a SOFT one only costs points: ADR 0030)."""

    criterion_id: str
    field: str
    mode: str
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
    name: str | None  # the company or fund name (the universe snapshot's)
    rank: int
    decision: str
    score: float | None
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
    missing: int  # gating values missing where the funnel reached them (a row counts per criterion)
    missing_reasons: dict[str, int]  # ``no <field>`` -> rows
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
class PreviewChanges:
    """The draft against the screener's saved run for the same session: the tickers it would
    pick that the run did not (``entered``) and the reverse (``left``), sorted."""

    run_id: str
    session: date
    entered: list[str]
    left: list[str]


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
    criteria: list[ScreenCriterion]  # the draft's, in funnel order (the table's headers)
    display_columns: list[ScreenColumn]  # the draft's ``[columns]``
    rows: list[PreviewRow]  # the top ``limit`` by rank
    cached: bool  # the field frame came from the in-process cache
    changes: PreviewChanges | None  # None: no saved run of this screener for ``session``


def draft_spec(document: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """The draft's screen id and the document to resolve (without a legacy schedule)."""
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
        keep = {Outcome.PASS, Outcome.NEAR}
        if criterion.mode is Mode.SOFT:  # no value only costs points: the row stays in
            keep.add(Outcome.MISSING)
        kept = [r for r in remaining if r.results[index].outcome in keep]
        steps.append(
            FunnelStep(
                criterion.id,
                criterion.field,
                criterion.mode.value,
                entering=len(remaining),
                passed=passed,
                near=near,
                failed=outcomes.count(Outcome.FAIL),
                missing=outcomes.count(Outcome.MISSING),
                remaining=len(kept),
            )
        )
        remaining = kept
    return steps


def _row(row: RuleRow, symbol: str | None, name: str | None) -> PreviewRow:
    return PreviewRow(
        instrument_id=row.instrument_id,
        symbol=symbol,
        name=name,
        rank=row.rank,
        decision=row.decision.value,
        score=row.score,
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


def preview_changes(
    ctx: ReadContext,
    who: UserContext,
    screener_id: str,
    session: date,
    rows: Sequence[RuleRow],
    symbols: Mapping[str, str],
) -> PreviewChanges | None:
    """``rows`` (the draft's, every one) against ``screener_id``'s saved run for ``session``
    (the read model's latest-run rule, as ``who`` sees the screener); None without one."""
    mine = open_context(ctx.reader, ctx.configs, who, session, ctx.cache)
    screener = load_screener(mine, screener_id)
    run = None if screener is None else latest_run(mine, screener.owner, screener_id).run
    if run is None:
        return None
    saved = run_rows(mine, run)
    before = {str(i) for i, d in zip(saved["instrument_id"], saved["decision"], strict=True)
              if is_picked(str(d))}  # fmt: skip
    after = {r.instrument_id for r in rows if is_picked(r.decision.value)}
    # Tickers by the frame's universe; one it does not name (snapshot drift) is left out.
    entered = sorted(symbols[i] for i in after - before if i in symbols)
    left = sorted(symbols[i] for i in before - after if i in symbols)
    return PreviewChanges(run.run_id, run.session, entered, left)


def preview_screen(
    ctx: ReadContext,
    frames: ResultCache,
    spec: Mapping[str, Any],
    user: str | None = None,
    limit: int = 50,
    now: datetime | None = None,
) -> ScreenPreview:
    """``spec`` (an unsaved draft rule screen, resolved for ``user``: default the context's)
    evaluated on ``ctx.session``. ``frames``: the field-frame cache (large, few entries: kept
    apart from ``ctx.cache`` so page reads never evict the frame an edit re-evaluates). Fails
    closed: an invalid draft is a ``ConfigurationError`` naming its path, and nothing is
    evaluated."""
    who = UserContext(validate_id("user", user if user is not None else ctx.user.user_id))
    name, document = draft_spec(spec)
    config = resolve_rule_draft(ctx.configs, name, who, document)
    rules, selection, screening = config.screen_spec, config.selection, config.screening
    if selection is None:  # a rule screen always resolves with one; never run without it
        raise ConfigurationError(f"{who.user_id}/{name}: a screener needs a selection")
    session, closed = ctx.session.date, last_closed_session(now or datetime.now(UTC))
    fields = {r.field for r in selection.where.rules()} | set(rules.fields())
    if selection.order_by:
        fields.add(selection.order_by)
    frame, cached = field_frame(
        ctx.reader,
        frames,
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
    run = settle_coverage(run, selected, frame.universe, session, screening, frame.missing)
    symbols, names = frame.symbols, frame.names
    kept = sum(1 for r in result.rows if r.decision is not Decision.REJECT)  # ranked first
    top = result.rows[: max(0, min(max(limit, kept), MAX_ROWS))]
    summary = result.summary
    steps = funnel(rules, result.rows)
    return ScreenPreview(
        screener_id=name,
        user=who.user_id,
        config_hash=config.hash,
        session=session,
        last_closed=closed,
        summary=PreviewSummary(
            rows=summary.rows,
            passed=summary.passed,
            missing=sum(s.missing for s in steps),
            missing_reasons={f"no {s.field}": s.missing for s in steps if s.missing},
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
        funnel=steps,
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
        criteria=[
            ScreenCriterion(c.id, c.field, c.mode.value, c.rule.op, c.rule.value)
            for c in rules.criteria
        ],
        display_columns=[ScreenColumn(n, f) for n, f in rules.columns],
        rows=[_row(r, symbols.get(r.instrument_id), names.get(r.instrument_id)) for r in top],
        cached=cached,
        changes=preview_changes(ctx, who, name, session, result.rows, symbols),
    )
