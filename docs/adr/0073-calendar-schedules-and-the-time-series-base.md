# ADR 0073: Calendar schedules and the time-series base

**Amended by [0088](0088-setups-as-positions-and-rules.md)** (proposed, 2026-11-01): base `delta_equivalent` for named option sleeves, lifting decision 1's limits for that base only.

**Status:** accepted (2026-10-18; design from the EB harness plan, architect-reviewed). Extends [0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (edges, outcomes,
one harness) and [0064](0064-edge-evidence-series-and-trade-ledger.md) (what a run publishes).

## Context
An edge timed by the calendar ("the turn of the month", "the week of the monthly expiry", "the
session before a holiday") asks whether one instrument earns more inside a window than outside it.
0053's base is a cross-section: the picks against the other names of the same session. A window
edge has no cross-section; its comparison is the same instrument's other stretches of time. The
calendar windows themselves (`core/time/windows.py`, `schedule = "calendar:<window>"`) were added
to the cross-section harness first; this ADR adds the comparison they need.

## Decision
1. **`base = "out_of_window"`** (a new `BASES` value) is legal only with a `calendar:<window>`
   schedule, an `excess_return` outcome over benchmark `none` (the instrument's raw return; the
   comparison is its own other stretches, not SPY), no `[[variants]]`, and a universe of 1 to 10
   named instruments: one rule `instrument.symbol in [...]` (`config/edges/named.py`). A symbol
   becomes an id only through `SymbolResolver` (0018); one the reference snapshot does not know
   is UNMEASURED with the reason `UNKNOWN_SYMBOL`.
2. **The value of a window** is the instrument's raw return over it, read from the outcome
   partition at its entry session S (horizon = the window's length, benchmark `none`), so the
   one-session rule of 0036 / 0053 holds. **The base** is the same instrument's returns over the
   non-overlapping stretches of the same length outside every window of the range, tiled
   deterministically from the first session after each window (`out_of_window_stretches`); a
   stretch that would not fit whole before the range's end is dropped, and a stretch avoids every
   window of the calendar, also one that begins after the range's end, so placing periods never
   depends on anything later (a property test).
3. **Measures**, per instrument and slice (all, each year, each regime label, and with a split
   the in-sample and frozen sides, cut by the period's decision session D): the mean in-window
   minus out-of-window return (`decile_spread`); its Welch t-ratio (`decile_t`, the number the
   verdict's Promising t >= 2 and Works t >= 3 read); the share of positive windows against the
   base's share (`hit_rate` against `base_rate`, so `lift` and the verdict words are the existing
   ones); Hedges' g; the Sharpe ratio and its t (`picks_t`) of the *paired* series, each window minus
   the first stretch tiled right after it (a window's raw return is mostly the instrument's drift,
   so a rising fund would pass on it; a window with no such stretch is counted in
   `excluded_missing`, never filled); the deflated Sharpe ratio of that series (trials counted as
   for any edge, one per instrument; with several instruments the variance of their Sharpe ratios,
   else the null's `1 / (T - 1)`) and the PBO among them. `decile_t` stays the honest Welch t (the
   verdict words it "In-window minus out-of-window t (Welch)" for such an edge). Year and regime
   slices are also cut by the split (`year_part`, `regime_part`), so a hidden out-of-sample run
   keeps its in-sample rows.
   The Sharpe ratio of "long in the window, Treasury bill otherwise" against buying and holding
   (the bill: the par rate of the curve tenor nearest 91 days that D itself saw, times h / 252) is
   recorded in the run record's trial entry (`timing`), not in `results/edge_eval`.
4. **Independence**: one window is one session in every count. A period's weight is
   `statistics.window_weights` over its entry sessions with the window's length as the horizon
   (the tiling leaves none overlapping; an overlapping placement would be weighted down). The t is
   read over the independent periods (`overlap_t`). Small samples are shown with their counts
   (about 100 turn-of-month windows since 2018).
5. **Random robustness**: 1,000 draws (`DEFAULT_DRAWS`), each as many periods as the edge has
   windows in the out-of-sample slice, uniformly without replacement from all its periods
   (windows and stretches), seeded by (edge, window, symbol, horizon, seed version) only; a draw's
   row is `role = random`, `slice_kind = draw`, against the instrument's own out-of-window share,
   so the verdict places the edge's lift among them as for random picks.
6. **Where it lives**: `services/evaluation/time_series/` (ownership `edge-time-series-evaluation`),
   called from `evaluate_edge`, which wraps the result as the same `EdgeEvaluation` and
   `edge_eval` rows (variant = the symbol, horizon = the window's length); there are no legs,
   per-session series or ledger (nothing is screened). The outcomes reader is imported only by
   `time_series/harness.py` in that package (an import-linter contract and a fitness test), as
   `cross_section/harness.py` is the one of its package. The quarantine of 0053 is unchanged: only
   `services.evaluation` imports `data.outcomes`.
7. **Missing history is UNMEASURED with a reason**, never a zero or a fill: no outcome row at S
   (the window is unclosed or not stored), an UNMEASURED row (0061), an unknown symbol, or no bill
   rate at D (that period only leaves the timing Sharpe ratio). The instruments' history needed
   (ETF and index proxies) comes from the Tiingo backfill of track D0; none is required to build
   or test the base.
8. **A pre-FOMC style window is never a calendar window**: a window whose placement needs a
   schedule known only at D is `on_event:macro_release` (0050); `calendar:` windows are fixed by
   the exchange calendar ahead of time.

## Consequences
`BASES` gains a value, so the document loader and its Guide entry change; the frozen split,
trial log and verdict of 0053 / 0065 / 0064 apply unchanged to a time-series edge. A time-series
edge publishes no per-session series or trade ledger, so its page shows the verdict and slices
only; the timing Sharpe ratio is in the run record until a read object carries it. Variants of a
time-series edge, a basket of instruments as one trial and costs of the timed position are not
built; each needs its own decision.
