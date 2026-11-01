"""The composite market label R1-R12 of ``market_conditions`` (design 2.1,
research-options-regimes.md section 2): one category per session from the dimension states, by
a fixed precedence.

R9 (earnings season) and R10 (event week) overlay any other regime, so they stay the flags
``earnings_season_on`` and ``event_week_on``, never labels. The ten label rules are tried in
``PRECEDENCE`` order, the most severe and most specific first; the first rule that holds names
the session. A rule is three-valued (``indicators.compare`` / ``both``: off as soon as one
condition is off, unknown only while another condition is unknown and none is off). **A label
never skips an unknown rule**: when a rule of higher precedence is unknown the label is null
(UNKNOWN), because the true label might be that rule's; when every rule is off the label is
``UNCLASSIFIED``. R3 (narrow leadership) reads the realised correlation ratio where the
research also names COR1M (not stored yet): the realised side only.

The thresholds are ``Bands`` (``config/site/rollups.toml ["market_conditions@v2"]``); a change
is a new version. The module is pure: the caller hands it the session's readings.
"""

from dataclasses import dataclass

from algotrade.features.rollups.market.indicators import Verdict, both, compare, either

PRECEDENCE = ("R6", "R7", "R12", "R8", "R5", "R4", "R3", "R11", "R2", "R1")
LABELS = (*sorted(PRECEDENCE, key=lambda r: int(r[1:])), "UNCLASSIFIED")


@dataclass(frozen=True)
class Bands:
    """The label thresholds (research-options-regimes.md sections 1 and 2)."""

    calm_below: float = 25.0  # D1: VIX below this is CALM
    stress_at: float = 35.0  # D1: VIX at or above this is STRESS
    near_trend: float = -0.05  # D4: above the 200-day mean, or no more than this far below it
    correction_lo: float = -0.15  # D4: a correction is a drawdown from this ...
    correction_hi: float = -0.05  # ... to this
    breadth_narrow: float = 0.50  # D5: fewer than this share above their 200-day mean
    breadth_bear: float = 0.30  # D5: fewer than this share in a bear trend
    corr_low: float = 0.30  # D6: the realised correlation ratio below this is high dispersion
    backwardation_days: int = 10  # R6 needs this many closes inverted; R7 only that few
    spike_chg: float = 0.40  # R7: VIX up this much over 5 observations
    thin_vrp: float = 2.0  # R2: VIX minus realised volatility below this is thin
    contango_below: float = 0.95  # D2: VIX / VIX3M below this is contango (as the verdict)
    backwardation_at: float = 1.0  # D2: VIX / VIX3M at or above this is backwardation
    vrp_rich_at: float = 4.0  # D3: VIX minus realised volatility at or above this is rich
    vix_low_pct: float = 20.0  # D1: a VIX percentile below this is low
    season_share: float = 0.15  # R9: this share of names about to report
    fomc_days: int = 5  # R10: a decision within this many sessions


@dataclass(frozen=True)
class LabelReadings:
    """What the rules read for one session, NaN / None where unknown."""

    vix: float
    ratio: float  # VIX / VIX3M
    run: float  # backwardation_run
    chg_5d: float
    pct_252: float
    vrp: float  # VIX minus the index's realised volatility, points
    drawdown: float  # S&P 500 from its 252-session high (<= 0)
    sma_200: float  # S&P 500 close / its 200-day mean - 1
    cross_50_200: float  # 50-day mean / 200-day mean - 1
    breadth: float  # share of stocks above their 200-day mean
    breadth_falling: Verdict
    corr_ratio: float
    credit_on: Verdict  # the high-yield spread card
    macro_high: Verdict  # the headline regime label is CAUTION: macro risk high, market calm
    cheap: Verdict  # index_vrp_cheap_on
    recovery: Verdict  # post_spike_recovery_on
    rate_shock: Verdict  # rate_shock_on


def _band(value: float, lo: float, hi: float) -> Verdict:
    """``lo <= value < hi``."""
    return both(compare(value, ">=", lo), compare(value, "<", hi))


def rules(x: LabelReadings, b: Bands) -> dict[str, Verdict]:
    """Every label rule, three-valued."""
    below = compare(x.sma_200, "<", 0.0)
    above_or_near = compare(x.sma_200, ">=", b.near_trend)
    caution = _band(x.vix, b.calm_below, b.stress_at)
    calm = compare(x.vix, "<", b.calm_below)
    rich = compare(x.vrp, ">=", b.vrp_rich_at)
    return {
        "R6": both(below, compare(x.cross_50_200, "<", 0.0), compare(x.vix, ">=", b.stress_at),
                   compare(x.run, ">=", b.backwardation_days),
                   compare(x.breadth, "<", b.breadth_bear), x.credit_on),
        "R7": both(compare(x.ratio, ">=", b.backwardation_at),
                   compare(x.run, "<", b.backwardation_days),
                   compare(x.chg_5d, ">=", b.spike_chg), above_or_near),
        "R12": both(x.cheap, None if x.recovery is None else not x.recovery),
        "R8": x.recovery,
        "R5": both(below, x.rate_shock, caution, rich),
        "R4": both(caution, compare(x.ratio, "<", b.backwardation_at),
                   _band(x.drawdown, b.correction_lo, b.correction_hi), above_or_near),
        "R3": both(compare(x.sma_200, ">=", 0.0), compare(x.breadth, "<", b.breadth_narrow),
                   x.breadth_falling, compare(x.corr_ratio, "<", b.corr_low)),
        "R2": both(compare(x.pct_252, "<", b.vix_low_pct), compare(x.vrp, "<", b.thin_vrp),
                   compare(x.sma_200, ">=", 0.0)),
        "R1": both(calm, compare(x.ratio, "<", b.contango_below), compare(x.sma_200, ">=", 0.0),
                   compare(x.breadth, ">=", b.breadth_narrow), compare(x.vrp, ">=", 0.0)),
        "R11": both(x.macro_high, calm, compare(x.sma_200, ">=", 0.0)),
    }  # fmt: skip


def classify(x: LabelReadings, b: Bands) -> str | None:
    """The label of ``x``: the first rule in ``PRECEDENCE`` that holds, ``UNCLASSIFIED`` when
    every rule is off, ``None`` when a rule of higher precedence than the first that holds (or
    any rule, when none holds) is unknown."""
    found = rules(x, b)
    for name in PRECEDENCE:
        if found[name] is None:
            return None
        if found[name]:
            return name
    return "UNCLASSIFIED"


def flags(share: float, fomc_sessions: float, opex_week: bool, b: Bands) -> tuple[Verdict, Verdict]:
    """``(earnings_season_on, event_week_on)``: R9 and R10 as flags (null when unknown; an
    opex week alone makes the event week on)."""
    season = compare(share, ">=", b.season_share)
    return season, either(compare(fomc_sessions, "<=", b.fomc_days), opex_week)
