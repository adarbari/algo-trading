# ADR 0074: Portfolio outcomes: a weighted book against a blended benchmark

**Status:** accepted (2026-10-18; orchestrator design call, pending owner confirmation, see
`docs/decisions/log.md`). Amends [0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (the
outcome kinds and the harness), [0063](0063-incremental-edge-evaluation.md) (a leg's contents,
leg v5) and [0065](0065-verdict-basis-fixed-before-the-frozen-period.md) (what Promising and
Works rest on for a book). Part (a) of EB H10; the pre-registered ensemble and the out-of-sample
haircut are part (b) and amend this ADR when they land.

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
  sessions on the edge page; the ensemble and the out-of-sample haircut (part b).
