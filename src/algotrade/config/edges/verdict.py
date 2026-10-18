"""The thresholds of an edge's verdict (``config/site/verdict.toml``, ED8): how many out-of-sample
trades it takes to say anything, and what Promising and Works ask of the out-of-sample
figures. Data, not code: the rule (``services/read/evaluation/verdict.py``) reads them from
here, and each default is the owner's decision of 2026-10-09."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id

KEYS = (
    "min_oos_trades",
    "works_trades",
    "works_oos_trades",
    "not_working_t",
    "promising_t",
    "works_t",
    "works_picks_t",
    "not_working_dsr",
    "promising_dsr",
    "works_dsr",
    "max_pbo",
    "works_max_pbo",
    "oos_lift_share",
    "random_beat_share",
    "forward_sessions",
    "live_min_sessions",
    "live_low",
    "live_high",
    "edge_costs",
    "published_haircut",
    "decoys",
    "capacity_adv_floor_usd",
    "capacity_position_usd",
)
LEGS = ("long", "long_short")  # ``[published] leg`` (ADR 0065; H3 adds ``short``)
HAIRCUT_KEYS = LEGS  # ``[published_haircut]``: the share of a published figure lost, by leg
DECOYS_STANDARD = (
    "size_small", "momentum_12_1", "ivol_high", "max_ret_high", "amihud_illiquid", "beta_low",
)  # fmt: skip
COST_LEVELS = (0.0, 15.0, 30.0, 50.0)  # bp, the site grid (ADR 0064 decision 5; owner 2026-10-10)


@dataclass(frozen=True)
class VerdictSettings:
    """Trades are independent sessions; ``t`` is the top-vs-bottom decile t statistic, ``dsr`` the
    deflated Sharpe ratio, ``pbo`` the probability of backtest overfitting. ``oos_lift_share``:
    the out-of-sample lift must keep this share of the whole-history lift. Works needs the
    out-of-sample lift to beat ``random_beat_share`` of the random-pick backtests' draws (ED8,
    drawn by the harness)."""

    min_oos_trades: int = 40  # owner decision 2026-10-09
    works_trades: int = 100
    works_oos_trades: int = 40
    not_working_t: float = 1.0
    promising_t: float = 2.0
    works_t: float = 3.0
    works_picks_t: float = 3.0  # Works needs this t on the picks series too (owner 2026-10-17)
    not_working_dsr: float = 0.5
    promising_dsr: float = 0.80
    works_dsr: float = 0.95
    max_pbo: float = 0.5
    works_max_pbo: float = 0.2
    oos_lift_share: float = 0.5
    random_beat_share: float = 0.95
    forward_sessions: int = 20  # a new version's forward test, in sessions (ED8; owner 2026-10-09)
    # The live record (paper trades) is judged against the backtest's usual range, the ``live_low``
    # to ``live_high`` quantiles of the wins n closed signal sessions (the picks of one night are
    # correlated, so a session is the independent unit) would show if the backtest's win rate held,
    # once ``live_min_sessions`` have closed (ED8, ADR 0053 amendment; owner-delegated).
    live_min_sessions: int = 10
    live_low: float = 0.10
    live_high: float = 0.90
    # ``[edge_costs] levels_bps``: the round-trip costs (bp) every return edge is also measured
    # at, beside its document's own ``cost_bps`` (ADR 0064 decision 5). The harness counts hits
    # at each level in every leg, so the grid is in the leg key: a changed grid recomputes legs.
    cost_levels_bps: tuple[float, ...] = COST_LEVELS
    # ``capacity_adv_floor_usd``: a pick whose 20-day average dollar volume at the decision session
    # is below this is "low liquidity" in the capacity columns of ``results/edge_eval`` (ADR 0064
    # decision 5). Applied when the statistics are computed, not in the leg key: a changed floor
    # never recomputes a leg, only the next run's rows.
    capacity_adv_floor_usd: float = 5_000_000.0
    # ``capacity_position_usd``: the size of the position the capacity page measures against a
    # pick's 20-day dollar volume ("a $100,000 position is 0.07% of the median pick's volume");
    # read when served, never stored, so changing it needs no run.
    capacity_position_usd: float = 100_000.0
    # ``[published_haircut]``: the share of a published figure to expect lost by the time it is
    # traded, by the paper's leg (McLean and Pontiff: about a third after publication, a half for
    # a long-short spread that also has costs and short limits). Display only: never a verdict
    # input (ADR 0065 amendment 2026-10-17).
    haircut_long_short: float = 0.5
    haircut_long: float = 0.333
    # ``[decoys] standard``: the screener presets ``baselines = ["@standard"]`` expands to, the
    # decoy battery every edge is compared with (ADR 0053 amendment 2026-10-18). Baselines are in
    # the run hash, so a changed list is a new run, never a changed trial.
    decoys_standard: tuple[str, ...] = DECOYS_STANDARD

    def published_haircut(self, leg: str) -> float:
        """The share of a published figure on ``leg`` (``LEGS``) expected to be lost."""
        return self.haircut_long_short if leg == "long_short" else self.haircut_long

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "verdict.toml"
    ) -> "VerdictSettings":
        d = cls()
        t = Table(doc, where)
        t.only(KEYS)
        cut = t.table("published_haircut", HAIRCUT_KEYS)
        decoys = t.table("decoys", ("standard",))
        return cls(
            min_oos_trades=t.integer("min_oos_trades", d.min_oos_trades, 1),
            works_trades=t.integer("works_trades", d.works_trades, 1),
            works_oos_trades=t.integer("works_oos_trades", d.works_oos_trades, 1),
            not_working_t=t.number("not_working_t", d.not_working_t),
            promising_t=t.number("promising_t", d.promising_t),
            works_t=t.number("works_t", d.works_t),
            works_picks_t=t.number("works_picks_t", d.works_picks_t),
            not_working_dsr=t.fraction("not_working_dsr", d.not_working_dsr),
            promising_dsr=t.fraction("promising_dsr", d.promising_dsr),
            works_dsr=t.fraction("works_dsr", d.works_dsr),
            max_pbo=t.fraction("max_pbo", d.max_pbo),
            works_max_pbo=t.fraction("works_max_pbo", d.works_max_pbo),
            oos_lift_share=t.number("oos_lift_share", d.oos_lift_share, 0),
            random_beat_share=t.fraction("random_beat_share", d.random_beat_share),
            forward_sessions=t.integer("forward_sessions", d.forward_sessions, 1),
            live_min_sessions=t.integer("live_min_sessions", d.live_min_sessions, 1),
            live_low=t.fraction("live_low", d.live_low),
            live_high=t.fraction("live_high", d.live_high),
            cost_levels_bps=_cost_levels(t.table("edge_costs", ("levels_bps",)), d),
            capacity_adv_floor_usd=t.number("capacity_adv_floor_usd", d.capacity_adv_floor_usd, 1),
            capacity_position_usd=t.number("capacity_position_usd", d.capacity_position_usd, 1),
            haircut_long_short=cut.fraction("long_short", d.haircut_long_short),
            haircut_long=cut.fraction("long", d.haircut_long),
            decoys_standard=_decoys(decoys, d.decoys_standard),
        )


def _cost_levels(t: Table, d: VerdictSettings) -> tuple[float, ...]:
    """``levels_bps``: distinct non-negative numbers, ascending (missing: the default grid)."""
    raw = t.raw("levels_bps")
    if raw is None:
        return d.cost_levels_bps
    ok = isinstance(raw, list) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in raw
    )
    if not ok or len(set(raw)) != len(raw) or list(raw) != sorted(raw):
        raise ConfigurationError(
            f"{t.where} levels_bps: expected distinct non-negative numbers ascending, got {raw!r}"
        )
    return tuple(float(v) for v in raw)


def _decoys(t: Table, default: tuple[str, ...]) -> tuple[str, ...]:
    """``standard``: distinct screener preset ids (that they exist is checked where an edge
    expands them, and by a fitness test over the shipped files); missing: the default list."""
    found = tuple(validate_id("screener", s) for s in t.strings("standard", default))
    if len(set(found)) != len(found):
        raise ConfigurationError(f"{t.where} standard: a decoy is listed twice: {list(found)}")
    return found
