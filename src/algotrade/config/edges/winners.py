"""``WinnersStudySettings``: the ED6 winners study's parameters (ADR 0053 amendment 2026-10-09)
from ``config/site/studies/winners.toml``: the outcome window the outcomes backfill computes
for it, the grid, the winner and control definitions, the discovery thresholds and the gate. Site
only, fail closed: an unknown key, a wrong type or an out-of-range value names the file."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

KIND = "studies"
NAME = "winners"
WHERE = "config/site/studies/winners.toml"


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class WinnersStudySettings:
    horizon_sessions: int
    benchmark: str
    step_sessions: int
    min_history_sessions: int
    frozen_from: date
    max_missing_fraction: float
    min_price: float
    min_adv_usd_20d: float
    top_fraction: float
    controls_per_winner: int
    liquidity_quantiles: int
    listing_age_edges_years: tuple[int, ...]
    seed: int
    min_coverage: float
    max_coverage_gap: float
    cluster_rank_corr: float
    stable_blocks: int
    block_sessions: int
    split_date: date
    permutations: int
    min_clusters: int
    min_abs_hedges_g: float
    null_percentile: int


def _date(t: Table, key: str) -> date:
    raw = t.raw(key)
    if type(raw) is date:
        return raw
    raise ConfigurationError(f"{t.where} {key}: expected a date (2026-04-01), got {raw!r}")


def parse_winners(doc: Mapping[str, Any] | None, where: str = WHERE) -> WinnersStudySettings:
    """The document, typed; a missing file or section is an error (the study has no defaults)."""
    if not doc:
        raise ConfigurationError(f"{where}: missing")
    t = Table(doc, where)
    t.only(("outcome", "grid", "eligible", "winner", "controls", "discovery", "gate"))
    out = t.table("outcome", ("horizon_sessions", "benchmark"))
    grid = t.table(
        "grid", ("step_sessions", "min_history_sessions", "frozen_from", "max_missing_fraction")
    )
    el = t.table("eligible", ("min_price", "min_adv_usd_20d"))
    win = t.table("winner", ("top_fraction",))
    ctl = t.table(
        "controls", ("per_winner", "liquidity_quantiles", "listing_age_edges_years", "seed")
    )
    dis = t.table(
        "discovery",
        (
            "min_coverage",
            "max_coverage_gap",
            "cluster_rank_corr",
            "stable_blocks",
            "block_sessions",
            "split_date",
            "permutations",
        ),
    )
    gate = t.table("gate", ("min_clusters", "min_abs_hedges_g", "null_percentile"))
    ages = ctl.raw("listing_age_edges_years")
    if (
        not isinstance(ages, list)
        or not ages
        or not all(type(a) is int and a > 0 for a in ages)
        or ages != sorted(set(ages))
    ):
        raise ConfigurationError(
            f"{ctl.where} listing_age_edges_years: expected ascending positive integers"
        )
    pct = gate.integer("null_percentile", 95, 1)
    if pct > 99:
        raise ConfigurationError(f"{gate.where} null_percentile: expected an integer <= 99")
    return WinnersStudySettings(
        horizon_sessions=out.integer("horizon_sessions", 504, 1),
        benchmark=out.text("benchmark", "SPY"),
        step_sessions=grid.integer("step_sessions", 63, 1),
        min_history_sessions=grid.integer("min_history_sessions", 252, 1),
        frozen_from=_date(grid, "frozen_from"),
        max_missing_fraction=grid.fraction("max_missing_fraction", 0.02),
        min_price=el.number("min_price", 5.0, 0),
        min_adv_usd_20d=el.number("min_adv_usd_20d", 1_000_000.0, 0),
        top_fraction=_open_fraction(win, "top_fraction", 0.02),
        controls_per_winner=ctl.integer("per_winner", 5, 1),
        liquidity_quantiles=ctl.integer("liquidity_quantiles", 5, 2),
        listing_age_edges_years=tuple(ages),
        seed=ctl.integer("seed", 0, 0),
        min_coverage=dis.fraction("min_coverage", 0.8),
        max_coverage_gap=dis.fraction("max_coverage_gap", 0.1),
        cluster_rank_corr=dis.fraction("cluster_rank_corr", 0.7),
        stable_blocks=dis.integer("stable_blocks", 5, 1),
        block_sessions=dis.integer("block_sessions", 504, 1),
        split_date=_date(dis, "split_date"),
        permutations=dis.integer("permutations", 200, 1),
        min_clusters=gate.integer("min_clusters", 5, 1),
        min_abs_hedges_g=gate.number("min_abs_hedges_g", 0.3, 0),
        null_percentile=pct,
    )


def _open_fraction(t: Table, key: str, default: float) -> float:
    value = t.fraction(key, default)
    if value <= 0:
        raise ConfigurationError(f"{t.where} {key}: expected a fraction above 0 and up to 1")
    return value


def load_winners(configs: Documents) -> WinnersStudySettings:
    """``config/site/studies/winners.toml``, typed."""
    return parse_winners(configs.load("site", KIND, NAME))
