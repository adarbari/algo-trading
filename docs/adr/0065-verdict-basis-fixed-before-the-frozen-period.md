# ADR 0065: The verdict's basis is fixed before the frozen period is read

**Status:** accepted (2026-10-10; owner decision D9 of the Edge page redesign plan). Amends the
verdict decision of [0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (ED8: an edge's
verdict is its best candidate's); keeps [0007](0007-point-in-time-data.md)'s rule that nothing
chooses on what was not known when the choice is made.

## Context
An edge is implemented by several candidates: each of its screeners at each holding period of
its outcome (`vrp_short_premium`: one screener at 15, 21 and 31 sessions; up to 3 x 3 before).
`services/read/evaluation/verdict.py::judge` judged every candidate on its out-of-sample
(`frozen`) figures and kept the best by (verdict level, out-of-sample lift). The figure the page
leads with was therefore the MAXIMUM of up to nine out-of-sample results: the fair test was used
to choose what is tested, and the best of several noisy results is biased upward. On the store of
2026-10-10, `vrp_short_premium` rested on 31 sessions (out-of-sample +7.6 pts) although 31
sessions was -0.1 pts in-sample; 21 sessions was the in-sample best (+1.2 pts; 15 sessions -1.5).
Every panel planned to lead with the basis (curve, decay, ledger) would inherit the bias.

## Decision
1. **One basis, fixed without the frozen period** (`verdict.choose_basis`). The candidates are
   the main edge variant's non-baseline (screen, holding period) pairs named by their
   `in_sample` or `all` rows (the rows' existence, never their figures). The edge document's
   declaration narrows them: `[implementation] promoted` (the screen) and the new optional
   `[implementation] horizon` (one of the main outcome's `horizon_sessions`, validated at load;
   bookkeeping, not a run input). One left is the basis. Of several, the best by the verdict's
   own ranking (level, then lift points) applied to the `in_sample` row alone: it stands for every
   period, the baselines are their in-sample rows, and there are no random draws (they are
   out-of-sample). In-sample rows carry no overfitting probability or deflated Sharpe, so the
   ranking level is at most Not enough data: in practice it puts a hard in-sample failure (lift
   not above zero, decile t, below the median baseline) below the rest, then orders by lift.
   Ties go to the first by screen, then horizon. A model screener's in-sample row is its training
   fit (`EdgeRow.in_sample`) and is never ranked: a model is the basis only when `promoted` (or
   when it is the one candidate). No `frozen`, `split`, `year`, `year_part`, `regime`, `regime_part` or `all` figure is read.
2. **Everything comes from the basis.** The verdict, the criteria, the columns, the evidence, the
   years and every figure are the basis's. The other candidates are not judged for the headline
   (the variant grid may show them, labelled as not the pre-chosen test). A basis that lost
   inputs is Waiting on data; the verdict never switches to another candidate because one broke.
   A declared basis the result does not have is Waiting on data, naming it.
3. **Older runs** (before the harness wrote the `in_sample` slice): with one candidate there is
   nothing to choose and it is judged as before. With several and no declaration that narrows
   them to one, the verdict is Waiting on data ("predates the in-sample figures its basis is
   chosen on; it needs a new run"). The whole-history `all` row is not a fallback: it contains
   the frozen period. A full re-run of every site edge is allowed (owner, 2026-10-10).
4. **A user's copy** (`versions.py`) follows the same rule; `implementation` is site-decided, so a
   copy's basis is always its in-sample best. A hidden copy's basis is chosen from the in-sample
   rows it is served, so revealing the result never moves it. The comparison (`Edge.compare`)
   reads every line at that basis (it fell back to the best out-of-sample lift before).
5. **Site documents declare a horizon only where the thesis fixes one**:
   `momentum_at_earnings` (its quality bar holds "one trade per report held 20 sessions") declares
   20. `vrp_short_premium` (15, 21 or 31 sessions: the range the owner trades) and
   `small_cap_earnings_drift` ("drifts for weeks": 20 or 60) are left to the in-sample rule; the
   others have one horizon.

A test fixes the point-in-time property: the basis is unchanged when every out-of-sample row is
changed or dropped (`test_the_basis_is_invariant_to_any_change_of_the_out_of_sample_rows`).

## Alternatives
- **Keep the best out-of-sample candidate and haircut it for multiplicity** (deflate the lift or
  the t by the number of candidates). Rejected: the haircut needs a model of the candidates'
  correlation (horizons overlap heavily), it still shows a chosen figure, and every panel built
  on the basis (curve, ledger) would need its own haircut.
- **Judge all candidates jointly** (a family-wise test: Works only if the set passes a corrected
  threshold). Rejected for the headline: one verdict over a set is hard to read and to act on;
  the deflated Sharpe and the overfitting probability already count the variants tried.

## Consequences
- Some bases, figures and headlines drop. On the store of 2026-10-10 (read only): no verdict level
  changes (every site edge with a run is Not enough data); `vrp_short_premium` moves from 31 to
  21 sessions (out-of-sample lift +7.6 to +5.0 pts) and `small_cap_earnings_drift` from 60 to 20
  sessions (+6.6 to +4.0 pts); the others keep their basis.
- An edge whose candidates have no in-sample rows waits until it is re-run.
- The in-sample choice can pick a candidate that is worse out of sample; that is the point: the
  out-of-sample figure is then an honest test of a choice made before it.
- `promoted` was chosen by ED7c on frozen-slice numbers; it is a reviewed declaration, used as
  written. No site edge is promoted today.
- The Guide term `verdict_basis` states the rule and why.

### Amendment (2026-10-17): two t series, a site-wide trial count, the published haircut

Owner decisions of 2026-10-17 (`docs/decisions/log.md`; build plan H1). Promising stays at a
decile t of 2; Works needs a t of 3 on **both** t series: the top-vs-bottom decile spread
(`works_t`) and the picks series (`works_picks_t`, new). The picks-series t is the t-ratio of the
Sharpe ratio of the slice's trial values (`quant/edges/statistics.sharpe_t`, the `t` of
`haircut_sharpe`), stored per slice as `results/edge_eval.picks_t` (not stored, as in an older
run: the criterion is "not measured" and the verdict stays Promising until the next run).
Both t-ratios count **independent sessions**: windows of `h` sessions started every session
overlap, so the picks t is `sharpe x sqrt(independent)` and the decile t is scaled by
`sqrt(independent / n)`, with `independent` the sum of `statistics.window_weights` (the count the
haircut already used: `runs.measured_sessions`) over the slice's measured sessions. The decile t
of an every-session edge with `h` > 1 therefore falls by about `sqrt(h)` from the next run, which
can lower a verdict that rested on it (it was overstated, never understated); a schedule spaced
at least `h` apart is unchanged. `deflate` is untouched: each edge's own trial count still deflates its Sharpe ratio.

The haircut Sharpe is also made for a **site-wide trial count**, the variants tried across the
whole programme (140 edges x variants x horizons is the count the literature's t > 3 bar is
about): `runs.load_site_trials` sums `trials_counted` of the canonical run of every site
edge (rejected and blocked ones too, not a user's own), kept per published state. `EdgeHaircut` carries
both, the edge's own and the site's (`site_trials`, `site_haircut_sharpe`, `site_cut`), and its
sentence says both. Display only: the verdict reads the deflated Sharpe, as before.

`[published] leg` (`long_short` or `long`; by default `long_short` for a `decile_spread` and `long`
for any other measure; H3 adds `short`) says what the paper's figure is of;
`verdict.toml [published_haircut]` (`long_short = 0.5`, `long = 0.333`) is the share of it
to expect lost once traded (McLean and Pontiff: about a third after publication). The decay read
carries `expected` (the figure after the haircut, the out-of-sample bar and its share of it) and
the edge page says "Published x, expect y" under the decay bars. **Display only**: no verdict
criterion reads it, and changing a share needs no run.

## Amendment 2026-10-17: the basis names a side (outcome sides, ADR 0053 amendment)

The basis is chosen among candidates of the main edge variant, whose outcome has one side
(`long`, `short` or `long_short`). A `short` candidate may be a basis: it is ranked and judged on
its own in-sample and out-of-sample figures like a long one, over liquid names only (the short
leg's dollar-volume floor and the assumed borrow cost are in its figures, `verdict.toml`).
A `long_short` candidate is never a basis (owner decision 2026-10-17: a spread cannot be traded
by buying alone and the broker access is read-only); an edge whose candidates are all
`long_short` has no basis and waits, with that reason. Promising still needs t >= 2 and Works
t >= 3 on both t series. The verdict and the edge page carry the basis's side.
