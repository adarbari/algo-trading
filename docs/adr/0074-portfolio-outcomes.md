# ADR 0074: Portfolio outcomes: a weighted book against a blended benchmark

**Amended by [0088](0088-setups-as-positions-and-rules.md)** (proposed, 2026-11-01): the one book entity with a `slots` weighting, its series in the trade contract.

**Status:** accepted (2026-10-18; orchestrator design call, pending owner confirmation, see
`docs/decisions/log.md`). Amends [0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (the
outcome kinds and the harness), [0063](0063-incremental-edge-evaluation.md) (a leg's contents,
leg v5) and [0065](0065-verdict-basis-fixed-before-the-frozen-period.md) (what Promising and
Works rest on for a book). Part (a) of EB H10; the pre-registered ensemble and the out-of-sample
haircut are part (b), recorded below as the amendment of EB H10b.

## Context
Every outcome so far values one name at a time: a pick is held alone and the edge is the mean of
its picks over a base rate of the eligible names. An allocation edge (ETF rotation, tactical asset
allocation, a trend filter that goes to cash) holds a weighted book of a few instruments and is
judged against what a passive mix of the same assets would have paid. Its universe has ten
names, not hundreds, so a base rate over names and a decile spread mean nothing, and "beats SPY"
is the wrong bar for a book that is half bonds. The harness already owns the frozen split, the
trial log and the verdict (the backtest engine has none of these), so the allocation outcome
belongs in it.

## Decision
1. **A new outcome kind `portfolio_return`** and a new `base` value `benchmark` (the only base it
   has, the default). One session's value is the book's return from S's close to the close `h`
   sessions later minus the benchmark's over the same window; a session hits when that is above
   zero after the document's cost. Limits: a long book, no drawdown limit, no buy/hold band, and
   `month_end`, or `every_session` held one session (windows never overlap).
2. **The benchmark is `SPY` or a blend** `mix:SPY=0.6,AGG=0.4`: tickers and weights written, the
   weights adding to one (never normalised), parsed by `config/edges/portfolio.py::parse_mix`.
   `BENCHMARKS` stays the set the outcomes grain stores. A blend is computed in the harness from
   the constituents' own rows at the same S: they are universe instruments, so the grain has
   them. Each ticker becomes an id only through the reference snapshot S sees (the resolver, ADR
   0018). The window's return is the stored `fwd_return`, which does not depend on the grain's
   benchmark, so the rows the harness already reads (read over SPY) serve every constituent.
   A constituent the snapshot does not know, or with no usable row at S, leaves the session out
   with the reason `no_benchmark_row:<ticker>`; never a partial blend, never a zero.
3. **Weights** are formed at D from the picks (the qualified names among the pickable ones, best
   first, `top_k` of them): `equal`; `inverse_vol`, proportional to one over a declared feature
   read at D (`vol_field`); `score`, proportional to the screen's score. A pick without a finite
   positive volatility (`no_vol`) or score (`no_score`), a held name without a usable return at S
   (`no_pick_return`), leaves the session out: a book is never re-weighted over the names that
   happen to have an input. A score is a rank key, not a size, so a non-positive one has no size
   to give.
4. **Cash.** A pick `CASH` is a position with an equal share; an empty pick set is a *cash
   session*, measured, not excluded (for this kind only). Cash earns the shortest-tenor par yield
   of the curve D sees (`rates/treasury`, the latest on or before D) times `h / 252`. No stored
   curve leaves a cash-holding session out (`no_cash_yield`). Cash costs nothing to hold or leave.
   Each slot a `top_k` leaves unfilled is a `1 / top_k` share in cash too (architect decision: re-normalising over fewer names would put the whole book in one). A day before the first stored curve has no yield (`no_cash_yield`): the read would fall back to a later curve.
5. **Cost is the weight change.** A leg's stored value is net of one full round trip, as every
   leg's is. The turnover pass (`reporting/turnover.py::apply_rebalances`) replaces it by the
   cost of `sum |w_t - w_(t-1)| / 2` round trips over the names, cash excluded: the first
   session buys its book, the last book is sold at the end of the data (charged), a session that
   could not be valued closes every position. The net series (Sharpe, deflated Sharpe, PBO, the
   mean) follows it; the legs' gross figures and the hit stay as stored. Shares ADR 0053's
   amendment on bands: an entry and an exit each pay half a trip.
6. **A leg of a book** (`SessionStat`, leg v5, ADR 0063): `pick_values` is the one session
   value, `weights` the book by id (`weight_ids`, `weight_values`; `CASH` for the bill share)
   and `portfolio_reason` why a session has no value (it is then `excluded_coverage`: not
   measured). The columns are null in every other leg and no existing leg's content changes, so
   `LEG_VERSION` stays 4 and no leg is recomputed; a book's trial hash carries its weighting and
   `vol_field` (``identity_dict`` leaves the default out, so no hash of an existing edge moves).
7. **What does not apply.** The benchmark is the base, so there is no base rate, lift, effect
   size or equal-weight floor (served N/A, never 0). The decile figures are the screen's ranking of
   the eligible names and exist only when about 20 are ranked (`MIN_DECILE_NAMES`). No random
   draws are made for a book (its value is not a name's). The cost grid rows are not written for a
   book yet (its cost is its turnover's, not a per-name level).
8. **Verdict.** A book is read against its benchmark: the win rate, lift and random-picks
   criteria do not apply; the decoys are compared on the mean excess return of their own books;
   the picks-series t is a Promising test (`promising_t`, new criterion `promising_picks_t`) and
   Works's (`works_picks_t`, 3), and its failure below `not_working_t` is a hard fail as the decile
   t is for a ranking. With about 20 names ranked the decile criteria stand beside it, so Works
   then needs both t series (0065 amendment 2026-10-17); with fewer the picks-series t is the one
   t Works needs. The sentences say "beat a blend of 60% SPY and 40% AGG" (`benchmark_words`).
9. **Not settled name by name.** A book is valued whole: `apply_outcome` refuses the kind, the
   forward paper record skips its trades with a reason and a scorer is not fitted on it.

## Consequences
- Every weighting, the blended benchmark and cash have Guide terms (`outcome_portfolio_return`,
  `blended_benchmark`, `weighting_equal`, `weighting_inverse_vol`, `weighting_score`,
  `cash_position`), checked by `tests/architecture/guide/test_portfolio_outcomes.py`.
- Real data needs the constituents' outcome rows (they are universe ETFs) and, for cash, the
  Treasury curve; missing history is `no_benchmark_row` / `no_cash_yield` with the reason, never a
  zero. Tiingo history (D0) is not needed to build or test; it decides how much a run can measure.
- Deferred: cost-sensitivity rows and a break-even for a book; the per-reason counts of excluded
  sessions on the edge page.

## Amendment (2026-10-18, EB H10b): the ensemble and the out-of-sample haircut
10. **`[ensemble] variants = ["mom3", "mom6", ...]`**, for a `portfolio_return` edge: a
    pre-registered grid (at least two distinct screeners, all listed in `screeners`; `ensemble` is
    the combined variant's reserved id). Each session the harness forms every member's book at D,
    averages the weights name by name (`average_books`; cash included, so the average adds to one)
    and values the average as one book. A member that cannot be read or weighted leaves the session
    out (`<reason>:<member>`); the grid is whole or it is not measured. The ensemble has no single
    ranking, so no decile figures.
11. **One trial.** The ensemble is a variant of role `screener` and its trial hash is the sorted
    hashes of its members', so adding or changing a member is another trial. The members run as
    role `member`: reported with their own rows, never a trial (`_prior_trials`, the deflated
    Sharpe peers, `trials`) and never a verdict basis (`choose_basis` and the candidates skip the
    role; a declared `promoted` member finds no candidate). The trial log records the ensemble once
    with `grid`, the size of its grid, beside it. Members already logged as screeners in earlier
    runs stay counted (a conservative count, never rewritten). `ensemble` is a run input; the
    licence of the ensemble is the strictest of its members'.
12. **Out-of-sample haircut.** `verdict.toml [oos_haircut] trend = 0.45` (the share of an in-sample
    Sharpe ratio to expect lost out of sample) and the edge's `oos_class = "trend"` (bookkeeping,
    not a run input). The run's report prints, for each trial of the edge itself, the in-sample
    Sharpe ratio, what it becomes after the haircut and the out-of-sample one, per decision session
    and not annualised: display, never a verdict input. The read model and the edge page do not
    show it yet.

## Amendment (2026-10-18, EB E5): allocation signals, volatility targeting and the canary
13. **A bridge of macro and market series to the universe.** The signals an allocation edge
    reads (credit spreads, the VIX family, VX basis and roll, real yields, the dollar, country
    CAPE, FX carry) are stored per universe ETF as one nightly group, `etf_macro@v1`, so an edge
    reads them as any feature (the harness reads no macro table). The series-to-ETF map is code
    with a version (a fitness test pins its hash), ETF ids come from the resolver, and the group is
    not optional: a null is a row with a reason, never a missing table. Point in time: a macro value
    is the one whose vintage was known on S (`known_window`), a VX settle is read with
    `known_from <= S`, a VX basis only when the VX trade date is the VIX observation date, a value
    older than its series' `max_age_days` is null, a moving average needs 80% of its window, and a
    row's licence is the strictest of the series it read. Country CAPE is revised after
    publication, so its history is not as known; the edge's notes carry that caveat.
14. **`vol_target`.** `[outcome] vol_target = 0.10` (a fraction a year in `(0, 1]`) sizes a book
    to a volatility. With `sigma` the annualised sample standard deviation of the book's daily
    returns, `k = min(1, vol_target / sigma)`; every name is multiplied by `k` and the rest is cash
    at the bill yield (an existing cash share stays, the freed share joins it). There is no
    leverage and no weight below zero; a book already under the target is not changed (its
    `book_vol` is still stored); an all-cash book has no volatility and is not scaled.
    `vol_window` (60 sessions, at least 20) and `vol_return_field`
    (`rollup.trend_stats@v2.ret_1d`) are its other keys, refused without a target and outside a
    `portfolio_return` outcome. The scaled book pays its weight change: the turnover pass charges
    the rescaling like any other trade, cash stays free. The benchmark is not scaled (owner
    decision pending, `docs/decisions/log.md`).
15. **Realised volatility is read as it was known.** `sigma` is the book's volatility *at D*:
    today's weights on the daily returns of the `vol_window` sessions ending at D, each return read
    at its own session `t <= D` (`SessionReads.history`, `fields_view` historical, through the
    recording reader, cached per decision session so each leg logs its own reads) and never a value stored later. A restatement of any of those partitions
    invalidates the legs of the sessions that read it (ADR 0063), nothing after D is read, and a
    name with no finite return on a day of the window leaves the session out with the reason
    `no_book_vol`: sigma is never measured over the names that happen to have returns, and a
    missing return is never a zero.
16. **Leg columns.** `book_vol` (the book's volatility before scaling) and `risk_off` (the canary's
    risk-off share, item 17) are nullable floats of the leg (`SessionStat`, `legs/rows.py`,
    `edge_schemas.py`); null in every other leg and in a leg written before them, so
    `LEG_VERSION` stays 4. The vol target, its window and its return field join an outcome's
    identity only when a target is set (`identity_dict`), so no existing edge's hash moves.
17. **The canary and the defensive asset.** `[outcome.canary] tickers = ["VWO", "BND"], field =
    "<numeric feature>", breadth = 2, defensive = ["CASH"]` (or `["SHY", "IEF", "LQD"]`) gates
    the book. The canaries are resolved to ids at D (the resolver, ADR 0018) and the field is read
    at D (`SessionReads.numbers`), never at S: a signal that turns negative only after D does not
    move the book. `bad` counts the canaries with a value below zero, `f = min(1, bad / breadth)`
    is the risk-off share (VAA is a breadth of 1, DAA of 2) and the book becomes `(1 - f) * book +
    f * defensive`. The defensive asset is `CASH` (the bill yield, item 4) or the defensive ticker
    with the highest field at D, ties by ticker; it is chosen only when `f > 0`. A canary that is
    not a known instrument at D or has no finite value is `no_canary:<ticker>`, a defensive
    candidate likewise `no_defensive:<ticker>`, and a defensive asset with no return at S is
    `no_pick_return`: the session is left out, never read as positive. `risk_off` stores `f` in the
    leg; the canary table joins the outcome's identity only when present. A switch of defensive
    asset pays the weight change; `CASH` is free; the benchmark is not scaled.
18. **Composition order.** The overlays apply once per session, in `measuring._valued`, in this
    order: the weighting (with the cash of unfilled slots), the ensemble average, then the canary
    (item 17), then `vol_target`. A volatility target is measured on the book that will be held,
    so it sees what the canary left. The verdict is unchanged: a book is judged by the same
    criteria, and the guards of the weight-change cost (item 5) cover every overlay.
