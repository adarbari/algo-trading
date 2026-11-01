"""The historical exit rule a share setup publishes for a pick (ADR 0083 decision 3): ``ExitRule``
and ``load_exit_rule``.

The *stop* is the drawdown that ``stop_percentile`` (80%) of the setup's winning trades never
exceeded: the percentile of ``edge_trades.max_drawdown`` (a fraction of the entry reference, the
window's dip) over the ``hit`` long trades of the verdict's basis in the canonical run, read only
through ``runs.load_run_trades`` (which keeps ``oos_hidden`` and tells PRUNED from NOT_STORED).
With fewer than ``min_winners`` such trades the stop is the fallback, ``atr_multiple`` x
``momentum.atr_14`` of the name at the session. The *hold* is the verdict's stored
``basis_horizon``. A setup that declares its own stop publishes it (``declared``: the hook the
declared share exits of E3c fill); the percentile applies only without one.

Point in time at the served session S: the canonical run must end by S (``range_to <= S``) and
only trades that exited by S count. Nothing is filled: a missing input is an ``Unknown`` with its
reason, never an older value. The rule is a reading of the evaluation's own winners and never feeds
back into it (so it is not a judge input and not in the verdict fingerprint)."""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from algotrade.config.edges.positions.exit_rule import ExitRuleSettings
from algotrade.config.site.settings import site_document
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.verdict import (
    EdgeSummary,
    load_edge_summary,
    load_stored_summary,
)
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

ATR = "momentum.atr_14"  # the fallback's catalogue field (usd per share)


class StopKind(StrEnum):
    HISTORY = "HISTORY"  # the percentile of the basis's winners' adverse moves
    FALLBACK = "FALLBACK"  # atr_multiple x ATR(14): not from this setup's history
    DECLARED = "DECLARED"  # the setup's own declared stop, published as it is


@dataclass(frozen=True)
class Stop:
    """A stop. ``fraction``: how far below the entry reference close (HISTORY, DECLARED); ``atr``
    and ``multiple``: the ATR(14) in usd per share and its multiple (FALLBACK, the distance is
    their product). ``winners``: the winning trades a HISTORY stop rests on; ``beyond``: the
    share of them that went past it (1 - the percentile)."""

    kind: StopKind
    fraction: float | None = None
    atr: float | None = None
    multiple: float | None = None
    winners: int | None = None
    beyond: float | None = None


@dataclass(frozen=True)
class ExitRule:
    """A setup's exit rule at the served session: the ``stop`` and the ``hold`` in sessions (the
    verdict's basis horizon), each None only with the ``unknown`` that says why. ``winners``: the
    basis's winning long trades read (0 when none), whichever stop was published."""

    edge_id: str
    stop: Stop | None
    hold_sessions: int | None
    unknown: Unknown | None = None
    winners: int = 0
    in_sample_only: bool = False  # the canonical run hides its out-of-sample trades: not read


def _unknown(edge: Edge, code: UnknownCode, why: str) -> Unknown:
    return Unknown(code, run_cause(edge.id, why))


def history_stop(dips: list[float], share: float) -> Stop:
    """The stop of ``dips`` (the winners' adverse moves): the smallest observed dip that ``share``
    of them did not exceed (numpy's ``inverted_cdf``: an observed value, never an interpolated
    one), with the real share that went past it (ties make it differ from ``1 - share``)."""
    values = np.asarray(dips, dtype=float)
    stop = float(np.quantile(values, share, method="inverted_cdf"))
    return Stop(
        StopKind.HISTORY, fraction=stop, winners=len(dips), beyond=float((values > stop).mean())
    )


def _settings(ctx: ReadContext) -> ExitRuleSettings:
    found = ExitRuleSettings.from_document(site_document(ctx.configs.load, "verdict"))
    if found is None:
        raise ConfigurationError("verdict.toml has no [exit_rule] section")
    return found


def _fallback(
    ctx: ReadContext, edge: Edge, instrument_id: str | None, multiple: float, winners: int
) -> tuple[Stop | None, Unknown | None]:
    if instrument_id is None:
        why = f"only {winners} winning trades and no name to take the fallback from"
        return None, _unknown(edge, UnknownCode.NOT_APPLICABLE, why)
    cell = load_feature_values(ctx, [instrument_id], [ATR])[instrument_id][0]
    if cell.value is None:
        return None, cell.unknown
    return Stop(StopKind.FALLBACK, atr=float(cell.value), multiple=multiple, winners=winners), None


def _from_history(
    ctx: ReadContext, edge: Edge, run: runs.EdgeRun, summary: EdgeSummary, instrument_id: str | None
) -> ExitRule:
    """The percentile stop of the basis's winners, else the ATR fallback (the rules of the module
    docstring: a ledger the viewer's licences do not cover, or that is long-only, is UNKNOWN)."""
    screener, horizon, day = (
        summary.basis_screener or "",
        summary.basis_horizon or 0,
        ctx.session.date,
    )
    ledger = runs.load_run_trades(ctx, run, variant=screener, horizon=horizon)
    unknown = ledger.unknown
    if unknown is None and ledger.licence not in (None, "", runs.OPEN, *ctx.licences):
        why = f"the winners' outcomes are under the {ledger.licence} data licence"
        unknown = _unknown(edge, UnknownCode.LICENCE, why)
    known = [t for t in ledger.rows if t.exit_session is not None and t.exit_session <= day]
    if unknown is None and any(t.side != "long" for t in known):
        why = "the exit rule is published for long picks only"
        unknown = _unknown(edge, UnknownCode.NOT_APPLICABLE, why)
    if unknown is not None:
        return ExitRule(edge.id, None, horizon, unknown, in_sample_only=run.oos_hidden)
    dips = [t.max_drawdown for t in known if t.hit is True and t.max_drawdown is not None]
    t = _settings(ctx)
    if len(dips) >= t.min_winners:
        stop = history_stop(dips, t.stop_percentile)
        return ExitRule(edge.id, stop, horizon, winners=len(dips), in_sample_only=run.oos_hidden)
    fallback, unknown = _fallback(ctx, edge, instrument_id, t.atr_multiple, len(dips))
    return ExitRule(edge.id, fallback, horizon, unknown, len(dips), run.oos_hidden)


def exit_rule_at(
    ctx: ReadContext,
    edge: Edge,
    instrument_id: str | None = None,
    declared: Stop | None = None,
    bounded: bool = False,
) -> ExitRule:
    """The exit rule of ``edge`` at ``ctx.session``; ``instrument_id``: the pick, for the ATR
    fallback; ``declared``: the setup's own stop, published as it is when given. Nothing, the
    hold included, is read from a canonical run that ends after the session. ``bounded``: the
    canonical run is the latest committed on or before the session (as Ideas reads the verdict,
    ``runs.load_canonical_run``), so the rule and the verdict it sits beside name one run."""
    canonical = (
        runs.load_canonical_run(ctx, edge, True) if bounded else runs.load_canonical_run(ctx, edge)
    )
    run = canonical.run
    if run is None:
        return ExitRule(edge.id, None, None, canonical.not_run)
    if run.range_to > ctx.session.date:  # its verdict, basis and ledger are not known then
        why = f"the canonical run ends {run.range_to}, after the session {ctx.session.date}"
        return ExitRule(edge.id, None, None, _unknown(edge, UnknownCode.NOT_RUN, why))
    summary = (
        load_stored_summary(ctx, edge, bounded=True) if bounded else None
    ) or load_edge_summary(ctx, edge)
    if summary.basis_screener is None or summary.basis_horizon is None:
        why = f"{edge.id} has no verdict basis ({summary.result})"
        return ExitRule(edge.id, None, None, _unknown(edge, UnknownCode.NOT_RUN, why))
    if declared is not None:
        return ExitRule(edge.id, declared, summary.basis_horizon)
    return _from_history(ctx, edge, run, summary, instrument_id)


def load_exit_rule(
    ctx: ReadContext | None,
    edge: Edge,
    instrument_id: str | None = None,
    declared: Stop | None = None,
) -> ExitRule | None:
    """``exit_rule_at`` for the served session (None: no session is served)."""
    return None if ctx is None else exit_rule_at(ctx, edge, instrument_id, declared)
