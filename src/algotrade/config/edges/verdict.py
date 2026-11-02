"""The thresholds of an edge's verdict (``config/site/verdict.toml``, ED8): how many out-of-sample
trades it takes to say anything, and what Promising and Works ask of the out-of-sample
figures. Data, not code: the rule (``services/read/evaluation/verdict/``) reads them from
here, and each default is the owner's decision of 2026-10-09."""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from algotrade.config.edges.portfolio import OOS_CLASSES
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
    "oos_haircut",
    "decoys",
    "capacity_adv_floor_usd",
    "capacity_position_usd",
    "exit_rule",  # typed apart (positions/exit_rule.py); never a judge input
    "tails_verdict",  # TailsVerdict: the ``tails`` profile (ADR 0088, design 2.6)
    "option_costs",  # OptionCosts: the option cost levels (E6b-2 reads them)
    "option_quotes",  # typed apart (positions/quotes.py); sets outcome rows, never a judge input
)
TAILS_KEYS = (
    "option_cost_level",
    "promising_psr",
    "works_psr",
    "max_cvar_ratio",
    "min_tail_windows",
    "bootstrap_draws",
    "bootstrap_mean_block",
)
OPTION_COSTS_KEYS = ("levels", "effective_share_by_legs", "commission_usd")
OPTION_LEVELS = ("mid", "effective", "full")  # the contract's option ``cost_level`` names, in order
PROFILES = ("return", "tails")  # ``verdict_profile`` (design 2.6)
EDGE_COSTS_KEYS = ("levels_bps", "borrow_bps_annual")
LEGS = ("long", "short", "long_short")  # ``[published] leg`` (ADR 0065; outcome sides)
HAIRCUT_KEYS = LEGS  # ``[published_haircut]``: the share of a published figure lost, by leg
DECOYS_STANDARD = (
    "size_small", "momentum_12_1", "ivol_high", "max_ret_high", "amihud_illiquid", "beta_low",
)  # fmt: skip
COST_LEVELS = (0.0, 15.0, 30.0, 50.0)  # bp, the site grid (ADR 0064 decision 5; owner 2026-10-10)


@dataclass(frozen=True)
class TailsVerdict:
    """The ``tails`` profile (``[tails_verdict]``): PSR bounds, the largest CVaR ratio a setup may
    show against its base (and the fewest windows in the tail that make the ratio worth reading),
    and the stationary block bootstrap's size. Part of ``settings_hash``: a tune re-stores the
    headlines once."""

    option_cost_level: str = "full"
    promising_psr: float = 0.90
    works_psr: float = 0.95
    max_cvar_ratio: float = 1.25
    min_tail_windows: int = 5
    bootstrap_draws: int = 2000
    bootstrap_mean_block: float = 3.0

    def __post_init__(self) -> None:
        if self.option_cost_level not in OPTION_LEVELS:
            raise ConfigurationError(f"option_cost_level: expected one of {list(OPTION_LEVELS)}")
        if self.promising_psr > self.works_psr:
            raise ConfigurationError("tails_verdict: promising_psr is above works_psr")

    @classmethod
    def from_table(cls, t: Table) -> "TailsVerdict":
        d = cls()
        return cls(
            option_cost_level=t.choice("option_cost_level", d.option_cost_level, OPTION_LEVELS),
            promising_psr=t.fraction("promising_psr", d.promising_psr),
            works_psr=t.fraction("works_psr", d.works_psr),
            max_cvar_ratio=t.number("max_cvar_ratio", d.max_cvar_ratio, 1e-9),
            min_tail_windows=t.integer("min_tail_windows", d.min_tail_windows, 1),
            bootstrap_draws=t.integer("bootstrap_draws", d.bootstrap_draws, 100),
            bootstrap_mean_block=t.number("bootstrap_mean_block", d.bootstrap_mean_block, 1),
        )


@dataclass(frozen=True)
class OptionCosts:
    """The option cost levels (``[option_costs]``, design 2.4): ``mid`` pays no spread,
    ``effective`` the share of the half spread by the number of option legs (a tuple of pairs,
    so the canonical JSON has one form), ``full`` all of it; the commission per contract on each
    side. In ``settings_hash``; E6b-2 puts it in the option leg key."""

    levels: tuple[str, ...] = OPTION_LEVELS
    effective_share_by_legs: tuple[tuple[int, float], ...] = ((1, 0.75), (2, 0.65), (4, 0.53))
    commission_usd: float = 0.65

    def __post_init__(self) -> None:
        if self.levels != OPTION_LEVELS:
            raise ConfigurationError(f"option_costs levels: expected {list(OPTION_LEVELS)}")
        legs = [n for n, _ in self.effective_share_by_legs]
        shares = [s for _, s in self.effective_share_by_legs]
        ok = bool(legs) and legs[0] == 1 and all(a < b for a, b in pairwise(legs))
        ok = ok and all(0 < s <= 1 for s in shares)
        ok = ok and all(a >= b for a, b in pairwise(shares))
        if not ok:
            raise ConfigurationError(
                "option_costs effective_share_by_legs: expected ascending leg counts starting "
                f"at 1, shares in (0, 1] that do not rise, got {list(self.effective_share_by_legs)}"
            )
        if self.commission_usd < 0:
            raise ConfigurationError("option_costs commission_usd: expected >= 0")

    @classmethod
    def from_table(cls, t: Table) -> "OptionCosts":
        d = cls()
        return cls(
            levels=tuple(t.strings("levels", d.levels)),
            effective_share_by_legs=_shares_by_legs(t, d.effective_share_by_legs),
            commission_usd=t.number("commission_usd", d.commission_usd, 0),
        )


def resolve_profile(kind: str, declared: str | None) -> str:
    """The verdict profile of an edge: the document's ``verdict_profile``, else ``tails`` for an
    ``option_pnl`` outcome and ``return`` for every other kind (design 2.6; G-M2)."""
    found = declared or ("tails" if kind == "option_pnl" else "return")
    if found not in PROFILES:
        raise ConfigurationError(
            f"verdict_profile: expected one of {list(PROFILES)}, got {found!r}"
        )
    return found


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
    # ``[edge_costs] borrow_bps_annual``: the assumed yearly cost (bp) of borrowing a name to short
    # it, for an outcome that does not set its own (ADR 0053 amendment, outcome sides). No borrow
    # data is stored: it is an assumption the reports say so. The short leg of a ``short`` or
    # ``long_short`` outcome pays it scaled by the holding period (sessions / 252), and only names
    # over ``capacity_adv_floor_usd`` can be that leg. It enters the leg key (it sets values).
    borrow_bps_annual: float = 100.0
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
    # ``[oos_haircut]``: the share of an in-sample Sharpe ratio to expect lost out of sample, by
    # the edge's ``oos_class`` (``trend``: McLean-Pontiff style decay of a published anomaly; ADR
    # 0074 amendment). Shown beside the in-sample and out-of-sample Sharpe ratios in the run's
    # report, never a verdict input.
    oos_haircut_trend: float = 0.45
    haircut_short: float = 0.5  # as the spread: a short leg is harder to hold (ADR 0065)
    tails: TailsVerdict = TailsVerdict()  # ``[tails_verdict]``: the ``tails`` profile
    option_costs: OptionCosts = OptionCosts()  # ``[option_costs]``

    def oos_haircut(self, oos_class: str) -> float:
        """The share of an in-sample Sharpe ratio expected lost, for an ``OOS_CLASSES`` class."""
        return {"trend": self.oos_haircut_trend}[oos_class]

    def published_haircut(self, leg: str) -> float:
        """The share of a published figure on ``leg`` (``LEGS``) expected to be lost."""
        return {
            "long_short": self.haircut_long_short,
            "short": self.haircut_short,
        }.get(leg, self.haircut_long)

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "verdict.toml"
    ) -> "VerdictSettings":
        d = cls()
        t = Table(doc, where)
        t.only(KEYS)
        cut = t.table("published_haircut", HAIRCUT_KEYS)
        decoys = t.table("decoys", ("standard",))
        oos = t.table("oos_haircut", OOS_CLASSES)
        tails = TailsVerdict.from_table(t.table("tails_verdict", TAILS_KEYS))
        costs = OptionCosts.from_table(t.table("option_costs", OPTION_COSTS_KEYS))
        return cls(
            tails=tails,
            option_costs=costs,
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
            cost_levels_bps=_cost_levels(t.table("edge_costs", EDGE_COSTS_KEYS), d),
            borrow_bps_annual=t.table("edge_costs", EDGE_COSTS_KEYS).number(
                "borrow_bps_annual", d.borrow_bps_annual, 0
            ),
            capacity_adv_floor_usd=t.number("capacity_adv_floor_usd", d.capacity_adv_floor_usd, 1),
            capacity_position_usd=t.number("capacity_position_usd", d.capacity_position_usd, 1),
            haircut_long_short=cut.fraction("long_short", d.haircut_long_short),
            haircut_short=cut.fraction("short", d.haircut_short),
            haircut_long=cut.fraction("long", d.haircut_long),
            decoys_standard=_decoys(decoys, d.decoys_standard),
            oos_haircut_trend=oos.fraction("trend", d.oos_haircut_trend),
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


def _shares_by_legs(
    t: Table, default: tuple[tuple[int, float], ...]
) -> tuple[tuple[int, float], ...]:
    """``effective_share_by_legs``: a table of leg count -> share (``{ 1 = 0.75, 2 = 0.65 }``)."""
    raw = t.raw("effective_share_by_legs")
    if raw is None:
        return default
    try:
        pairs = [(int(k), float(v)) for k, v in dict(raw).items()]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in raw.values()):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ConfigurationError(
            f"{t.where} effective_share_by_legs: expected a table of leg count to share, "
            f"got {raw!r}"
        ) from None
    return tuple(sorted(pairs))


def _decoys(t: Table, default: tuple[str, ...]) -> tuple[str, ...]:
    """``standard``: distinct screener preset ids (that they exist is checked where an edge
    expands them, and by a fitness test over the shipped files); missing: the default list."""
    found = tuple(validate_id("screener", s) for s in t.strings("standard", default))
    if len(set(found)) != len(found):
        raise ConfigurationError(f"{t.where} standard: a decoy is listed twice: {list(found)}")
    return found
