# ADR 0065: The verdict's basis is fixed before the frozen period is read

**Status:** accepted (2026-10-10; owner decision D9 of the Edge page redesign plan). Amends the
verdict decision of [0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (ED8: an edge's
verdict is its best candidate's); keeps [0007](0007-point-in-time-data.md)'s rule that nothing
chooses on what was not known when the choice is made. Amended 2026-10-25 (proposed, owner decision
2026-10-24): a post-publication basis for setups taken from published research (last section).

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
`long_short` has no basis; its verdict is Diagnostic only, a state of its own, not Waiting on data. Promising still needs t >= 2 and Works
t >= 3 on both t series. The verdict and the edge page carry the basis's side.

## Amendment 2026-10-18: a grain with no pre-frozen history (chain P&L, ADR 0053 amendment)

The rule above fixes the basis before the frozen period is read, and ranks several candidates on
the in-sample slice. The chain P&L grain (`outcomes/option/structure_pnl@v1`) has no in-sample
history: chains are stored from 2026-10-02, after the frozen split 2026-04-01. So for an
`option_pnl` edge no candidate can be ranked on an in-sample period, and none was chosen by
looking at one: **the basis is declared at filing** (the document's one screen and one horizon,
the main variant first; `choose_basis` already takes one declared candidate without ranking), and
**every row is out of sample**; the in-sample slice is empty, not zero. An edge that files
several candidates cannot be ranked, and its verdict is Waiting on data until one is declared.
Candidates added after the first row was stored are trials in the site-wide count and cannot
become the basis. Verdict rules for such an edge (architect decision 2026-10-18): the criterion
"out-of-sample lift keeps its size" is not applicable (no in-sample lift exists to keep), so
Promising is reachable on the other criteria; Works has one more criterion, "basis fixed on an
in-sample period", which stays unmet, so **Works is unreachable** for a chain edge until a later
amendment of this ADR says when a basis declared at filing may count. The verdict text names it.

## Amendment 2026-10-25: a post-publication basis for setups taken from published research (ADR 0053 amendment)

Owner decision 2026-10-24 (`docs/decisions/log.md`). Everything marked **(owner)** is proposed and
listed again under "Owner decisions" below. The per-setup inputs and the setups' sort into the
classes below are in `docs/edge-evidence/post-publication.md`. Architect review 2026-10-24: ten
findings, all taken into the text below (the review's findings are in the PR).

**Why.** On the store of 2026-10-21, 63 of 66 setups read Not enough data: every out-of-sample
period starts at `frozen_from = 2026-04-01`, so a monthly setup with a 20-session hold has 5 or 6
independent decisions against the 40 the bar asks (`verdict.toml min_oos_trades`). For a setup whose
rule a paper published, the years after the paper's own sample are out of sample for its authors
and for us (what McLean and Pontiff measure the decay on). They are not an honest forward test, so
they get their own basis, name and ceiling, and never replace the forward one.

1. **Two bases, named, never blended.** `forward`: unchanged (ADR 0053 amendment 2026-10-08, split
   `frozen_from`, UI "forward paper record since 2026-04-01"). `post_publication`: new, UI
   "backtested (hypothetical), after publication <years>" (**(owner)** wording: where the window
   starts before the paper's publication year the label says "after the paper's sample"). The
   windows are disjoint: post-publication is the decision sessions after `sample_end` and up to the
   last decision session before `frozen_from` (a window is placed by its decision session, as
   `before_split` does today); forward starts at `frozen_from` **(owner: closed window; the
   alternative is to run to the latest session, which makes the forward record a subset)**. A
   verdict, a trade count, a t, a figure and a chart belong to one basis; no number pools them.
2. **The registration** is a new optional table of a **site** edge document, `[post_publication]`:
   `source` (index into `[[sources]]`), `sample_start`, `sample_end` (dates, from the paper's main
   sample for its headline result, never ours), `screen`, `horizon_sessions`, `match`
   (`exact` | `one_leg` | `close`, below), `match_notes`, `registered` (the commit date). Not keys of
   `[published]`: that table is the paper's figure and only 15 of 80 documents have one. A setup
   with no paper (own, practitioner), or a copy, has none. **The basis is mechanical, never
   chosen:** `screen` is the document's first `screeners` entry and `horizon_sessions` the horizon of the
   main edge variant's `[outcome]` nearest the paper's holding period (the shorter on a tie); a fitness
   test checks that the `quality_bar.replication` text names no other screener first, and that `source`
   is the paper whose rule the screener implements.
   Match levels: `exact`: same signal, ranking, side and holding period; `one_leg`: exact except it
   trades one leg of the paper's long-short spread, or the top of its extreme decile or quintile
   (a top-K cut) over the document's liquidity-floored universe; equal weighting is never a difference
   (the harness has no other); `close`: any other named difference (a different or substituted measure, a
   subset of the paper's measures, a formation or holding window, a proxy, an added filter or carry rule).
3. **Eligibility.** (a) the table is valid and the document is a site research or event setup;
   (b) `match` is `exact` or `one_leg`; `close` needs the owner's confirmation of that setup and its
   named difference in the decision log **(owner)**; (c) the basis is the mechanical one above, never
   ranked on an in-sample slice: ADR 0065 decision 1 does not apply to this basis (the in-sample
   basis of `momentum_12_1` on the 2026-10-19 store is the variant `momentum_x_quality_interaction`);
   (d) the trial log shows no variant chosen after seeing results: the basis key (`edge_variant`,
   `screen`, `horizon`) has **one** `config_hash` across every recorded run (`harness._prior_trials`,
   served as `EdgeTrials`) of the edge's job; **the screener's own hash** (`variant.hash`, which does not
   include an edge's outcome or universe, unlike the trial hash of `measuring.py:888`) has one value across
   every run of every site edge that lists the screener; **and the same basis inputs**: a hash of the
   document keys that define the basis's picks and outcome (`RUN_INPUTS`, `harness.py:168`: universe,
   `top_k`, schedule, `picks`, and the outcome's kind, benchmark, start offset, cost and the basis horizon)
   is recorded in each run's stats (`basis_inputs_hash`; for a run before it, the git history of the edge
   document and the screener preset is checked once at registration and the result written in the decision
   log). Adding or editing another screener, variant or baseline does not withdraw the setup: it is a trial
   in the deflation, and it can never become the basis; (e) an owner attestation in the decision
   log that the parameters were set from the paper's text and not tuned on the store **(owner)**.
   Limit, said on the page and here: every document was filed and run from 2026-10-08, and the
   whole-history and by-year slices over the post-sample years were visible before registration, so
   `registered` is not blind; (c), (d) and (e) are the protection, and a setup registered after its
   first run says "registered <date>; figures for the period were visible earlier".
   **Immutable once registered:** the table, the basis inputs hash and the screener hash are pinned in
   `architecture/post_publication_registered.toml`, one entry per registered setup. Unlike
   `preset_versions.toml` (any change fails CI), an entry may be **withdrawn**, never deleted or edited:
   `withdrawn = "<date>: <reason>"` moves the setup to forward-only for good, and the test requires that every
   document whose `screen`, `horizon_sessions`, `sample_end` or basis inputs differ from a live entry has been
   withdrawn in the same PR. The canonical post-publication run must match a live entry and the document
   today (`split_from` = `sample_end`, the same range end, the same hashes).
4. **Evidence rules.** `min_oos_trades = 40` and every threshold of `verdict.toml` are unchanged. A
   trade is an independent session as the haircut counts it: a window with status `measured` and at least
   one pick, weighted by `window_weights`; overlapping windows and individual names never count as more.
   **The count is per slice**, the weights computed inside the slice (`runs.measured_sessions` today counts
   over the run's whole series: used as it is it would hand every forward setup its 2010-2026 sessions).
   The harness stores it on each `edge_eval` row (`independent_sessions`, a new column of the table, in
   `architecture/tables.toml`; null in an older row, read as "needs a new run"; the stored-verdict judge has no
   store context to recompute it from the series); three readers use it and nothing else: the trades criterion (`criteria.py:211`),
   the Works counts (`criteria.py:169`) and the thin flag (`level.py:83`), which read the decision-session
   count `sessions` today (on 2026-10-19 `analyst_revision_momentum` shows 177 sessions and 0 picks, so
   such a screen would pass 40). The change applies to both bases (it can only lower a forward count),
   the counting function joins `JUDGED_CODE` (`fingerprint.py`) and `JUDGE_VERSION` goes to 2.
   The registered run evaluates **every** screener, variant, horizon and baseline of the document, as any
   run does: the probability of overfitting and the deflated Sharpe ratio need the whole grid (a run of the
   basis alone would take the lone-trial path of `criteria.py:147` and lower the bar). The deflated Sharpe
   counts every trial of the edge **(owner)**: Works on this basis also deflates by the site-wide trial count
   (recommended: the registered setups were chosen with the period visible). The out-of-sample slice is the
   window, the sessions before `sample_end` the in-sample slice (replication against the paper's own
   sample: shown, never ranked). The criterion "out-of-sample lift keeps its size" is not applicable when
   there is no in-sample slice, through a new flag `no_in_sample` (it is `c.chain` today, whose wording names
   chains); the Works criterion `basis_registered` ("basis registered before the window was read: the
   paper's rule") is new, met when the eligibility holds, and is the later amendment the 2026-10-18
   chain-P&L amendment promised for a basis declared at filing, for this basis only (`basis_in_sample`
   stays as it is for chain edges).
5. **Survivorship.** A verdict on this basis needs the survivorship-free universe (a separate work item).
   The harness stamps each run `universe_basis`: `survivors` is today's rule (ADR 0053 amendment
   2026-10-09, historical eligibility: names alive in the listing history, delisted ones included, with
   today's flags or a liquidity proxy: a disclosed lookahead tilt; the run's `historical_identity` text is
   the caveat shown); `free` is what that work item defines. Every run is `survivors` until then. A
   `survivors` run adds the Works criterion `survivorship_free` (unmet), so the ceiling is Promising; for
   an outcome side `short` (the names that failed are the best shorts and the least likely to be in the
   data) its level is at most Not enough data, never Not working; a `long` Not working stands, labelled.
   Once `free` runs exist Works is reachable, still labelled hypothetical, and never moves `status`.
6. **Interactions.**
   - **A third run state.** Today any run whose split is not `frozen_from` is exploratory
     (`runs.py:262-264`, `harness.py:401-407`), its out-of-sample rows are slice `split`, and the verdict
     drops them: a post-publication run would be invisible. `evaluate-edges --basis post_publication` makes a
     run with `basis_kind = post_publication` that derives the split (`sample_end`), the range end and the
     inputs from the document; `--basis` with `--split-from` or `--from/--to` is refused; its rows have their
     own slice kind `post_publication`; it is `exploratory = false` only when it matches the registration;
     `--split-from` alone stays exploratory, and `effective_split` is unchanged for every other path.
   - **Canonical run per basis.** `runs.load_canonical_run` takes the forward run (`basis_kind` absent or
     `forward`); a post-publication canonical run is looked up by (edge, `post_publication`). Every reader
     that filters on `exploratory` is audited in the implementation PR (`promotion.py:55,146`,
     `track_record.py:81`, `detail/verdict.py:39-50` `canonical_kind`, the ingestion verdicts task,
     `ledger_keep` `runs.py:873`: the retention purge keeps the closed post-publication run's trade ledger).
     Test: adding a post-publication run changes no forward result.
   - **Fitness test on `frozen_from`** and `[evidence].split_from == frozen_from` stay: `status`
     (`evidenced`, `live`) changes only from a forward run, never from a hypothetical one. New tests: the
     table is valid, appears only in site documents, the basis is the mechanical one, the pinned registry
     matches the documents.
   - **Copies and `oos_hidden`.** `post_publication` joins `SITE_DECIDES` (`loading.py:52`) and the harness's
     `BOOKKEEPING` list (ADR 0053 amendment 2026-10-09: what the site decides is never inherited or set): a
     copy has no post-publication basis however identical its rule, and its hidden out-of-sample withholding
     is untouched.
   - **Stored verdicts** (`verdict/stored.py`, `results/edge_verdict`): `judged_run_id` already tells the
     two bases apart, so a nullable `basis_kind` is a column, not a key (read as `forward`); the fingerprint
     adds `basis_kind`, the registration, `basis_inputs_hash` and `universe_basis`; `canonical_kind` and the
     ingestion re-judge task take the basis; a reader that asks by edge alone gets the forward row.
7. **Obligations of the implementation PR.** Which basis the Edges list headline shows, sorts and
   filters on **(owner)**; Guide entries and coverage (ADR 0051) for `basis_kind`, `universe_basis` and the
   new criterion ids, the two UI labels served from the read model and the Guide, none written in
   `apps/web`; the GraphQL schema snapshot; an ownership entry for the eligibility check (`add-responsibility`);
   the cost: a registered run recomputes legs and random draws for about 16 years (`reuse.py:190`), a long job
   (detached, per setup).
8. **Not changed:** the 2026-04-01 split and its fitness test; the haircut as display only; `[published]`;
   the long-short basis rule (a `long_short` candidate is never a basis).

**Consequences.** On the store of 2026-10-21, **2 setups meet the rules without an owner decision**
(`c31_lottery_options_short`, `short_squeeze_days_to_cover`: `one_leg`, 171 and 86 independent
post-publication sessions); 12 more are `close` and reach 40 if the owner confirms the named difference
(`momentum_12_1`, `net_share_issuance`, `lazy_prices_10k_change`, `pre_earnings_runup_winners`,
`earnings_neutral_reversal`, `earnings_announcement_premium`, `short_term_residual_reversal`,
`insider_opportunistic_cluster_buys`, `cash_based_operating_profitability`, `composite_mispricing_score`,
`quality_minus_junk`, `earnings_date_shift`); 9 are too thin today (an annual or 60-session basis, a
late-starting feature or calendar outcomes not yet stored; their match level is assessed when the data is
there); 2 are held (`risk_factor_change` by decision 5, `closed_end_fund_discounts` until the
survivorship-free universe covers closed-end funds); 55 stay forward-only
(`docs/edge-evidence/post-publication.md`). Most papers' samples ended before the store starts (2010), so the
window is the store's history before `frozen_from` and the exact `sample_end` does not move the count;
`lazy_prices_10k_change`, `quality_minus_junk`, `cash_based_operating_profitability` and
`composite_mispricing_score` have an in-sample (replication) slice. First verdicts (Not
working, Promising) arrive without lowering the bar; none reads Works before the survivorship-free universe
exists. The forward record is untouched and remains the only evidence for `status`.

**Owner decisions** (recommendation first). (1) Label wording: "after publication <years>", or "after the
paper's sample" where they differ. (2) Which `close` setups to accept, each with its named difference.
(3) Edges list headline: two labelled columns, forward first (alternatives: forward only; post-publication
only while forward is Not enough data). (4) Works on this basis deflated by the site-wide trial count: yes.
(5) One setup per paper: `lazy_prices_10k_change` only, not `risk_factor_change` (decide now, before results
are read). (6) The attestation (e) for each registered setup. (7) Closed window (stops at `frozen_from`) rather
than running to the latest session. (8) A `short`-side setup on a survivors-only universe is capped at Not
enough data, never Not working.
