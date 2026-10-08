"""Use case: run a registered screener for a session date and save an audited result.

A rule screen (``impl = "rules"``, ADR 0029) reads its spec's fields, is evaluated once by
``strategies.screeners.rules`` and writes ``results/rule_screen`` + ``rule_screen_values``
atomically; its run summary goes into the run record (``stats["summary"]``).

With ``[regime]`` enabled (ADR 0049) the session's regime label is read (``services.screening
.regime``) and the screening engine's gate PAUSES the picks of a screener that pauses in it
(or of every gated screener, one with a ``pause_in``, when the label is unknown: fail
closed); every result row carries the session's ``regime`` and ``size_multiplier``, and the
run record the gate's summary.

With ``sources`` given (ADR 0054) the session's chain status is read and the stale chains the
chains acceptance check tolerated (``data.chains.tolerated_stale``) are EXCLUDED from the run
(a not-processed row of one becomes ``Decision.EXCLUDED`` with the reason; out of the coverage
denominator) instead of lowering coverage; the audit says how many and why."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.config.site.settings import ScreeningSettings, SourcesSettings
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.chains import chain_status, tolerated_stale
from algotrade.data.reference import Universe, load_universe
from algotrade.engines.screening.exclusions import exclude_rule_result
from algotrade.engines.screening.gate import RegimeGate, gate_rule_result
from algotrade.engines.screening.runner import RunCoverage, ScreenRun, audit_rows, run_screen
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import config_features
from algotrade.services.screening.regime import market_names, regime_gate, session_market
from algotrade.services.screening.rule_results import Stamp, rule_frames
from algotrade.services.selection import fields_view, select
from algotrade.services.views import feature_view
from algotrade.storage.runs import start_run
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.strategies.screeners.registry import create_screener
from algotrade.strategies.screeners.rules import RULES, RuleScreener, RuleScreenResult


def run_job_name(config_id: str, user: str) -> str:
    """The run-record ``job`` of a screen of ``config_id`` for ``user``."""
    return f"screen-{config_id}-{user}"


@dataclass(frozen=True)
class ScreenOutcome:
    run_id: str
    session_date: date
    run: ScreenRun
    universe: Universe
    audit: dict[str, object]
    rules: RuleScreenResult | None = None  # a rule screen's ranked rows and run summary


def rows_frame(run: ScreenRun, session_date: date, run_id: str, now: datetime) -> pd.DataFrame:
    records = [
        {
            "instrument_id": r.instrument_id,
            "decision": r.decision.value,
            "score": r.score,
            "reasons": "; ".join(r.reasons),
            **r.values,
        }
        for r in run.rows
    ]
    frame = pd.DataFrame.from_records(records)
    frame["session_date"] = session_date
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = f"screener:{run.screener}"
    frame["run_id"] = run_id
    return frame


def _with_coverage(run: ScreenRun, coverage: RunCoverage) -> ScreenRun:
    return ScreenRun(
        run.screener,
        run.rows,
        run.universe_rows,
        run.unique_instruments,
        run.duplicates_removed,
        coverage,
    )


def screen_rules(
    reader: StoreReader,
    config: ResolvedConfig,
    session_date: date,
    selected: SelectionResult,
    features: FeatureSet,
    gate: RegimeGate | None = None,
    excluded: Mapping[str, str] | None = None,
) -> tuple[ScreenRun, RuleScreenResult, tuple[str, ...]]:
    """A rule screen over the selected instruments: the spec's fields read for the session
    (missing values stay missing: a HARD criterion rejects the row), evaluated once, through
    the regime ``gate`` and the ``excluded`` names (ADR 0054), then audited. Also returns the
    tables that had no rows for the session."""
    screener = RuleScreener(config.screen_spec)
    ids = list(selected.instruments)
    view, source = fields_view(reader, screener.spec.fields(), session_date, ids, features=features)
    result = exclude_rule_result(gate_rule_result(screener.evaluate(view), gate), excluded or {})
    return rule_run(result, ids, config.screening), result, source.missing


def rule_run(result: RuleScreenResult, ids: list[str], screening: ScreeningSettings) -> ScreenRun:
    """A rule screen's rows audited against the selected ``ids`` (one row each) and graded."""
    rows = [r.screen_row() for r in result.rows]
    return audit_rows(RULES, rows, ids, screening.min_coverage)


def settle_coverage(
    run: ScreenRun,
    selected: SelectionResult,
    universe: Universe,
    session_date: date,
    screening: ScreeningSettings,
    missing_tables: Sequence[str] = (),
) -> ScreenRun:
    """The run's final coverage: ``EMPTY_SELECTION`` when the selection matched nothing,
    ``PARTIAL`` when a table the screen reads had no rows for the session (every row would
    read as missing data, which a HARD criterion rejects: ADR 0030, never a clean run), and
    ``UNIVERSE_INCOMPLETE`` when a complete run read a universe older than allowed."""
    if selected.empty:
        return _with_coverage(run, RunCoverage.EMPTY_SELECTION)
    if missing_tables and run.coverage is RunCoverage.COMPLETE:
        run = _with_coverage(run, RunCoverage.PARTIAL)
    if run.coverage is RunCoverage.COMPLETE and universe.is_stale(
        session_date, screening.max_universe_age_days
    ):
        return _with_coverage(run, RunCoverage.UNIVERSE_INCOMPLETE)
    return run


def _write(
    writer: ResultWriter,
    config: ResolvedConfig,
    run: ScreenRun,
    rules: RuleScreenResult | None,
    stamp: Stamp,
) -> None:
    if not run.rows:
        return
    if rules is None:
        frame = rows_frame(run, stamp.session_date, stamp.run_id, stamp.knowledge_ts)
        frame["user_id"], frame["config_id"], frame["config_hash"] = (
            stamp.user_id,
            stamp.config_id,
            stamp.config_hash,
        )
        frame["regime"], frame["size_multiplier"] = stamp.regime, stamp.size_multiplier
        writer.write_result(config.config.impl, stamp.session_date, stamp.run_id, frame)
        return
    with writer.publishing(stamp.run_id, stamp.knowledge_ts):  # both tables or neither
        for name, frame in rule_frames(rules, stamp).items():
            writer.write_result(name, stamp.session_date, stamp.run_id, frame, pending=True)


def _tolerated_stale(
    reader: StoreReader, session_date: date, now: datetime, sources: SourcesSettings | None
) -> Mapping[str, str]:
    """The stale chains the chains gate tolerated for the session, as the run knew them
    (``as_of`` its time; nothing without ``sources``: fail closed)."""
    if sources is None:
        return {}
    return tolerated_stale(chain_status(reader, session_date, as_of=now), sources)


def run_screener(
    reader: StoreReader,
    writer: ResultWriter,
    config: ResolvedConfig,
    session_date: date,
    now: datetime | None = None,
    sources: SourcesSettings | None = None,
) -> ScreenOutcome:
    """Select -> screen -> audit -> save, for one resolved screener config and user."""
    now = now or datetime.now(UTC)
    if config.config.kind != "screener":
        raise ConfigurationError(f"{config.config.id} is a {config.config.kind}, not a screener")
    if config.selection is None:
        raise ConfigurationError(f"{config.config.id}: a screener needs a selection")
    screening = config.screening
    universe = load_universe(reader, session_date)
    features = config_features(config)
    selected = select(reader, config.selection, session_date, features=features)
    rules: RuleScreenResult | None = None
    missing_tables: tuple[str, ...] = ()
    market = session_market(reader, market_names(config), session_date)
    gate = regime_gate(config, market)
    excluded = _tolerated_stale(reader, session_date, now, sources)
    if config.config.impl == RULES:
        run, rules, missing_tables = screen_rules(
            reader, config, session_date, selected, features, gate, excluded
        )
    else:
        screener = create_screener(config.config.impl, params=config.config.params)
        view = feature_view(
            reader, screener.requires, session_date, selected.instruments, market=market
        )
        ids = list(selected.instruments)
        run = run_screen(screener, view, ids, screening.min_coverage, gate, excluded)
    run = settle_coverage(run, selected, universe, session_date, screening, missing_tables)
    user = config.user.user_id
    record = start_run(run_job_name(config.config.id, user), session_date, now)
    run_id = record.run_id
    audit = {
        **run.audit(),
        "user": user,
        "config_id": config.config.id,
        "config_hash": config.hash,
        "config_version": rules.spec.version if rules else None,
        "config_layers": list(config.layers),
        "selection": selected.as_dict(),
        "universe_snapshot": universe.snapshot_date.isoformat(),
        "universe_version": universe.version,
        "universe_last_verified": universe.last_verified.isoformat()
        if universe.last_verified
        else None,
        "universe_rows_loaded": universe.rows_loaded,
        # The universe came from a snapshot after the session: results carry survivorship bias.
        "universe_pre_snapshot": universe.pre_snapshot,
    }
    if gate is not None:  # ADR 0049: the label, the size and whether picks were held back
        audit["regime"] = {
            "label": gate.regime,
            "size_multiplier": gate.size_multiplier,
            "paused_reason": gate.reason,
        }
    if rules is not None:  # the run summary (ADR 0029): passed, decisions, narrow misses
        audit["summary"] = rules.summary.as_dict()
        audit["missing_tables"] = list(missing_tables)
    version = rules.spec.version if rules else None
    stamp = Stamp(session_date, run_id, now, user, config.config.id, config.hash, version)
    if gate is not None:
        stamp = replace(stamp, regime=gate.regime, size_multiplier=gate.size_multiplier)
    _write(writer, config, run, rules, stamp)
    complete = run.coverage is RunCoverage.COMPLETE
    writer.save_run(record.finish(now, complete=complete, stats=audit))
    return ScreenOutcome(run_id, session_date, run, universe, audit, rules)
