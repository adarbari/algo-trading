"""Evaluate one edge over a range of sessions (ADR 0053 decisions 5 to 7, ``docs/edges-plan.md``).

For each horizon the edge stores, the start sessions of its schedule (``sessions``) are screened
for every listed screener and baseline (``picks``: only what was known at the session), and the
picks, the eligible names and the screener's ranking are joined to the closed outcomes read as
of the run's start (``hit.apply_outcome``) and measured per slice (``measures``). **This is the
only module that reads outcomes** (``read_outcomes``; the picks never see one: a fitness test
checks both). A window not closed has no outcome row and is excluded, never a miss; a session
with no closed window at all is counted in ``unclosed_sessions``.

The deflated Sharpe ratio counts every distinct (variant, config hash, horizon) tried in
earlier runs of the edge plus this one (the trial log, ``results.py``); the probability of
backtest overfitting compares the variants' per-session pick means over the same sessions.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from functools import partial
from typing import Any

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import Selection, parse_selection
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.data.outcomes import read_outcomes
from algotrade.quant.edge_statistics import deflated_sharpe, pbo_cscv
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.hit import (
    IMPLIED_VOL_FIELD,
    apply_outcome,
    needs_implied_vol,
)
from algotrade.services.evaluation.cross_section.measures import (
    SessionStat,
    Slice,
    SliceMeasure,
    decile_means,
    slice_measures,
)
from algotrade.services.evaluation.cross_section.picks import RankedRun, screen_variant
from algotrade.services.evaluation.cross_section.picks import eligible as eligible_names
from algotrade.services.evaluation.cross_section.sessions import edge_sessions
from algotrade.services.screening.regime import session_market
from algotrade.services.selection import fields_view
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.tables.result_writer import ResultWriter

HARNESS_VERSION = 1
BENCHMARK = "SPY"  # outcomes are read over SPY for every edge: returns and vols ignore it
PBO_SPLITS = 16
UNKNOWN = "UNKNOWN"
SELECTIONS = "selections"


@dataclass(frozen=True)
class Variant:
    id: str
    role: str  # "screener" | "baseline"
    config: ResolvedConfig


@dataclass(frozen=True)
class VariantResult:
    variant: str
    role: str
    config_hash: str
    horizon: int
    stats: tuple[SessionStat, ...]
    measures: tuple[SliceMeasure, ...]


@dataclass(frozen=True)
class EdgeEvaluation:
    edge_id: str
    run_hash: str
    benchmark: str  # the edge document's: "SPY" or "none"
    start: date
    end: date
    as_of: datetime
    snapshot: date | None  # the first (here: earliest read) universe snapshot
    results: tuple[VariantResult, ...]
    trials: int
    start_sessions: Mapping[int, int]  # horizon -> start sessions the schedule gave
    unclosed_sessions: Mapping[int, int]  # horizon -> of those, sessions with no closed window


def run_hash(
    edge: Edge, variants: Sequence[Variant], start: date, end: date, as_of: datetime
) -> str:
    """Identity of one evaluation: the parsed document, each variant's config hash, the range,
    the outcomes' ``as_of`` and the harness version."""
    payload = {
        "edge": asdict(edge),
        "variants": [(v.id, v.config.hash) for v in variants],
        "range": [start, end],
        "as_of": as_of,
        "version": HARNESS_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _variants(configs: ConfigStore, user: UserContext, edge: Edge) -> list[Variant]:
    found = [
        *(Variant(s, "screener", resolve_config(configs, s, user)) for s in edge.screeners),
        *(Variant(s, "baseline", resolve_config(configs, s, user)) for s in edge.baselines),
    ]
    if not found:
        raise ConfigurationError(f"edge {edge.id}: no screeners or baselines to evaluate")
    return found


def _universe(configs: ConfigStore, user: UserContext, edge: Edge) -> Selection:
    if isinstance(edge.universe, Selection):
        return edge.universe
    for scope in (user.user_id, "site"):
        doc = configs.load(scope, SELECTIONS, edge.universe)
        if doc is not None:
            return parse_selection(doc, f"{scope}/{SELECTIONS}/{edge.universe}")
    raise ConfigurationError(f"edge {edge.id}: unknown selection {edge.universe!r}")


class _Session:
    """What is read once per start session, whatever the horizon: each variant's run, the
    eligible names, the regime label and (when the measure needs it) the implied vol."""

    def __init__(
        self, reader: StoreReader, edge: Edge, universe: Selection, variants: list[Variant]
    ):
        self._reader, self._edge, self._universe, self._variants = reader, edge, universe, variants
        self._runs: dict[tuple[str, date], RankedRun] = {}
        self._eligible: dict[date, frozenset[str]] = {}
        self._labels: dict[date, str] = {}
        self._implied: dict[date, dict[str, float | None]] = {}

    def run(self, variant: Variant, day: date) -> RankedRun:
        if (variant.id, day) not in self._runs:
            self._runs[variant.id, day] = screen_variant(self._reader, variant.config, day)
        return self._runs[variant.id, day]

    def eligible(self, day: date) -> frozenset[str]:
        if day not in self._eligible:
            self._eligible[day] = eligible_names(self._reader, self._universe, day).ids
        return self._eligible[day]

    def snapshots(self) -> list[date]:
        """The universe snapshot dates the screens read."""
        return [run.screened.universe.snapshot_date for run in self._runs.values()]

    def label(self, day: date) -> str:
        if day not in self._labels:
            name = self._variants[0].config.regime.label
            value = session_market(self._reader, [name], day).get(name)
            self._labels[day] = UNKNOWN if value is None else str(value)
        return self._labels[day]

    def implied(self, day: date) -> dict[str, float | None]:
        if day not in self._implied:
            ids = sorted(self.eligible(day))
            view, _ = fields_view(self._reader, (IMPLIED_VOL_FIELD,), day, ids)
            values = {i: view.get(i, IMPLIED_VOL_FIELD) for i in ids}
            self._implied[day] = {
                i: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
                for i, v in values.items()
            }
        return self._implied[day]


def _stat(
    edge: Edge, session: _Session, variant: Variant, day: date, rows: pd.DataFrame
) -> SessionStat:
    """One variant at one session: ``rows`` are the stored outcomes of the session."""
    run, ids = session.run(variant, day), session.eligible(day)
    inside = rows[rows["instrument_id"].isin(ids)]
    implied = session.implied(day) if needs_implied_vol(edge) else None
    res = apply_outcome(edge, inside, implied).set_index("instrument_id")
    counted = res[res["excluded"] == ""]
    in_universe = [i for i in run.qualified if i in ids]
    picks = in_universe if edge.top_k is None else in_universe[: edge.top_k]
    pick_set = set(picks)
    have = set(res.index)
    got = [i for i in picks if i in counted.index]
    ranked = [i for i in run.ranking if i in counted.index]
    deciles = decile_means(counted.loc[ranked, "oriented"].to_list()) if ranked else None
    return SessionStat(
        session=day,
        regime=session.label(day),
        pick_values=tuple(float(v) for v in counted.loc[got, "oriented"]),
        pick_hits=int(counted.loc[got, "hit"].sum()),
        rest_values=tuple(float(v) for v in counted.loc[~counted.index.isin(pick_set), "oriented"]),
        base_hits=int(counted["hit"].sum()),
        top_decile=deciles[0] if deciles else None,
        spread=deciles[1] if deciles else None,
        ranked=len(ranked),
        excluded_unclosed=sum(1 for i in picks if i not in have),
        excluded_missing=sum(1 for i in picks if i in have and i not in counted.index),
        delisted=int(counted.loc[got, "delisted"].sum()),
        pre_snapshot=run.pre_snapshot,
        outside_universe=len(run.qualified) - len(in_universe),
    )


def _slices(edge: Edge, stats: Sequence[SessionStat]) -> list[Slice]:
    slices = [Slice("all", "all", _always)]
    for year in sorted({s.session.year for s in stats}):
        slices.append(Slice("year", str(year), partial(_in_year, year)))
    for label in sorted({s.regime for s in stats}):
        slices.append(Slice("regime", label, partial(_in_regime, label)))
    if edge.frozen_from is not None:  # fixed by the document, never rolling
        slices.append(Slice("frozen", "frozen", partial(_since, edge.frozen_from)))
    return slices


def _always(stat: SessionStat) -> bool:
    return True


def _in_year(year: int, stat: SessionStat) -> bool:
    return stat.session.year == year


def _in_regime(label: str, stat: SessionStat) -> bool:
    return stat.regime == label


def _since(day: date, stat: SessionStat) -> bool:
    return stat.session >= day


def _prior_trials(writer: ResultWriter, edge_id: str) -> set[tuple[str, str, int]]:
    found: set[tuple[str, str, int]] = set()
    for record in writer.runs_for(f"edge-eval:{edge_id}"):
        for t in record.stats.get("trials", []):
            found.add((t["variant"], t["config_hash"], int(t["horizon"])))
    return found


def _deflate(results: list[VariantResult], trials: int) -> list[VariantResult]:
    """The deflated Sharpe ratio, the trial count and PBO on each variant's "all" rows."""
    sharpes = [m.sharpe for r in results for m in r.measures[:1] if m.sharpe is not None]
    variance = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
    by_horizon: dict[int, list[VariantResult]] = {}
    for r in results:
        by_horizon.setdefault(r.horizon, []).append(r)
    out = []
    for r in results:
        peers = by_horizon[r.horizon]
        days = [s.session for s in r.stats]
        matrix = np.array([[_mean_on(p, d) for p in peers] for d in days], dtype=np.float64)
        pbo = pbo_cscv(matrix, PBO_SPLITS) if len(peers) > 1 and days else None
        means = [m for m in (s.pick_mean for s in r.stats) if m is not None]
        first = r.measures[0]
        dsr = deflated_sharpe(means, trials, variance) if means else None
        deflated = replace(first, deflated_sharpe=dsr, trials=trials, pbo=pbo)
        out.append(replace(r, measures=(deflated, *r.measures[1:])))
    return out


def _mean_on(result: VariantResult, day: date) -> float:
    """A variant's pick mean at ``day``; 0.0 when it held nothing (not invested)."""
    for s in result.stats:
        if s.session == day:
            return s.pick_mean if s.pick_mean is not None else 0.0
    return 0.0


def evaluate_edge(
    reader: StoreReader,
    writer: ResultWriter,
    configs: ConfigStore,
    user: UserContext,
    edge: Edge,
    start: date,
    end: date,
    as_of: datetime,
) -> EdgeEvaluation:
    """``edge`` over the start sessions in ``start..end`` for every horizon, its screeners and
    baselines, with outcomes known by ``as_of``. Raises ``ConfigurationError`` for an event
    schedule (ED4) and ``MissingDataError`` when no outcome is stored for a horizon."""
    if edge.event_class is not None:
        raise ConfigurationError(f"edge {edge.id}: {edge.schedule} arrives with ED4")
    variants = _variants(configs, user, edge)
    session = _Session(reader, edge, _universe(configs, user, edge), variants)
    days = sessions_between(start, end)
    results: list[VariantResult] = []
    starts: dict[int, int] = {}
    unclosed: dict[int, int] = {}
    for horizon in edge.outcome.horizon_sessions:
        sessions = edge_sessions(edge.schedule, days, horizon)
        outcomes = read_outcomes(reader, horizon, sessions, BENCHMARK, as_of=as_of)
        closed = dict(tuple(outcomes.groupby(outcomes["session_date"].map(_day))))
        starts[horizon], unclosed[horizon] = len(sessions), sum(d not in closed for d in sessions)
        for variant in variants:
            stats = tuple(
                _stat(edge, session, variant, d, closed[d]) for d in sessions if d in closed
            )
            measures = tuple(slice_measures(stats, _slices(edge, stats)))
            results.append(
                VariantResult(
                    variant.id, variant.role, variant.config.hash, horizon, stats, measures
                )
            )
    tried = {(r.variant, r.config_hash, r.horizon) for r in results}
    trials = len(tried | _prior_trials(writer, edge.id))
    snapshot = min(session.snapshots(), default=None)
    return EdgeEvaluation(
        edge_id=edge.id,
        run_hash=run_hash(edge, variants, start, end, as_of),
        benchmark=edge.outcome.benchmark,
        start=start,
        end=end,
        as_of=as_of,
        snapshot=snapshot,
        results=tuple(_deflate(results, trials)),
        trials=trials,
        start_sessions=starts,
        unclosed_sessions=unclosed,
    )


def _day(value: Any) -> date:
    return pd.Timestamp(value).date()
