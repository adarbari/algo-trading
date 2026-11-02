# Decision log

Append-only, newest last: an entry is never edited except its `status` line (and the
`- confirmed:` line added with it); a reversal is a new entry. A unit test cannot check that a
diff touched only status lines, so a reviewer does. One entry per policy decision, or design
call worth a line, whoever took it (`.claude/skills/review-and-release`, section 2).
`decided by`: owner | Fable on the owner's behalf | orchestrator (design call). The
orchestrator never decides policy (who sees what, stored personal data, retention, money,
product behaviour, an ADR contradiction); a heuristic test rejects `orchestrator` on an entry
about those topics.
`status`: final | pending owner confirmation | overruled. `final` needs `decided by: owner` or
a `- confirmed: owner YYYY-MM-DD` line: only the owner's word makes an entry final. The owner
confirms or overrules by telling the session, which updates the entry (an overrule means a
follow-up PR).

(Entries before 2026-10-18 17:00 are in `log-2026-10-11-to-17.md`; new entries are appended here.)

## 2026-10-18 | EB H7 (buy/hold bands) | One full re-run after LEG_VERSION 4
- Question: who pays the re-run that LEG_VERSION 3 (H6) and 4 (H7) each force?
- Options: a re-run after each / one after both.
- Decision: one full re-run after both merge (`algotrade-backtest evaluate-edges --full`; the PR gives the command); H7 does not run it against the real store.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: every stored leg is recomputed by either bump, so two runs would spend the same hours twice.

## 2026-10-18 | PR #651 (D6, Form 4 insider transactions) | Storing the reporting owner's CIK and officer title
- Question: may the insider transaction table store `owner_cik` and `officer_title` (public EDGAR fields that identify a natural person), or only a hashed owner key plus role flags?
- Options: store `owner_cik` + `officer_title` as filed / store a salted hash of the owner CIK + role flags only / store role flags only (no per-person key).
- Decision: store `owner_cik` and `officer_title` as filed, no names, no other identifiers (no address, no owner name from the XML). The table carries the Form 4 public filing data only; the UI shows counts and roles (distinct insiders, officer / director / 10%-owner), never a per-person list. Retention: as the other event grains (indefinite, point-in-time), per D6's plan. `docs/architecture.md` section 10 ("PII: none stored") gets a one-line amendment in a follow-up: "public SEC filer identifiers (reporting-owner CIK, officer title) are stored as filed; no names."
- decided by: Fable on the owner's behalf
- status: overruled
- confirmed: owner 2026-10-18
- Reasoning: the owner CIK is an SEC public identifier the data set is keyed on; a hash buys nothing (the hash of a public id is trivially reversible against EDGAR) and loses the join to later filings, amendments (4/A) and the deep-dive dossier. Officer title is attribute data a cluster-buy edge weighs (CEO / CFO buys vs. director buys), stored as filed with no name. The cluster-insider-buy edge needs a distinct-insider count, so a stable per-person key is functionally required. Data never enters the public repo (store is local, git-ignored); the read model serves aggregates. Precedent: ADR 0040 keeps emails (private personal data) out of the repo, not public filing data out of the store. Erasure and shorter retention are owner-only decisions (log 2026-10-11), so the default event retention stands until the owner says otherwise.

## 2026-10-18 | EB H11 (residual returns) | Betas read before S, sector term, no nightly step yet
- Question: which session's betas measure a window's residual, what to do with the sector loading, and does the task join the nightly workflow in this PR?
- Options: betas at D / at the session before S / at S; the four-factor residual only / add the sector term where `beta_sector` is set (two fits' betas) / a single five-factor fit; a nightly step now / the task and its backfill command first.
- Decision: the betas of `previous_session(S)` (exact partition, never an older one), the sector SPDR term only where `beta_sector` is set (the brief's rule, with the two-fit mix stated in the ADR), the task registered with its backfill command and no workflow step in this PR; the leg-reuse stamps do not cover the residual partitions (ADR 0053 amendment, limit a).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the session before S is D for the usual offset of 1 and never holds a window return for a larger one; the sector term is what the plan lists, and the mixed-fit inconsistency is small and visible; a nightly step needs the workflow-step tests and a real-store cost measurement the PR cannot run.

## 2026-10-18 | EB H11 (residual returns) review | Four-factor betas only, stamps, nightly step, settlement
- Question: how to resolve the architect's four findings on the residual-returns grain (sector counted twice, stale legs, no nightly step, settlement raising for a residual edge)?
- Options: sector from `beta_sector` / drop it until a five-beta `factor_betas@v2`; leave the stamps / add the residual partitions to them; follow-up step / the step now; attach residuals in settlement / catch the error per edge.
- Decision: residual on the four-factor betas only (market, size, momentum, value; a `factor_betas@v2` with all five betas of one fit is needed for sector; this supersedes the 2026-10-18 entry's sector choice); the stamps cover the residual partitions when a plan measures them (combined sequence and `knowledge_ts`); the optional nightly step `residual-returns` with an acceptance check; settlement attaches the residual rows, an unstored one waits and is skipped with a reason after the grace window.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the stored sector slope is from a different fit than the other four, so adding it counts sector exposure twice; a leg stored before the backfill must not stand for ever; an unscheduled grain goes stale; one residual edge must not stop every followed edge's settlement.

## 2026-10-18 | EB H5b (time-series base) | How a window edge is declared and judged
- Question: how does a raw-return, named-instrument edge fit the edge document and the verdict without a new outcome kind or stored column?
- Options: a new outcome kind `raw_return` and a new `edge_eval` column for the timing Sharpe / keep `excess_return` over benchmark `none` (legal only with `base = "out_of_window"`), named instruments as one `instrument.symbol in [...]` rule, the Welch t in the verdict's existing t slot and the timing Sharpe in the run record.
- Decision: the second: no new outcome kind, no schema change; `decile_t` carries the Welch t (Promising t >= 2, Works t >= 3), `hit_rate` / `base_rate` the positive-window shares, `sharpe` / `picks_t` / the deflated Sharpe the in-window series, the random window sets are `role = random` rows; no variants and no per-session series, legs or ledger for such an edge.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the verdict, trial log and frozen split are reused unchanged, so a window edge cannot be judged more leniently than a cross-section one; a stored column and a series for a screen-less edge are a schema decision for when a page shows them. Known gap: the timing-versus-buy-and-hold Sharpe is in the run record only.

## 2026-10-18 | EB H5b (time-series base) | The outcomes seam is a forbidden contract, not a widened one
- Question: the plan says to widen "only cross_section/harness.py reads outcomes" to name `time_series/harness.py`.
- Options: widen the named-modules list only / also add an import-linter contract confining the new package.
- Decision: both: `time_series/harness.py` joins the named modules of `test_edge_outcomes_expressible.py`, and a forbidden contract keeps every other module of `services.evaluation.time_series` off `algotrade.data.outcomes`; the protected-module contract of 0053 (only `services.evaluation`) is unchanged.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the package-level contract already admits all of `services.evaluation`, so widening it would change nothing; the per-package contract is what makes "one reader" true for the new folder.

## 2026-10-18 | EB H5b (PR 660 review) | The paired series carries the Sharpe, t and deflated Sharpe
- Question: the in-window Sharpe, picks t and deflated Sharpe on raw window returns read drift, not timing.
- Options: raw in-window series / each window minus the first stretch tiled right after it (unpaired windows counted, never filled).
- Decision: the paired series; `decile_t` stays the Welch t, worded "In-window minus out-of-window t (Welch)" through `EdgeFacts.base`; several instruments deflate with the variance of their Sharpe ratios; `year_part` / `regime_part` slices added; Guide term `base_out_of_window`.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a rising instrument would otherwise pass Works on drift alone; the paired difference removes the instrument's drift without a model.

## 2026-10-18 | EB E3 (event edges and avoid lists) | Short-side edges, a delayed tender entry, and what is filed blocked
- Question: how are the avoid-list edges tested, how is a tender offer's "after expiry" entry expressed, and what happens to ideas whose event class or data is missing?
- Options: avoid lists as a long edge read for a negative lift / as `side = "short"` (O2); tender entry at the filing / 21 sessions after it / wait for an expiry field; missing classes skipped / filed `blocked` with the reason / classes added in this PR.
- Decision: 8-K Item 4.02 and NT late filers are `side = "short"` edges over event names, ranked by dollar volume (the harness's short leg takes the lowest scores, so the screeners order ascending and the most liquid filer is shorted first); the tender edge enters 21 sessions after the filing (a tender offer stays open at least 20 business days; the expiry date is not stored, extensions enter early, and SC TO-T joins SC TO-I in one column); spinoff_drift, reverse_split_distress_filter and thematic_etf_launch_fade are filed `blocked` with what is missing (the classes spinoff, reverse_split and etf_launch in `EVENT_CLASSES` and `EVENT_FIELDS`, which this PR does not touch); `eight_k_item_flag` flags 4.02, 4.01 and 5.02 within 20 sessions for the avoid screen while the edge tests 4.02 only; `earnings_gap_volume@v1` adds the last report's volume ratio (the four-report mean in `earnings_reaction@v1` is a habit of the name, not the event).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a long edge reads an avoid list's confirmation as a negative lift (Not working), the short side states the same claim so that it passes; a dense-score short leg over a universe fills up with unflagged names when few are flagged, so a non-event schedule cannot test a small flagged set; entering at the filing would trade the offer's own period, not the post-expiry dip the thesis is about; a blocked document keeps the thesis, the bar and the missing pieces on file without a placeholder passing as a test.

## 2026-10-18 | EB E4 (option P&L, closed-end fund and ETF flow edges) | What is a candidate, what is blocked, and the fund features
- Question: which of the E4 and E6 ideas can be measured by the merged harness today, and how do the fund features read data the universe does not cover?
- Options: every idea a candidate / a candidate only where the outcome can be priced and the inputs have history, the rest `blocked` with the reason; fund features as a new `applies_to` value / `any` with rows only for funds.
- Decision: c12, c14, c18 (IBKR IV30, 502 sessions, horizons inside the 10 to 42 sessions the parser prices) and etf_flow_pressure (iShares counts from 2026-10-17, accruing) are candidates; c13 (no long-tenor volatility history), c16 and c17 (a 3-session and a 1-to-2-session position cannot be priced by a 30-day volatility; a short-tenor field is needed), closed_end_fund_discounts and cef_distribution_trap (closed-end funds are not in the covered universe, so no bars; the payout data is not stored either) are `blocked`; c19 (index chains not stored) and etf_premium_discount_reversion (no ETF NAV history) are not filed. `cef_nav@v1` and `etf_flows@v1` carry `applies_to = any` and rows only for funds with a NAV or a count (a new `applies_to` value is a framework change); `cef_nav@v1` is `licence = "personal"` (Tiingo). c14 reuses `ivol_high` on the liquid optionable universe. No figure is filed as `[published]`: the sources' numbers are decile or quintile spreads or one-leg premium averages.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a candidate whose outcome the parser refuses, or whose inputs have no history, would show a verdict-less row for months; a blocked document keeps the thesis, the bar and the unblock path on file. Adding closed-end funds to the universe is an owner decision (coverage, nightly bars and the Tiingo symbol budget; ADR 0013), listed in the hand-back, not decided here.
## 2026-10-18 | EB H10 (portfolio outcomes) | What a book is judged on and how it is built
- Question: how is an allocation edge (a weighted book against a blended benchmark) measured, and what do Promising and Works rest on when there is no base rate over names?
- Options: a new outcome kind in the harness / a path in the backtest engine; a mix read from the grain / computed from the constituents' rows; slots a `top_k` leaves unfilled go to cash / are left out; win rate and lift against the benchmark's hit rate / no base rate; Works on the decile t as for a ranking / on the picks-series t.
- Decision: a `portfolio_return` kind in the harness (ADR 0074); the mix computed from the constituents' own `fwd_return` at the same S through the resolver (a missing constituent leaves the session out with its reason); unfilled slots are NOT put to cash (only a `CASH` pick or an empty pick set is); no base rate, lift or random draws for a book; Promising needs the picks-series t of 2 and Works of 3, with the decile t beside it only when about 20 names are ranked; decoys compared on the mean excess return of their own books.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the harness already owns the frozen split, the trial log and the verdict, and the engine none; a base rate over ten ETFs is a coin flip and a decile of ten names is one name; putting unfilled slots to cash is a policy (a defensive default that changes what the screen means), so it waits for the owner; failing closed on a missing input keeps a book from being quietly re-weighted.

## 2026-10-18 | EB H10 (portfolio outcomes) | Leg v5 without a LEG_VERSION bump
- Question: does adding the book's weights to a leg need another full re-run of every stored leg?
- Options: bump `LEG_VERSION` to 5 / add nullable columns and leave the version.
- Decision: nullable columns (`weight_ids`, `weight_values`, `portfolio_reason`), no bump; the default weighting stays out of an outcome's identity.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: no existing leg's content or key changes (a bump recomputes every leg for nothing); a portfolio edge's legs are new keys anyway. H6 and H7's bumps already force the one full re-run.

## 2026-10-18 | EB H10 (portfolio outcomes) | Unfilled slots are cash; Works for a book without deciles
- Question: when fewer names qualify than `top_k`, is the book re-normalised over them or is the rest cash? What does Works rest on for a book with no deciles?
- Options: re-normalise / unfilled slots in cash; picks-series t alone / both t series always.
- Decision: each unfilled slot is `1 / top_k` in cash (re-normalising puts the whole book in one name); a day before the first stored Treasury curve has no yield (no look-ahead); Works for a book rests on the picks-series t of 3 when there are no deciles, with deciles both t series.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: architect review of PR 666; the cash rule is set before any edge stores legs, so no leg is invalidated.

## 2026-10-18 | EB H13 (chain P&L grain) | One UNMEASURED status per row, executable value, hedge with r = q = 0
- Question: when a hedge-day chain is missing or stale, is only the hedged P&L unmeasured or the whole row; is the harness value mid or executable; which rate and yield does our own hedge delta use?
- Options: hedged columns null, unhedged kept / the whole row UNMEASURED; mid-to-mid / ask in, bid out (half-spreads on the hedged value); the Treasury curve and dividend yield / r = q = 0.
- Decision: the whole row is UNMEASURED with the first reason (`STALE_CHAIN:<day>`, `NO_CHAIN:<day>`, `NO_DELTA:<day>`, `NO_EXIT_QUOTE`), every P&L null; the harness value is executable (a long pays the ask in and bid out, a short the reverse, the hedged value less the same half-spreads) while the mid P&L columns stay stored; the delta uses r = q = 0 and calendar days over 365.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: one status then means one thing and the spec's "never a zero, never a silently filled stale chain" holds for every column; option spreads are the main cost of this trade, so a mid value would overstate it; a one-month delta moves under 1% with the curve and the yield, and r = q = 0 keeps the grain independent of the rates and dividend tables (ADR 0053 amendment 2026-10-18, item 5). The cost of the first choice is that a stale mid-window day also unmeasures an unhedged window.

## 2026-10-18 | EB H13 (chain P&L grain) | The basis is declared at filing; no stored basis column
- Question: with no pre-frozen chain history, how is the verdict's basis fixed, and does `results/edge_eval` get a stored `basis` column (H8 left it for H13)?
- Options: rank candidates on an in-sample slice that does not exist / the basis declared at filing, every row out of sample; a stored column / the basis from the document's kind, which is in the outcome hash.
- Decision: the basis is the declared screen and horizon (several undeclared candidates: Waiting on data); every chain row is out of sample; `Outcome.basis` is `"chain"` and no `edge_eval` column is added; how the Promising and Works rules read an empty in-sample t is left open for the architect review.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: ranking needs the in-sample history the grain cannot have, and `choose_basis` already takes one declared candidate; a column on a stored results table is a schema change for a label the outcome hash already fixes, so a run cannot be mistaken for the other basis.

## 2026-10-18 | EB H13 (chain P&L grain) | Structures, tenor rule and where the grain is read
- Question: which structures and which tenor rule does the first chain grain offer, and does a mixed edge (price and chain variants) run?
- Options: only the straddles / also the short put by delta; the expiry nearest the tenor / the first at least the tenor out and not before the window's end; mixed edges allowed / refused.
- Decision: five structures (`atm_straddle_long|short`, `delta_hedged_atm[_short]`, `put_short` by delta), the grain stores the long position (`atm_straddle`, `put_delta_NN`); the first listed expiry at least `tenor_days` out and not before T; an edge and its `[[variants]]` are all `option_pnl` or none is.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: one stored row serves the long, short and hedged edge; an expiry before T could not be held to the exit; the harness reads one outcome grain per run (reuse stamps and commit sequences are per grain), so mixing is refused at filing instead of silently reading the wrong table.

## 2026-10-18 | EB H13 (architect review of #664) | Hedge-day gaps cost only the hedged P&L; bid-0 quotes and delta limits
- Question: does a missing or stale chain on a session between entry and exit unmeasure the whole row, and how are far out-of-the-money and deep in-the-money legs read after a large move?
- Options: the whole row UNMEASURED (first entry) / only the hedged P&L, with a `hedge_reason`; a bid-0 quote and an unsolved vol are missing / a bid-0 quote reads as mid ask / 2 and an unsolved vol takes the delta limit (0, +-1).
- Decision: only the hedged P&L is lost (`hedge_reason` set, the row COMPLETE, a hedged structure's harness row excluded as unmeasured); bid-0 quotes and delta limits as above. This overrules the first H13 entry's "whole row UNMEASURED". r = q = 0 is accepted for v1.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the architect review showed the biggest moves would otherwise become NO_EXIT_QUOTE / NO_DELTA and flatter the short straddle, and a stale mid-window day would blank an unhedged window for no reason.

## 2026-10-18 | EB H13 (architect review of #664) | A chain edge can be Promising, never Works, until the verdict-basis rule says more
- Question: how do the verdict rules read an empty in-sample t for a chain basis declared at filing?
- Options: leave it open / the in-sample-lift criterion not applicable and a Works criterion that stays unmet.
- Decision: "out-of-sample lift keeps its size" is not applicable for a chain edge (Promising reachable); a Works criterion "basis fixed on an in-sample period" stays unmet (Works unreachable) until a later amendment of the verdict-basis rule; written into that amendment and the Guide.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: Promising can be read on the out-of-sample figures alone, but Works needs a basis not chosen after seeing the result, which the rule can only vouch for with an in-sample period.

## 2026-10-18 | EB H9 (pair spread) | Result side, costs, base and eligibility of a pair
- Question: how is a pair spread judged, what does it charge, what is its base and which pairs count?
- Options: verdict-eligible as a long outcome / diagnostic only like `long_short`; one round trip / two; the base as one value per pair / per name against its sibling; a sibling outside the universe counts / is excluded.
- Decision: results stored and judged as `long_short` (`Outcome.result_side`: Diagnostic only, not paper traded) while the document's `side` stays `long`; `cost_bps` per leg (two round trips) plus borrow on the sibling; the base is every eligible name against its own sibling (a pair twice, once per side), so its hit rate is near one half; a pair needs both legs in the universe at D and each naming the other (`sibling_not_eligible`, `sibling_mismatch`), and an issuer with three or more classes or a class under several ids is AMBIGUOUS, never guessed.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the spec builds the pair on `long_short` and the owner decision of 2026-10-17 makes a spread diagnostic only, so a pair spread is never a verdict basis unless the owner says so; two legs cost two trades; per-name orientation is the one base that a random side of the pair produces; a one-sided or mismatched pair would pair a name with the wrong class.

## 2026-10-18 | PR #661 review (EB H9) | Pair tests, verdict, and two follow-ups
- Question: where do the pair harness tests live, is a pair spread ever a verdict basis, and are per-reason exclusion counts and a sibling ADV floor in this PR?
- Options: split the test folder now / in the next PR touching it; diagnostic only / verdict-eligible; counts and floor now / follow-up.
- Decision: tests stay in `test_harness_trials.py` (split the folder by kind in the next PR touching it); a pair spread stays Diagnostic only through `result_side`; per-reason exclusion counts (today folded into `excluded_missing`, the reason is on each pick) and an ADV floor on the sibling (short) leg are follow-ups. A reference snapshot without `cik` / `share_class_figi` is MissingDataError, never an empty pair set.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the architect review found `REFERENCE_FACTS` dropped the ids so every pick read `no_sibling`; the loader now carries them. The folder split and the two counts touch other modules and need their own review.

## 2026-10-18 | PR #661 CI (EB H9) | A reference snapshot without issuer or class ids
- Question: does `share_classes@v1` raise MissingDataError when the reference snapshot has no `cik` / `share_class_figi` column?
- Options: raise / return no rows.
- Decision: no rows (every read is UNKNOWN; a pair pick reads `no_sibling`, counted), reversing the earlier review ask.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the ingestion nightly end-to-end tests build a reference without those columns and the critical rollups step failed, holding back the workflow; a snapshot built without issuer ids is a normal state, not a broken one.

## 2026-10-18 | EB E2 (PR 667 review) | How the BDC universe is defined
- Question: how is the universe of the BDC price-to-NAV edge defined, when the reference has no BDC type and the SEC company table no SIC for them?
- Options: a ticker list with a maintenance rule / key the list by instrument_id / drop the edge.
- Decision: key by instrument_id: the tickers are resolved once through the SymbolResolver and the ids are committed in the selection preset and the screener (a fitness test keeps them equal); the edge notes say history before the frozen period is survivor-only (BDCs merged away are missing; renamed ones such as ORCC to OBDC 2023 and AINV to MFIC 2022 are the same id). The screener also requires the balance sheet to be at most 135 days old (`rollup.qmj@v1.balance_sheet_age_days`) and discloses that the cover-page share count and the balance-sheet equity can differ by a quarter.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a ticker is reused and renamed, an id is not (ADR 0018); a list with no maintenance rule is a silent survivor filter, so it is named as one; dropping the edge loses a clean, cheap test of a documented structural niche.

## 2026-10-18 | EB H10b (ensembles and the haircut) | What an ensemble counts as and how its members are treated
- Question: how many trials is a pre-registered grid whose weights are averaged, may a member be the basis, and what does the out-of-sample haircut do?
- Options: every member a trial plus the ensemble / the ensemble once; a member may be promoted as the basis / never; the haircut a verdict gate / a display; one haircut for every edge / a class per edge.
- Decision: the ensemble is one trial (its hash is its members' sorted hashes) with the grid size recorded beside it; members run as role `member`, are reported, never a trial or a basis, and members already logged as screeners stay counted; a member that cannot be weighted leaves the ensemble session out; the haircut is display only, in the run's report (`[oos_haircut] trend = 0.45`, the edge's `oos_class`), not in the read model yet.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: averaging removes the choice among members, which is what multiple-testing counts; letting a member be the basis would restore it (ADR 0065); old logs are never rewritten, so the earlier count only errs conservative; a display keeps the haircut out of the verdict until the owner decides it should gate.

## 2026-10-17 | EB D7 (country CAPE) | Barclays Shiller CAPE file used as personal-use data
- Question: may the stack pull Barclays' public `cape.csv` (26 countries, monthly) although its terms could not be retrieved (the site is a single-page app whose disclaimer text is served only to a browser session)?
- Options: use it as personal research data, one pull a month, no redistribution, no vendor data committed / wait for the owner to read the terms / use Siblis' free tier (8 snapshots, too thin).
- Decision: use it under personal use: `licence = "personal"`, `refetch_days = 28`, tests on a hand-built fixture; the owner confirms the disclaimer once in a browser.
- decided by: Fable on the owner's behalf
- status: final
- confirmed: owner 2026-10-18
- Owner read the disclaimer: personal research use, monthly automated pull, no redistribution, no product built on the index.
- Clause to respect: no reproduction, distribution or transmission without Barclays' consent, so CAPE values and every feature derived from them are never served to other users (`licence = "personal"`, held only by the owners listed in `config/site/users.toml`, ADR 0069).
- Reasoning: the file is public and unauthenticated and has been served for years, a monthly pull is a light use, and the series is optional (the macro step is non-critical), so withdrawing it costs one registry block.

## 2026-10-18 | EB H4 follow-ups | Market-level triggers are a schedule family, not event classes
- Question: should a VIX spike or FOMC date be an event class?
- Options: an event class (base = the universe, N counts per trigger) / a schedule family `on_market:<trigger>` on the 0073 time-series harness.
- Decision: `on_market:<trigger>` (named universe, `base = out_of_window`, benchmark none, one horizon); `market_triggers@v1` in rollups/market, licence personal; FOMC joins as `on_market:fomc`; `tdf_contrarian_flows` stays blocked on `on_market:large_market_month`; amends the time-series schedule rule.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: an event base would equal the universe and each trigger would count once per name.

## 2026-10-18 | EB H4 follow-ups | VIX spike definition and its placement
- Question: how is a VIX spike defined and placed?
- Options: a level only / level plus term-structure inversion; thresholds in config / fixed in the feature.
- Decision: first session with the latest fresh VIX >= 30 and VIX/VIX3M > 1 after >= 21 sessions without one; thresholds fixed in the feature (a change is a version bump); D = the session the reading was first known, both legs FRED `VIXCLS` / `VXVCLS` (`pit = "lag"`, one-day release lag, personal licence), known by D when observation date plus lag is at or before D; a trigger within h sessions of the last counted window is skipped; the base depends on later triggers inside the range (known by range end, never a decision input) and a stretch near range end can change when the range is extended.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: fixed thresholds leave no tuning knob (multiple testing), and the skip rule keeps windows from overlapping.

## 2026-10-18 | EB H4 follow-ups | ipo_lockup and reverse_split classes
- Question: how are lockup expiries and reverse splits read without lookahead?
- Options: the row's instrument_id / CIK mapped through instruments/company as of D; latest version / `latest_versions(through=D)`.
- Decision: CIK mapped through `instruments/company` as of D, `latest_versions(through=D)`, `is_ipo` rows only; `reverse_split` anchored on the ex-date with `ts <= D`, ratio < 1 pinned by a test, funds excluded; `ipo_lockup` sign -1, `announced_ahead`, short avoid-list side.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a later version or a later instrument mapping would leak survivorship into the entry.

## 2026-10-18 | EB H4 follow-ups | pre_month_end and year_turn windows; weekend and etf_launch skipped
- Question: which calendar windows are added?
- Options: last 3 sessions of the month / turn of the year / weekend / etf_launch.
- Decision: `pre_month_end` (last 3 sessions, names disjoint from `SCHEDULES`) and `year_turn` (last 5 of December + first 5 of January, length 10, belongs to December's year; about 8 windows since 2018 so it cannot reach evidenced); non-overlap property test 2000-2040; weekend skipped (decayed evidence, adds a trial); `etf_launch` deferred until the owner supplies a keyword list.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: each window is one more trial; only those with a documented, undecayed mechanism are worth it.

## 2026-10-18 | EB track E | Owner approvals: shares --force and the stale edge-eval record
- Question: may the owner-approved ops actions run: a forced refetch of every SEC company-facts CIK (`algotrade-ingest shares --force`), and clearing the stale `edge-eval` job record for edge `momentum_12_1` (status running since 2026-10-18T10:00:35Z, no process)?
- Options: wait for the nightly backlog (400 CIKs a night) / run `shares --force` once locally; hand-edit or delete the stale record / clear it only through the jobs service.
- Decision: owner, in the session chat: "run shares --force"; for the stale record: "Approved" (to "clear the stale momentum_12_1 job record through the jobs service"). Bounds: local ingestion through the normal writer, detached, one at a time under the claim lock; no deletes, no `--waive`, no `--force` on anything else, no new vendor calls beyond SEC EDGAR (free, the `shares` task's own pace); the stale record is cleared only through the jobs service (`LocalJobRunner.recover`), never by deleting files by hand.
- decided by: owner
- status: final
- Note: the parent (orchestrating) session ran `shares --force`, not the implementer that recorded this entry; the stale record was cleared by this task through `LocalJobRunner.recover` (kind `edge-eval`, the only running record).
- Reasoning: the statements groups v2/v3/v4 need every CIK refetched: 5,260 CIKs are in the backlog at 400 a night, about 14 nights; `--force` does it in about 40 minutes. The stale record would otherwise block its owner's edge evaluations until the 2 h staleness window, and it is marked failed ("abandoned: the process running it stopped") with a `finished_at`.

## 2026-10-18 | EB track E | Owner approval: CEF coverage while Tiingo Power is active
- Question: may closed-end funds be pulled into coverage (and their history) while the Tiingo Power account is active?
- Options: keep CEFs out of the universe (ADR 0013) / amend coverage to pull CEFs and their history before Tiingo Power ends.
- Decision: owner, in the session chat: "pull cef also until tingo power is there. If the edges is strong we can reconsider our decision to continue tingo power account"
- decided by: owner
- status: final
- Reasoning: `closed_end_fund_discounts` (Strong), `cef_distribution_trap` and `muni_cef_december` are blocked because CEFs are not in universe coverage (ADR 0013). Bars already exist for 330 CEFs (the nightly Massive grouped-daily and Tiingo bars-history from 2010), so the Tiingo cost is 0 symbols; the change is the universe coverage amendment, with no deadline pressure. Continuing the Tiingo Power account is to be reconsidered if the CEF (or other) edges prove strong.

## 2026-10-18 | EB E5 (vol_target) | A volatility-targeted book is scaled down from today's weights over past returns
- Question: how is a book sized to a volatility target without look-ahead, leverage or a hidden re-weighting?
- Options: scale by the stored realised vol of each name / by the book's own daily returns; scale up as well as down / down only; use the returns as stored today / as each day read them; a missing return counts as zero / leaves the session out.
- Decision: sigma is the annualised sample std of `sum(w_i r_i,t)` over `vol_window` (60) sessions ending at D, today's weights on the returns each day `t <= D` read at `t` (through the recording reader, so a restated partition invalidates the legs); `k = min(1, target / sigma)`, names times `k`, the rest cash at the bill yield; a missing return is `no_book_vol`; an all-cash book is not scaled; the target and its window and field join an outcome's hash only when set. The scaled weights go through the turnover pass, so rescaling pays the cost.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the book's own series captures correlation, which per-name vols do not; down-only keeps the outcome a long, unlevered book; reading each day as it was known keeps a later restatement from moving an earlier session. Architect design of 2026-10-18 (ADR 0074 items 14 to 16 and 18).

## 2026-10-18 | EB E5 (vol_target) | A de-risked book is still judged against the fully invested blend
- Question: when a book holds cash by a volatility target or a canary, is its benchmark scaled the same way or left as the fully invested blend?
- Options: leave the benchmark as written / scale it by the same cash share / add `CASH` as a benchmark constituent on request.
- Decision: leave it: the book is judged against the fully invested blend, so the cost of de-risking shows up as a lower excess return in rising markets; a `CASH` constituent of the benchmark is added only if the owner asks.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: scaling the benchmark by the book's own choices would hide what de-risking cost; the proposed default is the stricter bar. Owner to confirm or overrule.

## 2026-10-18 | EB E5 (macro bridge) | Revised CAPE history is accepted with a caveat
- Question: country CAPE values are revised, so a backfill is not as it was known on each date; is the history used?
- Options: use the history with a caveat in the edge's notes / start the series at the first stored vintage / drop the signal.
- Decision: use it, flagged `revised` with the caveat in the notes of every edge that reads it; a signal built from it is never presented as an as-known test.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the series is monthly and slow-moving, a vintage-only start would leave years of history empty, and the caveat keeps the limit visible. Owner to confirm or overrule.
## 2026-10-18 | EB E5 (allocation extensions, macro series) | FX 3-month rates and the broad dollar added; two owner calls logged
- Question: which series feed the etf_macro bridge's dollar and FX carry columns, and what does the allocation overlay measure against?
- Options: DTWEXBGS + OECD 3-month interbank rates via FRED (free) / a paid FX source; de-risked book judged against the fully invested blend / against a book with CASH as a constituent; revised CAPE history accepted with a caveat / dropped.
- Decision: add DTWEXBGS (daily, lag 10 days) and the OECD rates for USD, JPY, AUD, CAD and CHF (monthly, lag 60 days), all `pit = "lag"` and open. EUR (IR3TIB01EZM156N) and GBP (IR3TIB01GBM156N) are left out: their last observation is January 2026, so those currencies' `fx_carry` is null until a fresher series is found. Owner decision 1: a de-risked book is still judged against the fully invested blend (CASH becomes a benchmark constituent only if the owner asks). Owner decision 2: the revised CAPE history is accepted for the bridge with a caveat (the backfill is not as-known).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: no paid source is needed; a stale series would make carry look known when it is not; the benchmark stays comparable across edges.

## 2026-10-18 | EB E5 (PR 680 review) | Allocation edges the harness measures only in part
- Question: how are the IBS edge (the source day is close(D) to close(D+1), but S = D + 1 at the earliest), the natgas avoid list and the 9-month lookback filed?
- Options: IBS dropped / filed as a documented-limit variant; natgas against SPY / against the mix of its own funds; a 189-session return column (changes stored group trend_stats@v2) / the 3, 6 and 12 month grid.
- Decision: IBS filed as a documented-limit variant that tests the second-day return, its failure_modes saying the always-held benchmark makes cash days negative by construction; natgas benchmark is the near-equal mix of UNG, USO and DBO, so a positive excess means cash in falling years beat holding them; keep the 3, 6 and 12 month ensemble, no ret_189d (a full-history recompute, catalogue and golden regeneration, every @v2 preset moves; the 9-month return correlates about 0.9 with 6 and 12; a later 4-member grid is a new trial by hash; revisit only if the 3-member ensemble reaches Promising).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a document that states what it cannot measure is better than none, and a stored-group change for a highly correlated member is cost without information.

## 2026-10-18 | Field guide files: folders by theme group, files split in two
- Question: the twelve `config/site/field_guide/*.toml` files sit at 934-991 lines (the 1000-line cap), so every new entry fails `make filelen`; how is the guide filed?
- Options: raise the cap for these files / split each file in two in place / subfolders named after the four Guide theme groups (tradeable, chart, options, company) with each file split `<stem>.toml` + `<stem>-2.toml` / re-home entries by theme.
- Decision: subfolders by theme group, each file split at an entry boundary near its midpoint (a pure move: no entry changes, no re-homing, since themes interleave across files); the loader reads the folders one level deep and the stem order keeps `x-2` right after `x`, so the order of fields and situations, the drafting prompt bytes and the Builder's help are identical (proved by a before/after snapshot); generated pages move to `docs/data/field-guide/<group>/`, a long theme split into parts under 900 lines; a contract test keeps the layout.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Note: planned by the architect agent on the owner's behalf; CLAUDE.md's settled line names `field_guide/*.toml`; the owner may reword it to `field_guide/**/*.toml` (this PR does not edit CLAUDE.md).
- Reasoning: the cap is a settled rule, the move costs no behaviour, and the groups are the ones the Guide already shows.
## 2026-10-18 | EB H4 follow-up (ipo_lockup, reverse_split) | Where the lock-up versions and the CIK map are read
- Question: ADR 0075 says read the lock-up table with `latest_versions(through=D)` and map the CIK through `instruments/company` as of D, but a rollup is pure (no storage, no data) and reads its inputs per session.
- Options: a loader that returns the latest version known by each session (`feature_inputs._Versions`, sharing `events.latest_of` with `latest_versions`) / a version filter inside `compute`; the CIK from `instruments/reference` / from `instruments/company` with its `cik` column added to `company_sectors`.
- Decision: the loader dedupes per session by the one shared rule, and `compute` joins the CIK to `instruments/company` of the session (`company_sectors` now returns `cik` too, one more column for its other readers); a CIK with several share classes gives each the event; the nearest lock-up is the earliest expiry from 20 sessions back on.
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: keeps the one version rule in `data/`, keeps the rollup pure, and honours the ADR's company snapshot; the stored reverse-split ratio is new shares per old (a forward 4-for-1 is 4), pinned by a test, a ratio below 1 is a reverse split.

## 2026-10-18 | EB H4 follow-up (ipo_lockup, reverse_split) | Field-guide entries of the new groups sit under the instrument-gates theme
- Question: `events.toml` (977 lines) and the events theme page `docs/data/field-guide/events.md` cannot take 11 more entries (cap 1000 each), the field_guide folder and the docs page folder are both at 12 files, and a new theme would be a 13th page.
- Options: entries under the events theme (fails `make filelen`); a new theme or file (breaks the 12-file cap); the entries under `instrument gates`, whose page has room (the names are avoid-list gates), filed in the files that have room (trend, momentum, options-wing).
- Decision: the third; a structural fix (raise the page cap, or split the events theme) is for the architect.
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: the entries must ship with the columns (coverage test); a mislabelled group is cheaper to move later than a failing gate.

## 2026-10-18 | EB H4 follow-up (PR 700 review) | Dual-class CIKs and the events field-guide split
- Decision: a CIK with two share classes counts the same lock-up expiry twice, which overstates the independent events of an `ipo_lockup` edge: the edge's run record notes it. The events field-guide theme (`events.toml` and its docs page at the cap) needs a sub-folder split; Now / Next is full, so the follow-up is here only.
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
## 2026-10-18 | EB E5 (etf_macro bridge) | Field guide entries ship with the first edge that screens on the columns
- Question: does the etf_macro@v1 PR carry field guide entries for its 32 columns?
- Options: entries now (needs a split of the field guide folders, both at their caps) / entries with the folder split or the first edge PR that screens on them.
- Decision: the entries ship with the folder split or the first edge PR that screens on a bridge column; no site preset screens on them yet, so nothing requires one.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the field guide folders are at their file caps and a guide entry without a user of the field is untestable prose.

## 2026-10-18 | EB E5 (etf_macro bridge) | The bridge fields stay out of the Describe-it prompt
- Question: do the 32 etf_macro@v1 columns enter the natural-language drafting index?
- Options: raise the 13k-token budget / keep the group out of the drafting prompt until an edge screens on it.
- Decision: keep the group out (`services/drafting/prompt.py UNDRAFTED_GROUPS`, a fitness test checks the list and that the prompt honours it); the columns stay in the catalogue, Explore and the Builder. They return to the index, by removing the group from the list, when the first edge screens on them. The budget is not raised.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the columns apply to about 30 carrier funds and are not for drafts yet; their index lines pushed two golden cases' fields (atr_pct, days_to_earnings) out of the slice.
## 2026-10-18 | EB E5 (canary) | The canary gate reads its signal at D and fails closed
- Question: how does a risk-off gate on a book read its scouts and choose its defensive asset without look-ahead or a silent default?
- Options: read the signal at D / at S; a missing scout counts as positive / leaves the session out; the defensive asset fixed / the highest signal among a declared few; chosen always / only when the gate is on.
- Decision: scouts resolved to ids and the field read at D, never S; the risk-off share is `min(1, bad / breadth)` and the book is `(1 - f) * book + f * defensive`; a missing scout or defensive value is `no_canary:<T>` / `no_defensive:<T>` and leaves the session out; the defensive asset (`CASH`, or the highest signal, ties by ticker) is resolved only when the share is above zero; the canary table is in the outcome hash only when present.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: a signal read at S would trade on the window it is measured over; a missing scout read as positive would be a silent decision to stay invested. Architect design of 2026-10-18 (ADR 0074 item 17).

## 2026-10-18 | EB D6b (Form 4 insider transactions) | The reporting owner's name is stored as filed
- Question: may the insider transaction table store the Form 4 reporting owner's name (`owner_name`), reversing the "no names" part of the PR #651 entry above?
- Options: keep no names (CIK and officer title only) / store the name as filed.
- Decision: store `owner_name` as filed (SEC bulk `RPTOWNERNAME`, Form 4 XML `rptOwnerName`), whitespace trimmed, NULL when absent, never lowercased or altered; a changed spelling across filings is another value, the owner key stays `owner_cik`. Officer and director names are public SEC filing data. Everything else of the #651 entry stands (CIK and officer title as filed, no address, no other identifiers). The name is not part of the row key and never moves a `known_from`. UI rule unchanged: aggregates only, no per-person list unless a screen is explicitly built later.
- decided by: owner
- status: final
- Reasoning: the name is on the public filing beside the CIK that is already stored, so storing it adds no exposure the CIK did not, and it makes the deep-dive dossier and a later per-insider view readable. Reverses only the "no names" clause; the #651 entry's status is `overruled` for that reason.

## 2026-10-18 | Guide Edges web PR (#712) | Entry-static-imports waiver and trader-ideas budget
- Question: the Guide Edges web pages (#712) leave the entry static imports 271 B over main's budget (CI 195971 B vs 195700 B, a shared budget that only goes down) and the Ideas page chunk 530 B over main's local size; waive or cut?
- Options: cut elsewhere in the entry / waive the shared rule for this PR and raise by about 300 B.
- Decision: owner waiver of the shared rule for the entry static imports budget only, raised to 196040 B (CI 195971 B + 69 B margin) through the new `waivers` map of perf-budgets.json (a waiver names a ceiling and this entry; the budget script lets the budget rise to that ceiling once, in the PR that adds it); every other budget unchanged. The trader-ideas budget is accepted at 42690 B with its reason; follow-up: diagnose the +530 B (a module moved into the page chunk) in a later PR.
- decided by: owner
- status: final
- Reasoning: the section's lazy drawer loader, paths and kinds and its route must be in the entry; the Edges documents, drawers, pages and route components are already lazy, and the remaining bytes were measured against main.

## 2026-10-18 | EB F PR 1 (filing text similarity) | Measure, tokens and floors of the text-change features
- Question: how is the change between a filing and its year-ago filing measured, and when is it a value?
- Options: cosine on TF-IDF / min-edit distance / cosine on raw term counts plus Jaccard on word sets.
- Decision: cosine on raw term frequency (the rank field) plus Jaccard; tokens are runs of `[a-z]{2,}` after NFKC and casefold, a pinned stop list in code, no digits, no stemming; an item counts when its quality is OK and it has at least 100 words, the composite at least 500 words each side; the comparator is the same form of the same company with a report date 330 to 400 days earlier; amendments (10-K/A, 10-Q/A) are excluded; the value is carried 150 days (10-K Item 1A: 400); two rollups (`filing_text_change@v1`, `filing_text_similarity@v1`), no new table; a value is null, never zero, when no comparator or too little text.
- decided by: orchestrator (design call)
- status: final
- confirmed: owner 2026-10-18
- Reasoning: TF-IDF weights depend on the corpus the night holds, so a value could change with no text changing; raw counts and a pinned tokeniser make it reproducible. The floors keep a short or missing section from reading as "unchanged". Architect design of 2026-10-18.
## 2026-10-18 | EB E5 (batch Y, macro allocation documents) | The gate reads the carrier fund, the macro legs are separate trials, two fields stay undrafted
- Question: how are the volatility-product, curve, credit, CAPE and carry documents filed on the merged bridge, canary gate and vol_target without implying the full source rule?
- Options: a VX column on each volatility fund (a map change and a version bump) / a canary on SPY, the carrier; a macro screener inside the existing ensemble / its own trial; the two new expression features in the Describe-it index / kept out like the bridge group.
- Decision: `vix_roll_yield` holds SVXY only (UVXY and VIXY named and not held, VXX not covered) under a canary on SPY's `vx_basis` (variant `curve_roll`: `vx_roll`), no `oos_class` (one rule, no lookback grid); the macro legs (`credit_spread_below_ma200`, `country_cape_cheapest`, `fx_carry_positive`) are screeners of the existing edges outside their ensembles, so each is one more trial; `bond_curve_timing` ensembles the two slopes; `trend_carry_value_combo` is the ten-country trend plus CAPE slice, carry skipped (no curve history); `vol_managed_equity` is SPY at `vol_target = 0.10`; VAA and DAA are variants of `absolute_momentum_crash_filter` on a 13612W expression feature; `feature.credit_spread_vs_ma200` and `feature.momentum_13612w` join `UNDRAFTED_FIELDS` (two index lines tip the slice margin).
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the carrier fund already holds the VX signal and a map change rewrites a stored group; a grid pre-registered as one ensemble must not absorb a different kind of signal; the bridge group's reason to stay out of the drafting prompt applies to its two derived fields.
## 2026-10-18 | Harness learnings (seven, EB batch) | Brief checklist, live-store authorizations, edge checklist, base fitness test, load guard
- Question: which of the seven learnings from the EB batch become harness changes?
- Options: add each in its most specific home / skip.
- Decision: approved ("approved all 7", relayed by the orchestrating session): worktree path in every brief and `no-automerge` by default for implementers (agent definition + review-and-release); the edge-document checklist (add-screener) and a fitness test `tests/unit/config/site/test_edge_base.py` for the base/picks tautology; live-store authorizations must be the owner's own words in the acting session (review-and-release); `scripts/ops/xdist_workers.py` caps xdist workers to 2 above a load of 12. The auto-merge nudge was already on main (#688).
- decided by: proposed by orchestrator; awaiting owner
- status: pending owner confirmation
- Reasoning: each cost real time in the EB batch (a lost first hour per agent batch, PRs opened without `no-automerge`, eight reviews repeating the same findings, blocked relayed authorizations, runs slowed by load 13+).
## 2026-10-18 | EB H14 batch X (reverse_split_distress_filter) | The short is charged an assumed borrow of 2000 bps a year, not the site's 100
- Question: what borrow does the short side of the reverse-split avoid list pay, when the document itself puts the real borrow at 20 to 100 percent a year?
- Options: (a) keep the site default of 100 bps and note it / (b) a per-edge `borrow_bps_annual = 2000` / (c) an evidence-only short with no verdict basis.
- Decision: (b), 2000 bps a year, worded as a lower bound on the real borrow; the universe is liquid-gated (ADV of $5M or more), so owner decision O2 applies.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: 100 bps on a distressed name flatters the short by an order of magnitude; the low end of the document's own range is the least unrealistic number the store supports.
## 2026-10-19 | EB thematic_etf_launch_fade (ADR 0076) | Flag both sector and thematic ETFs, kept as two categories
- Question: does the avoid filter follow the paper (sector and thematic funds are both "specialised", XLK and XLF count) or only themes, as the edge was first worded?
- Options: sector and thematic flagged, kept apart / themes only.
- Decision: flag both, as separate categories (`etf_category` = `sector` or `thematic`), so the edge or a screener can choose and the paper's result stays testable.
- decided by: owner
- status: final
- Reasoning: the paper's specialised group is 411 sector and 115 thematic funds, so a themes-only test would not reproduce its result.
## 2026-10-19 | EB thematic_etf_launch_fade (ADR 0076) | Tiingo listing start is the launch date; the avoid window is configurable
- Question: which date is an ETF's launch, and how long after it is a fund avoided?
- Options: Tiingo `listing_history.start_date` / the first universe snapshot or first bar / a paid inception field; a three-year window / the paper's five years.
- Decision: Tiingo listing start (earliest open listing per ticker), disclosed as `launch_date_source = "tiingo_listing"`, checked against a sample of issuer inception dates; the avoid window is configurable, three years to start, with the paper's five-year result (months 1 to 60) as the evaluation horizon.
- decided by: owner
- status: final
- Reasoning: it is stored and covers 5,621 of 5,760 active ETFs, which no other free source does; its limits (first listing of the ticker, capped at Tiingo's history) are disclosed.
## 2026-10-19 | EB thematic_etf_launch_fade (ADR 0076) | The ETF names are reviewed by an Opus agent into a curated override file
- Question: who settles the keyword rule's calls on the ETF names (454 thematic, 216 sector, 87 ambiguous, 788 unclassified at the dry run)?
- Options: an owner pass over a review file / the keyword list as `name_rule` with only the ambiguous names curated / an Opus review writing the curated file.
- Decision: an Opus agent reviews the rule's output and writes `config/site/overrides/thematic_etfs.csv` (symbol, category, theme, notes); the keyword rules ship as `name_rule` and the curated row wins; what it cannot settle is left UNKNOWN in a review file for the owner.
- decided by: owner
- status: final
- Reasoning: the owner's time is for policy; the reviewer's calls are visible rows the owner can overrule by editing the file.
## 2026-10-19 | EB thematic_etf_launch_fade (ADR 0076) | Entry on the 21st session after launch, $5M a day gate, horizons 250 / 750 / 1250
- Question: when is the launch fade entered, how liquid must the fund be, and which horizons are tried?
- Options: enter on the launch day with no liquidity gate / enter after twenty sessions of bars with the site's $5M a day gate (owner decision O2) / a lower gate for thin funds.
- Decision: entry the 21st session after launch (the 20-session dollar volume needs twenty sessions of bars), the $5M a day gate, horizons 250, 750 and 1250 sessions (one, three and five years), short side with the site's default borrow.
- decided by: owner
- status: final
- Reasoning: a gate that cannot be read on the launch day would leave the edge with no events; the established O2 gate keeps the short side a liquid-name test, at the cost of a small count, which the edge's notes disclose.

## 2026-10-24 | Admin Screener runs PR (#915) | Explore chart tab first-load budget raised
- Question: CI's phone perf e2e fails the Explore chart tab first-load script (305.3 kB against 305000 B): the Admin run detail's UnavailableNote import splits a chunk Combobox shared with it, +403 B on a page this PR does not change. Trim, or raise?
- Options: trim (an implementer found no real trim: lazy import, the entities barrel and a chunk group each fail a budget) / drop UnavailableNote from the detail (loses the admin cause display) / raise the one route budget.
- Decision: Explore chart tab `first_load_js_gzip_bytes` 305000 to 305420 B; no other budget changes.
- decided by: owner
- status: final
- Reasoning: the admin Cause chain (ADR 0056) is part of the page; the overage is a chunk boundary, not new code on that route.

## 2026-10-24 | Admin Screener runs PR (#915) | Entry budgets raised by the route registration's cost
- Question: the Admin Screener runs route's lazy registration and its required page-loader prefetch sit in the entry; after #902 the entry budgets are at their limit (CI: entry 25323 B against 25310, entry plus static imports about 197124 B against 197010). Trim, or raise?
- Options: drop the prefetch (fails page-loader.test: every page starts its reads with its chunk) / trim unrelated entry code / raise the two entry budgets by the measured cost.
- Decision: owner waiver for the two entry budgets only: entry 25310 to 25410 B and entry plus static imports 197010 to 197200 B, through the `waivers` map; the raise was approved by the owner in the session (asked: raise to 196560 B on the pre-#902 budget), rebased here on #902's budgets by the implementing session; no other budget changes.
- decided by: owner
- status: final
- Reasoning: the route registration is irreducible (about 90 B gzip); the two numbers keep a margin of about 70 B over the CI measurement, as earlier waivers did.

## 2026-10-23 | Data-status pill PR (#902) | Entry bundle budgets raised by the pill's cost
- Question: the always-visible data-status pill puts its badge in the entry chunk (the popover and its detail read load on the first click, so no extra request); the entry budgets sit at their limit. Trim elsewhere, or raise the two entry budgets?
- Options: cut the pill (a lazy badge adds a JS request on every page, over the request budgets) / raise the entry and entry-plus-static-imports budgets by the pill's measured cost / drop the pill.
- Decision: owner waiver of the shared rule for the two entry budgets only: entry 24900 to 25310 B and entry plus static imports 196367 to 197010 B (measured locally 25140 and 196840 B, CI about 100 B higher, +70 B margin), through the `waivers` map; no request, DOM or route budget changes.
- decided by: owner
- status: final
- Reasoning: traders need to see which session's data they are reading on every page without a click or an extra request; the badge is about 650 B gzip.

## 2026-10-21 | Remote-client load PR (early start) | Entry-static-imports waiver of 200 B
- Question: starting a trader page's reads at start-up beside the viewer (one round trip less for a distant client) puts a one-line dynamic import in the entry, about 90 B gzip over a static-imports budget with about 35 B of margin; cut elsewhere or waive?
- Options: cut elsewhere in the entry / waive the shared rule for this PR by up to 200 B / drop the early start.
- Decision: owner waiver of the shared rule for the entry static imports budget only, ceiling 196390 B through the `waivers` map; the budget is set to 196290 B (CI measures about 93 B above a laptop); every other budget unchanged.
- decided by: owner
- status: final
- Reasoning: a distant client (India, 250-300 ms) pays one round trip for the viewer before the page's reads leave; the owner asked on 2026-10-21 for load time to hold on other continents.

## 2026-10-21 | Serving release (ADR 0077 amendment b) | Pin first, measure, then decide the front proxy, warmer and shadow comparison
- Question: build the full release with the blue/green front proxy, a separate warmer and shadow comparison now, or the pin first (a manifest and the session record read through a pinned reader, keys on the release id) and measure?
- Options: the full ADR as written / the pin first, the proxy, the separate warmer and shadow comparison deferred until the writer-mode load test is measured / drop the proxy for good.
- Decision: the pin first, measure the page p95 while an ingest publishes and the cold site after a deploy, then build a deferred item only if the load test misses the read-model criteria (page p95 > 2.5 s, `/health` p99 >= 250 ms) or the cold page p95 within 5 minutes of a deploy is above 1 s (decisions 23-24).
- decided by: owner
- status: final
- Reasoning: the architect found pages are slow because every loader key holds the published sequence, so a pin removes most of the churn with far less machinery; the owner asked on 2026-10-21 to try the pin first and measure the impact.

## 2026-10-22 | Data architecture v2 (page latency) | Cheap code fixes first; cold load bar under 1 s with explicit owner exceptions
- Question: build the SQLite run ledger and the dates catalogue first (option a), or fix the measured causes in code first and decide on the ledger from a re-measure (option b)? And what is the bar for a page's cold load?
- Options: (a) ledger and catalogue first / (b) five cheap code fixes first (skip run-record files by job name and keep the parse cache scan-resistant; build the status strip's completeness cells only when asked; make the history-copy freshness check not depend on inode numbers and read each market table once per request; read only the listed columns of the event tables; freeze screener changes at write) then re-measure / a bar of 3 s per operation.
- Decision: (b). The bar is a cold page load under 1 s; any operation or page that stays above it needs an explicit exception from the owner (the architect lists the expected exceptions after P1-P5 so they can be decided). The run ledger (SQLite, derived and rebuildable) and the dates catalogue are built only if a re-measure after the fixes shows lookups still dominate or the run files keep growing.
- decided by: owner
- status: final
- Reasoning: the profiles of 20 pages (1,310 s of work) show 39% in run-record decoding (every lookup decodes the 572 `job-<kind>-<hash>` files), 25% in the status strip's unused completeness grid and 16-20% in market-history reads; these are code fixes that need no migration; the owner wants cold loads under 1 s and wants to approve any exception.

## 2026-10-22 | Shaped tables for the 1 s cold-load bar | Allowed where needed, each one reviewed and confirmed by the owner before it is built
- Question: may the nightly write small precomputed ("shaped") tables (Regime card, preset picks, market panel, track summaries, ...) to bring operations under the 1 s cold-load bar?
- Options: yes without review / yes, each design reviewed and confirmed by the owner first / no (accept exceptions to the bar).
- Decision: yes where required to meet the bar, but no shaped table is built before the owner has reviewed its design card (what it holds, who writes it and when, size, the operations that read it, the fallback when it is missing or stale, the expected saving) and confirmed it.
- decided by: owner
- status: final
- Reasoning: the architect's bar gap analysis (docs of 2026-10-22) shows no page reaches 1 s with code fixes alone; 11 operations need a shaped table or the run ledger; each new table is a new derived artifact with a freshness rule, so the owner wants to review each.
- Superseded 2026-10-22 by "Domain-aligned derived data" (ADR 0077 amendment (c))

## 2026-10-22 | Run records (data architecture v2, decision 3) | Slimming the edge-eval job records is on hold
- Question: after the architect's check showed slimming does not reduce runtime (edge pages read small `edge-eval:<edge>:<user>` records; the 6 MB `job:edge-eval` records are read only by three evaluation-start guards), implement it now?
- Options: now / after the speed phases / hold.
- Decision: hold; do not implement. It stays a disk-hygiene candidate (139 MB of duplicated rows, growing about 6 MB per evaluation run); revisit when disk or the evaluation-start guards' cost becomes a problem. Archiving old run records also stays deferred (revisit at about 100,000 run files). This amends the 2026-10-22 entry "slim now, archive later".
- decided by: owner
- status: final
- Reasoning: it does not help the cold-load bar, so it does not belong in the speed phases.

## 2026-10-22 | Explore events list (data architecture v2, decision 5) | No filing text in the list; each filing row links to the filing
- Question: keep the `filing_text` bodies in the Explore events list, or show filings as links only?
- Options: A drop the text and keep the dated row as it is / B drop the text and link each filing row to the filing / C keep the text.
- Decision: B. The events list (`InstrumentEvents`) no longer reads or sends the text bodies of `events/filing_text` (the web timeline never showed them: only earnings, dividend, split and reference change get a detail line, every other kind is a dated row with its table name); each filing row links to the filing itself. The per-table column list of phase 4 keeps what the chart needs (the 8-K acceptance time that confirms an earnings date) and adds what the link needs (filing form, cik and accession, known_from).
- decided by: owner
- status: final
- Note: direction is final; the link target (the SEC EDGAR filing page built from cik and accession, one link per filing not per item) is confirmed in the phase 4 design.
- Reasoning: the text bodies are 4.5 GB of the 56 s uncached read of one name's events and nothing on the page displays them; a link keeps the page useful and the read narrow.
## 2026-10-22 | Data stores (data architecture v2, decision 2) | Two engines: Parquet for domain data, SQLite for operational state, files for configuration
- Question: which engine for the run ledger, and how many data stores should the system have?
- Options: SQLite / JSON lines per job / DuckDB / none; one store for everything / two engines / a third engine.
- Decision: two engines plus files, and no third. Parquet (under the existing commit protocol) stores domain facts and derived business objects (market data, features, `results/` tables such as `screen_runs` and `screen_picks`); SQLite stores operational state (the run ledger: run id, job, session, status, times, owner, the latest-run lookups); human-edited configuration stays as TOML files. The run ledger is SQLite. The domain-relevant parts of a run (a screener run's counts and changes) live in the domain object, not in the ledger. The ledger starts as a derived, rebuildable index of the run JSON files (the JSON stays the truth); an amendment to ADR 0006 (DuckDB stays a future query engine only) is written when the build starts. When it is built is decided by the re-measure after phases 1-3 (triggers: a run-record lookup still above about 100 ms warm, run files past about 100,000, or an admin page needing the list under 1 s).
- decided by: owner
- status: final
- Note: engine and structure are final; build timing follows the triggers.
- Reasoning: the call patterns of run records are small, mutable, key-based reads and writes from several processes, which fit an indexed transactional store and not immutable columnar partitions; SQLite is in the Python standard library, so there is no new dependency; keeping domain facts in one engine keeps one place to read a business fact.
## 2026-10-22 | Screener "changes" (data architecture v2, decision 4) | Frozen at write, both versions recorded, a "definition changed" mark; re-runs are non-blocking with a visible status and ETA
- Question: are a screener run's `new` / `dropped` counts recomputed when read, or frozen when the run is written? What happens when the definition changed between the two runs?
- Options: recompute on read / freeze at write; with freeze: (i) record both versions and show a "definition changed" mark, (ii) compare only against a run of the same version, (iii) freeze silently.
- Decision: freeze at write (the writer of a run records the previous run's id, the previous run's version and the new and dropped counts in the run's `results/screen_runs` row); (i): the counts are kept as compared with the previous run whatever its version, both versions are recorded, and the screeners list shows a "definition changed" mark (a Guide entry, ADR 0051). The per-name new/dropped tags of a results page still compare the two runs' rows for the names shown. Runs written before this change keep being recomputed on read. Editing a screener stays allowed at any time.
- Added requirement (owner): a user can change a screener's parameters and run it again; a re-run takes about 15-30 s or more, so it must not block the user: it runs as a job, its status is clearly visible and shows an ETA. The design of that experience is written for the owner's review before it is built.
- decided by: owner
- status: final
- Reasoning: frozen counts mean "what was known when this ran", stay stable when an earlier session's run is superseded, and cost one small read instead of re-resolving two sessions per screener (about 53 s over 92 screeners); the mark keeps the counts honest after a definition change.
## 2026-10-22 | Ideas page size (data architecture v2, decision 6) | First 50 picks, a "more" control loads the next 50, and so on
- Question: the Ideas page returns every pick in one response; how many does a first load carry?
- Options: top 50 plus a "more" control loading the next 50; keep the full list and virtualise it on screen.
- Decision: the first load carries the top 50 picks; a "more" control loads the next 50, repeatedly. The first load stays within a 300 KB budget.
- decided by: owner
- status: final
- Reasoning: the response size and the server read stay small on phones and desktops; virtualising only hides rows already sent.

## 2026-10-22 | Screener re-run experience | Measure the full wait after a re-run first; build the progress experience only after
- Question: build the non-blocking re-run experience (status, ETA) now, or measure first?
- Decision: measure first (the run itself, then the results page's cold reload), and only then build the experience. The architect's design is `screener-rerun-experience.md` (shared notes).
- decided by: owner
- status: final
- Reasoning: on the clone a screener run took a median of 1.3 s (p90 3.1 s); the 15-30 s the owner sees is probably the cold reload of the results page, which the read-path fixes shorten.

## 2026-10-22 | Domain-aligned derived data (data architecture v2) | Business objects in existing homes; two new results tables; the release only pins
- Question: how is read-optimised derived data stored: page-shaped release tables, or business objects?
- Decision: business objects in their existing homes, no new table class and no copies in the release (design `domain-derived-data.md`, shared notes). New: `results/screen_runs` (ScreenRun) and `results/screen_picks` (ScreenPick), written by the screen's own writer in the same atomic publish as `rule_screen` (ADR 0022); `market.macro_asof@v1` only if profiling blames the regime provenance read; edge evaluations read by run from `results/edge_eval`; the regime-signals table, `results/edge_runs` and the run ledger are deferred by profile. Sub-decisions: (1) ADR 0077 decisions 1 and 23 are amended (no page-shaped release tables; the release pins); (2) ADR 0077 decision 16 stays (run operations not release-shared); (3) Ideas starts at 50 picks, "more" loads 50 (above); (4) pick history stays 20 sessions; (5) accepted over-1-s exceptions until their named fix, each re-measured after it: ScreenerResults, RegimeSignals, MarketHistory, InstrumentEvents, HarnessRuns (admin), InstrumentFacts.
- decided by: owner
- status: final
- Note: the run ledger is built when the re-measure or a trigger says so (lookup over 100 ms warm, about 100,000 run files, admin page over 1 s).
- Reasoning: one way to make reads fast, no second implementation of any loader, and the stored objects serve the edge harness, paper record and ML as well as the pages.

## 2026-10-22 | Persisted per-table committed-dates index (data architecture v2) | Later, by trigger; the history-copy validation memo now
- Question: build the persisted per-table committed-dates index (`tables/<table>/_dates.json`, written inside the commit protocol, validated by epoch and seq, fallback to listing; amendments to ADR 0022 and 0060, an ownership entry) now, or later?
- Options: build now / build later on named triggers / a per-table version counter in the commit instead of the global seq for cache keys / only memoise `HistoryCopy.usable` per (table, year, seq or pin, epoch).
- Decision: later, on any of four triggers: T1 after the pin serves pages, a fresh process spends over 1 s in `dates(upto)` or the pinned cold `/admin/ingestion` grid is over 1 s; T2 RegimeSignals or MarketHistory stay over 1 s cold after the memo and the owner withdraws their accepted exception; T3 partitions pass about 400k in total or 20k in one table, or one table's `dates()` fill is over 250 ms cold; T4 the next ADR 0060 or 0022 amendment is opened (events history copy, run ledger, compaction), in which case the index and the per-year digest ship inside it under one architect review. Now: memoise `HistoryCopy.usable` per (table, year, upto if pinned else published seq, destructive epoch) and keep the per-request memo in the profiler's uncached mode. The per-table version counter alone is rejected: it needs the same protocol touch as the full index for less benefit; the protocol is touched once, for the index. Acceptance when built: `dates()` from the file equals the listing after commit, purge, drop, compaction and crash recovery (contract test), fallback on any invalid file, first validation per table under 20 ms cold, RegimeSignals under 0.5 s cold, pinned `/admin/ingestion` under 1 s, commit cost at most 5 ms per touched table, idempotent `rebuild-dates-index`. Rollback: delete the files (or bump `format`) and every reader lists again; no stored data or cache key depends on it.
- decided by: Fable on the owner's behalf
- status: final
- confirmed: owner 2026-10-22
- Note: owner confirmed: wait; revisit only if the measured time is not good enough (the triggers above). At that point the architect must also evaluate SQLite as a store option for the index (beside the per-year file design), weighing commit atomicity with the file-based publish, clone and restore behaviour, writer contention, and the 5 ms commit budget.
- Reasoning: by runtime impact (tenet 1) the index is now worth about 0.6-2 s on the two regime reads (first-request validation 0.8 s per market table) and growth, since #822 removed the 12-20 s listing fill from the completeness and strip reads (1.67 s and 0.30 s on main) and the pin (ADR 0077 b) already keys page caches on the release seq instead of every commit; it is layered, not foundational (fallback to listing, rebuildable, nothing built now is wasted), so it ranks by impact behind the events, Ideas and Edges pages; it touches atomic publish and crash recovery, where a stale index is a silent correctness fault, so it belongs in one architect-reviewed protocol amendment rather than a side PR.

## 2026-10-22 | What the Explore Events tab shows (data architecture v2) | Calendar kinds only (option F); the 2 s events exception is withdrawn after the re-measure
- Question: the Events tab received every events table by prefix: for AAPL 1,791 rows of which about 92% (insider transactions, short volume, short interest, filings) show as blank "Event" lines with no detail; they cost most of the remaining 1.5 s (encoding, copy validation). What should the tab show?
- Options: (a) calendar kinds only: earnings, dividends, splits, ticker and index changes; (b) every kind, newest 200 first with "Show more"; (c) calendar kinds plus summarised insider and filing sections.
- Decision: proceed with F: the page reads only the calendar kinds (an explicit set in the read model, a `kinds` argument defaulting to it, the chart passing its window), with a fitness test that every events table is either in the set or declared "not a timeline event" with a reason, so no new table joins the page by prefix. Insider, filings, short interest and NAV can return later as their own lazy, paged sections on request. The Fable exception for the first events read (up to 2 s) is withdrawn when the re-measure after F shows the page under 0.5 s cold for an equity and a closed-end fund.
- decided by: owner
- status: final
- Reasoning: no storage change, no point-in-time change; it removes the cost instead of storing it faster. Analysis: events-design-deep-dive.md (shared notes).

## 2026-10-22 | Ideas list: prestored per session in a SQLite table, top picks per screener, user screeners weighted (data architecture v2) | Direction decided; design to be reviewed before building
- Question: the Ideas page ranks and merges every screener's picks per request (1.0 MB, about 1 s cold); what should it read?
- Options: the server picks one best pick per ticker (Idea.best); the server merges metrics; a prestored list.
- Decision: keep it simple: a prestored Ideas list in a SQLite table, built from all screeners: the top 5 picks of each site screener and, for the user's own screeners, 3x the importance and the top 20 picks instead of 5. The page reads the stored list (paged, first 50 plus "Show more") instead of recomputing from run rows.
- decided by: owner
- status: final
- Note: direction is final. Open points the architect's design must settle before building: the exact meaning of "3x importance" in the ranking, how a ticker picked by several screeners is merged (best pick and metrics), per-user lists and privacy, the write path and atomic consistency with the Parquet publish (ADR 0022, 0033, 0077 pins), who rebuilds it after an on-request run, point in time (one session per read), and the ADR 0006 amendment for SQLite as a derived, rebuildable store beside the Parquet screen_picks.
- Reasoning: the owner prefers a small precomputed list over per-request ranking and merging; it also removes the 1.0 MB page and the best-pick question. This supersedes the earlier open questions about Idea.best and ideas.priority.

## 2026-10-22 | Ideas ranking rule, store and licence (confirmed) | Weight over position, a per-viewer SQLite index built after the rule PRs, personal-licence screeners withheld
- Question: the owner's 2026-10-22 direction (a prestored Ideas list, top 5 per site screener, the viewer's own screeners at 3x importance and top 20) left the ranking meaning, the store and its writers, and the licence of a ranked list open; the architect's design (`ideas-prestore-design.md`, shared notes) proposed answers.
- Options: ranking by sum of scores / linear decay / weight over position; a SQLite index / Parquet `results/ideas` / no store; a screener ranked on personal-licence fields listed for everyone / withheld from a viewer without the licence.
- Decision: (1) Rule: pick score = weight / position; site screeners contribute their first 5 picks at weight 1, the viewer's own screeners their first 20 at weight 3. An idea is its ticker's best pick score (the max, not the sum); ties break by consensus (the `picked_by` count), then the sum of pick scores, then `instrument_id`; display values, regime and size come from the best pick only; `ideas.priority` is retired. (2) Store: per-viewer lists of pointers and ranks in one SQLite index file (`<data root>/indexes/ideas.sqlite`), written by the nightly `ideas` step (ingestion) and by the API after an on-request run, with a stamp (`source_seq`, `screeners_hash`, `rule_hash`) and a live fallback (a missing or stale list is computed live, never served). It is built only AFTER the rule and the smaller-response loader PRs and their re-measure of the cold Ideas load. (3) Licence: a screener ranked on personal-licence fields gives no picks to a viewer without the licence. Minor: keep 20 sessions; a screener summary's `top` is its first 3 pool picks.
- decided by: owner
- status: final
- Note: this REVERSES, for Ideas only: ADR 0077 decision 25 ("a table only one page could ever read is a page table and is rejected"); the "Domain-aligned derived data" entry's rule that derived objects live in Parquet (the "Data stores" entry's two engines stay the rule everywhere else); and ADR 0005's writes line (the API also rebuilds the affected viewers' Ideas rows in the on-request run job). Recorded in ADR 0077 amendment (d), ADR 0006 and ADR 0005 amendments of the same date.
- Note: the index holds pointers and ranks only, never display values (those stay in `results/rule_screen_values` under their licence); it is derived and rebuildable, never in the release manifest, backups or the clone; owner `storage/indexes/ideas.py`. Confirmed in chat 2026-10-22 (the three decisions of the design's section 7).
- Reasoning: the rule shrinks Ideas from 9,444 to about 316 ideas on 2026-10-20 and gives one server-side best pick instead of a browser derivation; a stamped index with a live fallback keeps a stale list invisible; ranking a personal-licence screener's top 5 would leak the hidden ordering to viewers without the licence.

## 2026-10-22 | How the "under 1 s" bar is judged (data architecture v2) | The critical path per view under 1 s, plus a separate 1 s budget for the shell
- Question: a screen loads several requests at once, so what is timed for "cold load under 1 s": the slowest single request, the sum of all requests, or a real browser's time to content?
- Options: (1) critical path (the slowest request of the view) under 1 s, with the shell requests held to their own combined 1 s budget; (2) the sum of all requests under 1 s (needs one combined shell request); (3) real-browser time to content (ground truth, slow and noisy).
- Decision: (1). A view passes when its slowest request, measured as an empty-cache first request, takes under 1 s on a quiet machine (judged by ratio against untouched operations when the machine is busy), and the shell requests (Viewer, SessionDate, Regime, StatusStrip, EdgeDesk and the guide entries every screen asks for) together stay within 1 s (owner 2026-10-22: the shell has its own 1 s budget, a separate limit from the view's critical path). A real-browser time-to-content check is run now and then as ground truth, not as the gate. The fast benchmark harness becomes the regression gate: after each batch of merges it fails loudly when a view's critical path or the shell crosses its limit.
- decided by: owner
- status: final
- Reasoning: the browser overlaps requests, so the sum overstates the wait; the shell is shared by every screen and served in milliseconds in production by the release, warmer and response cache, so it gets its own small budget instead of being charged to each page.

## 2026-10-22 | Regime provenance dates for personal-licence series (data architecture v2) | Shown to viewers without the licence; values stay gated
- Question: the regime sources show, per macro series, the last observation date, the vintage date and kind, and the first vintage. Four of the seven series are licensed (BAMLH0A0HYM2 from ICE, SPX from S&P, VIX and VIX3M from Cboe). Should a viewer without the personal licence see those dates and kinds?
- Options: (a) keep showing them (release dates are not the licensed content; no values are shown); (b) gate the provenance fields for non-holders.
- Decision: (a). The provenance dates and kinds are shown to every viewer, as they are today; the licensed values stay gated. The `market.macro_asof@v1` columns over those series keep `licence = "personal"`, and the provenance read is an explicit exemption in the licence-gate test.
- decided by: owner
- status: final
- Reasoning: release dates and vintage kinds are not the licensed content, and hiding them would make the regime cards say less about how fresh their inputs are, with no licence benefit.

## 2026-10-22 | A stored edge verdict headline for the edges list (data architecture v2) | results/edge_verdict, fingerprint-checked, live fallback
- Question: the edges list judges every site edge's verdict per request (about 1.4 to 1.7 s of the 4 list views); should the headline be stored?
- Options: (A) keep judging live and speed up the judge; (B) a table `results/edge_verdict` holding the headline only, written in the edge-eval publish and by a re-judge task, read only when its fingerprint matches, else judged live; (C) store the full verdict.
- Decision: (B). The table keys on edge, user, judged run and fingerprint (judge call, settings hash, judge source digest, `JUDGE_VERSION`); the haircut is excluded; own edges and copies are always judged live; a missing or mismatched row falls back to live, never to Waiting on data.
- decided by: owner
- status: final
- Note: approved in chat 2026-10-22 (results/edge_verdict approved by the owner 2026-10-22 in chat); build plan in four PRs, PR 1 is the shared judge call and fingerprint with no behaviour change.
- Reasoning: stale is never an option, slow is: a fingerprint over everything the judge reads makes a stale verdict impossible by construction, and the headline reads less than the full verdict, so the table stays a flat row.
## 2026-10-23 | CI merge policy | Up-to-date merging not required (GitHub setting left off)
- Question: should PRs merge only when up to date with main, so cap and layout checks run on the merged result?
- Options: strict required checks with automatic branch update; a merge queue; leave as is
- Decision: leave as is (`required_status_checks.strict` stays false, no merge queue). When main is red, fix forward at once with a PR; before adding a module to a folder at cap-1, run `make layout` against current origin/main.
- decided by: owner
- status: final
- Note: owner, chat 2026-10-23: "I see this happen very few times but will add extra CI time for every push." Incident 2026-10-22: #855 and #856 each added a module to a folder one below its cap; main was red 20:57-21:54 UTC, #857 and #858 were blocked, about three agent cycles lost, no data or live-site effect. Policy text in `docs/ci.md`.
- Reasoning: the failure is rare and its cost small and recoverable, while strict checks re-run CI on every push of every PR.

## 2026-10-22 | Ideas SQLite index deferred; built in a separate session (data architecture v2) | Defer, revisit on measured triggers
- Question: build the per-viewer prestored Ideas SQLite index now, or defer it after the cheaper read fixes?
- Options: build now / defer on measured triggers.
- Decision: defer (owner, in chat 2026-10-22: "On Ideas SQLite index let us defer. I will start a different session on SQLite separately."). Triggers to revisit: IdeasPage over 1 s cold again after the cheaper steps; run-file count or payload growth past the plan's thresholds; a second feature needing the same prestored shape. Re-measure with the nightly gate first. The ADR 0006 amendment of 2026-10-22 and the decision "Ideas ranking rule, store and licence (confirmed)" stand unchanged.
- decided by: owner
- status: final
- Note: the owner starts the SQLite work in a separate session; the hand-off note is outside the repo.
- Reasoning: IdeasPage is 0.91 s cold on a quiet machine (0.85 s for a trader without the personal licence) after #860 (skip the values-file read) and #861 (light IdeaScreener.top), against a 1 s bar. The architect's profile showed run-file reads (about 65% of load_ideas) were the cost, and an index would save only about 0.1-0.3 s; the batched run-file read (#863) was closed after measuring 0.018 s against an estimated 0.15-0.2 s.

## 2026-10-23 | Page-latency gate (#848) | `MyScreens` may answer empty on the benchmark clone (`empty_ok`, expiry 2026-12-22)
- Question: `MyScreens` empty_ok: the benchmark viewer owns no screens, `[]` is the right answer, expiry 2026-12-22; approve it as the one named empty answer the gate accepts?
- Options: approve `empty_ok = ["MyScreens"]` with a reason and an expiry / fail the gate on it every night.
- Decision: approve. `benchmarks/perf_bar.toml` carries `empty_ok = ["MyScreens"]` with `empty_ok_expiry = "2026-12-22"`; every other operation that answers null or empty fails the gate.
- decided by: owner
- status: final
- Note: owner, chat 2026-10-23: "Ok approved then".
- Reasoning: the benchmark viewer owns no screens, so an empty list is the correct answer, and the entry expires so it is reviewed.

## 2026-10-23 | Analyst revisions v3 (#883) | Raise the entry-closure bundle budget to 196367 B (+77 B)
- Question: the Web performance budgets job fails on #883 with the entry closure at 196297 B against 196290 B (+7 B); trim the entry or raise the budget?
- Options: trim the entry closure by at least 10 B / raise `bundle.entry_closure_gzip_bytes` to the CI value plus the usual 70 B margin / drop the catalogue change.
- Decision: keep the raise to 196367 B (CI 196297 B + 70 B), noted in `apps/web/perf-budgets.json`; inside the #773 owner waiver (ceiling 196390 B). No trim required.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Note: an Opus agent measured the delta and proposed the raise (commit c2d30f6fb); Fable reviewed the evidence (the perf-budgets.json notes, the #773 waiver entry, CI job 120340124713 of run 39931132000: `196297 B gzip is over its budget of 196290 B`) and decided. Main's own CI run on f56e951 measured 196290 B, exactly the budget, so any PR touching the chunk graph trips it. The PR's web diff touches only the generated catalogue and the lazy financials-panel widget, nothing in the entry. The next raise past 196390 B needs the owner.
- Reasoning: no honest trim exists: `SITE_FEATURES` is tree-shaken out of the entry (the catalogue names, `revisions_basis` included, ship only in the lazy FinancialsTab chunk), so the 7 B is chunk-graph and gzip noise, not code to remove; the waiver the owner gave on 2026-10-21 covers exactly this noise band.

## 2026-10-23 | Web feedback loop (harness PR) | Bundle and e2e budget headroom from 1 % to 5 %
- Question: web PRs averaged one or more red CI runs on `perf:bundle` because `update` set route budgets at measured + 1 %, a few bytes above the current size. Keep 1 %, raise it, or also loosen the shared entry budgets?
- Options: 5 % headroom on `update`, route budgets reset to measured + 5 % with a dated reason, entry budgets untouched / the same plus a 5 % waiver on the two entry budgets / no change.
- Decision: 5 % headroom (`HEADROOM_PERCENT` in `apps/web/scripts/perf-budgets.ts`); every route budget reset once to measured + 5 % with a `reasons` entry; the shared entry budgets and the shrink-only rule unchanged.
- decided by: owner
- status: final
- Reasoning: 5 of 8 red web runs checked on 2026-10-23 failed the bundle check by tens of bytes; 5 % lets ordinary changes through while a real regression (a new dependency, a leaked lazy library) still fails.

## 2026-10-23 | 1 s page gate coverage | Every new page and operation is declared for the gate; CI enforces
- Question: the gate measures a one-day crawl snapshot of the views, so a new page, tab or operation was never measured and nothing failed. Keep it manual, or make CI enforce it?
- Options: a manual refresh when someone remembers / a CI fitness test over the web source with a shrink-only exception list, plus a nightly drift flag / a crawl in CI.
- Decision: every web view with a read and every GraphQL operation must be in the gate's list (`make api-latency-views`, no crawl) or in `architecture/perf_view_coverage.toml` with a reason; the list only shrinks; CI fails otherwise; the nightly records how many operations are not covered, as a flag that never changes the verdict.
- decided by: owner
- status: final
- Reasoning: a bar nobody measures a page against is not a bar; static parsing keeps the check in CI without the clone.

## 2026-10-23 | Data-status pill PR (#902) | Two e2e route budgets raised by the pill's cost
- Question: with the badge in the entry chunk, CI's perf e2e fails two route budgets (Explore chart tab first-load JS, Admin ingestion DOM nodes). Trim, or raise those two?
- Options: trim the badge further (about 295 B and 5 nodes, no honest cut left) / raise the two route budgets by the measured overage plus a small margin / drop the pill.
- Decision: Explore chart tab `first_load_js_gzip_bytes` 304630 to 305000 B (CI 304925) and Admin ingestion `dom_nodes` 646 to 654 (CI 651); no other budget changes.
- decided by: owner
- status: final
- Reasoning: the badge is on every page by design; the overage is the badge itself, and the route budgets sit at measured size.

## 2026-10-24 | Ideas screener chips PR (#929) | Ideas DOM-node budget raised by the chips' cost
- Question: the Ideas screener chips (a badge, a link and a Guide help button per screener) put the Ideas page at 332 DOM nodes against a budget of 318. Trim the chips or raise the budget?
- Options: trim the chips' DOM (fewer wrappers, help buttons only when needed) / raise the Ideas `dom_nodes` budget by the measured overage plus a small margin / drop the chips.
- Decision: Ideas `dom_nodes` 318 to 340 (CI measured 332); no other budget changes.
- decided by: owner
- status: final
- Reasoning: the chips are the added nodes, one set per screener the viewer sees; the owner chose to raise the budget in chat on 2026-10-24.
## 2026-10-23 | Filter bar on Ideas PR (#924) | Entry and Ideas budgets raised by the filter bar's shared code
- Question: adopting the shared filter bar on Ideas puts the `f` codec in the entry chunk (the route validates its search parameter synchronously) and the bar's components and read in the Ideas page; the two entry budgets and three route budgets sit below the measured size. Trim, or raise?
- Options: cut the validation (an unvalidated `f` reaches the page) / raise the two entry budgets and the Ideas and Explore route budgets by the measured cost / drop the canonical form of `f`.
- Decision: owner waiver of the shared rule for the two entry budgets only: entry 25310 to 25780 B and entry plus static imports 197010 to 197510 B (measured locally 25603 and 197336 B, +170 B margin for CI), through the `waivers` map; Ideas page chunk 46700 to 54900 B, Ideas first-load JS 235100 to 239000 B and requests 56 to 62, Explore chart first-load JS 305000 to 305500 B, each with a reason in `perf-budgets.json`. The owner pre-approved raises that come from the filter bar's shared code in the session that started this work (2026-10-23).
- decided by: owner
- status: final
- Reasoning: one filter bar for every table, list and feed (ADR 0082) is the owner's design; the cost is the shared code itself, and later surfaces adopt it without raising anything again.
## 2026-10-24 | Filter bar on Screeners and Edges lists PR (#940) | Entry and list budgets raised by the filter bar's route state
- Question: the Screeners and Edges routes validate `f` and `q` in the entry chunk, and the two list pages load the bar's components and reads; the two entry budgets and the Screeners, Edges and Ideas first-load budgets sit below the measured size. Trim, or raise?
- Options: cut the validation (an unvalidated `f` reaches the page) / raise the entry budgets and the list route budgets by the measured cost.
- Decision: waiver of the shared rule for the two entry budgets only: entry 25880 to 26170 B and entry plus static imports 197700 to 197900 B (measured locally 25998 and 197731 B, +170 B margin for CI), through the `waivers` map; Screeners page chunk 17966 to 32520 B, Edges page chunk 48000 to 61100 B, Edge sections 82100 to 92850 B, Ideas first-load JS 240000 to 240800 B and Screeners first-load JS 209900 to 216100 B, each with a reason in `perf-budgets.json`. The owner pre-approved raises that come from the filter bar's shared code (2026-10-23, #924).
- decided by: owner
- status: final
- Reasoning: the cost is the filter bar's shared code adopted by two more lists (ADR 0082), not the lists' own code.

## 2026-10-24 | Screener run line PR (#932) | Screener results route budgets raised by the run line's cost
- Question: the run line and ten-session strip put the Screener results route over its script, request and DOM budgets (CI 256892 B scripts, 88 requests, 287 DOM nodes). Trim or raise?
- Options: drop the strip's help button and its own CSS (breaks the Guide coverage rule) / raise the three route budgets by the measured cost plus a small margin / drop the strip.
- Decision: `/screeners/vrp_scanner` scripts 256400 to 257500 B (CI measured 256892, then 257161 and 257322 as main's shared chunks shifted), requests 86 to 90 (CI measured 89), dom_nodes 272 to 292; no other budget changes.
- decided by: owner
- status: final
- Reasoning: the two extra requests and the nodes are the strip and its help button, which the Guide rule requires; the owner chose to raise the budgets in chat on 2026-10-24.
- Update 2026-10-24: after main raised the route to scripts 267500 and requests 103, CI measured scripts 268153; raised to 268300; CI then measured 105 requests against main's 103, raised to 106 (owner-approved, same decision).

## 2026-10-24 | ADR 0082 filter-bar Export | May personal-licence values leave as a file
- Question: may the filter bar export the rows a viewer filtered, and what may the file hold?
- Options: (a) none until the owner decides / (b) hybrid: files carry what the viewer can see, built server-side through the gated loader / (c) browser rows saved as a file.
- Decision: option (b) hybrid. Files carry what the viewer can see, via the gated loader (ADR 0069), personal cells LICENCE for non-holders as the ledger CSV (ADR 0064 d.10), a stamped licence notice and an audit line. Reversible by removing the route; nothing a non-holder sees today changes.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the ledger CSV already serves personal cells as LICENCE to a non-holder through the page's loader, so a file built the same way cannot show more than the page; browser rows would bypass the gate. Decided by a Fable agent on the owner's behalf while the owner was away (owner instruction 2026-10-24).

## 2026-10-24 | ADR 0082 filter-bar Export (architect review) | Hybrid export confirmed after review
- Question: the architect's review found no licence leak and three details (CSV-injection prefix, audit line, file built from the viewer's resolved session): confirm the hybrid, restrict personal cells to holders, or withdraw Export?
- Options: confirm the hybrid / restrict personal cells to holders / withdraw Export.
- Decision: (a) confirmed: the file is exactly what the viewer sees, via the gated loader with the viewer's ReadContext and session; personal cells LICENCE to non-holders as the ledger CSV (ADR 0064 d.10); `#` notice; one audit line per export; the CSV prefix stays.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: no finding showed the file holding more than the page; a holders-only variant would make the export disagree with the page and the ledger precedent; the injection fix and same-session build are safety, not scope.

## 2026-10-24 | ADR 0082 filter-bar Export | Export audit is a log line, not a table
- Question: keep the per-export audit (viewer, surface, filter hash, row count, licences) a log line, or persist it in a new table with a new writer (ADR 0005)?
- Options: (i) a log line / (ii) a new table and writer.
- Decision: (i) one INFO line per export on the `algotrade_api.export` logger under var/logs/ (stderr, `api.err.log`), carrying viewer id, surface, filter hash (never filter values), row count and licences held, no cell values; erasure of a user is covered by ADR 0066's existing manual step for API logs; reconsider a table when a third real trader is registered or an admin page needs to read exports.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: a hash and a count carry no content, so a table, writer and retention registration cost with no reader.
## 2026-10-24 | Streak filters PR (#942) | Ship the results-page history filters; hold the Ideas ones until precompute
- Question: `days_picked` and `new_today` walk the chain of previous runs lazily, only when the filter is set. Cold on the real store: a screener's results 20-480 ms, Ideas with a history filter set 3.9 s (0.89 s plain). Ship all, results only, or hold until the nightly precomputes the streak into `screen_runs`?
- Options: (A) ship as is (opt-in cost, cached per publish) / (B) ship the results-page filters, hold the Ideas filters / (C) hold the whole PR until precompute.
- Decision: B. Keep `screener_results.toml`, `results.py`, `streaks.py`, the Guide terms and their tests. Remove from Ideas: the two `[[column]]`s and the two `changed` `[[filter]]`s in `config/site/filters/ideas.toml` (restore `new_today` / `days_picked` under the header's "needs new data" list, with "precompute into screen_runs" as the reason); in `services/read/screens/ideas.py` the `streaks` import, `Idea.days_picked` / `Idea.new_today`, `_days`, `_new`, `_history`, the `history` parameter and its two branches in `_frame`, and the `history_wanted` / `without_idle` / `_history` lines in `load_ideas`; the Ideas streak tests in `test_screeners.py`; the `ideas.py` file and the "Ideas takes the longest streak" clause in the `read_ownership.toml` entry; the "On Ideas it is the longest count" sentence of `filter_days_picked` and the multi-screener wording of `filter_new_today` in `config/site/guide/glossary/filters.toml`. The Ideas filters return in the precompute PR, where they read a stored column at plain cost.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the owner's bar (2026-10-09) is every page under 1 s cold, warm and first visit, no hacks, and the 1 s gate now covers every declared operation (2026-10-23): an opt-in filter is still the page, and a 3.9 s cold read is four times the bar, so Ideas would either fail the gate or need a coverage exception for a known-slow path. The results page is within the bar, so holding it too (C) delays a measured-good feature for no gain; precompute is already the agreed follow-up and gives Ideas the filter at plain cost.
## 2026-10-24 | More filters PR (#941) | FilterFeatures listed in perf_view_coverage.toml
- Question: how the click-only `FilterFeatures` operation (sent when More filters opens) meets the 1 s page gate's coverage test.
- Options: A list it with a reason and raise the pin 13 to 14 / B send it on every Ideas load so it is captured / C run the 22-minute crawl / D a static resolver.
- Decision: A: one `[[operation]]` entry and `max_operation = 14`.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Note: the gate cannot measure a lazy, click-only operation: `web_page_ops.py` does not follow `lazy(() => import(...))`, an uncertain operation is skipped by `fast_bench.op_set`, and views the crawl discovers are not timed.
- Reasoning: B spends a request and a catalogue-sized read on every Ideas load against the request budget; C buys no measurement. Follow-up: teach the gate to time discovered click views, then shrink the list.

## 2026-10-24 | Screener run line PR (#932) | Screeners list scripts budget raised by 100 B
- Question: CI measured the Screeners list route's scripts at 217010 B against a budget of 217000 B (10 B over); the local build is unchanged at 217.0 kB. Trim or raise?
- Options: trim another 10 B (an earlier trim changed nothing locally) / raise the `/screeners` scripts budget by 100 B / hold the PR.
- Decision: `/screeners` `first_load_js_gzip_bytes` 217000 to 217100; no other budget changes.
- decided by: owner
- status: final
- Reasoning: CI noise and main's drift, not the run line's behaviour; the owner chose to raise it in chat on 2026-10-24.
- Superseded the same day: main's #945 raised the same budget to 217130 B, so this PR keeps main's value and adds no raise of its own.

## 2026-10-24 | Cohort / IV-rank percentile filters | Withhold a filter with no known value for the session
- Question: IV-rank percentile filters match zero rows for every session until about Jan 2027 (60-session history); cohort percentile filters are UNKNOWN before 2026-10-02: offer with the unknown count, hide generically, or remove the IV-rank ones from config until then?
- Options: (1) keep offering / (2) generic rule: withhold when every row is UNKNOWN for the read session / (3) remove the IV-rank filters from config, re-add in January.
- Decision: (2). A catalogue-field filter whose field has no known value for any row of the read session is served in `withheld` as Unavailable (NOT_STORED, cause "no known value for session <S>", Guide term `filter_withheld_no_data`), listed in More filters with that reason, and an input naming it is never refused (a shared link opens; the lists still read it, and as UNKNOWN never passes it matches nothing with the gap disclosed; a screen echoes it switched off, `active` false, which is in no mask). No config change.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: a control that can only return 0 erodes trust; the rule is generic (covers both cases and any future late-starting feature), costs little (one cached population read per field and published version) and reverses itself when data arrives. Implementation note: the check reads the whole population for the session once per field (`filtering/no_data.py`), not the facets of one list, because `filterSet` serves definitions before any list is loaded and every surface must agree.

## 2026-10-24 | 1 s page gate | EdgeProblems answers empty by design (empty_ok)
- Question: hand run 9b failed integrity on `EdgeProblems` (answered empty); a stale capture, or a legitimate empty answer?
- Options: a resolver / `empty_ok` / drop the operation from the measured set.
- Decision: `empty_ok`: the operation lists the viewer's own edge files that failed to load; the benchmark viewer's all load, so `[]` is correct (no variables, nothing to resolve). A fitness test now checks every timed operation has its variables.
- decided by: orchestrator (design call)
- status: final
- confirmed: owner 2026-10-24
- Reasoning: the gate must not end every night as an integrity failure; the answer is correct, only empty.

## 2026-10-24 | 1 s page gate | Owner approves EdgeProblems in empty_ok
- Question: may `EdgeProblems` join `empty_ok` in `benchmarks/perf_bar.toml`?
- Options: yes / no (resolver or drop the operation).
- Decision: yes. It reports only the viewer's own broken edge files under `config/users/<id>/`; `[]` is the normal answer; site-file faults raise and still fail the gate.
- decided by: owner
- status: final
- Reasoning: the owner's word in chat, 2026-10-24 ("Yes, i approve"), as relayed by the coordinator.

## 2026-10-24 | Edge verdicts | A post-publication out-of-sample basis for research setups
- Question: 63 of 66 setups read Not enough data because every out-of-sample period starts 2026-04-01 (5 or 6 independent decisions for a monthly setup against 40 needed); can a setup taken from published research be judged on the years after its paper's sample, without lowering `min_oos_trades = 40`?
- Options: (1) forward-only, wait / (2) lower the 40 / (3) a second, separately labelled basis from the end of the paper's sample, for eligible research setups only.
- Decision: (3). Split = end of the source paper's sample period, recorded in the site edge document; eligible only when our rule matches the paper's and the trial log shows no variant chosen after seeing results; our own setups stay forward-only; `min_oos_trades = 40` unchanged, no counting of overlapping windows or names; the two bases are never blended (UI: "backtested (hypothetical), after publication <years>" and "forward paper record since 2026-04-01"); verdicts on it need the survivorship-free universe, until then they carry the caveat and cannot be Works. Written as the ADR 0065 amendment 2026-10-25 (PR "ADR 0065 amendment: post-publication basis"); points left to the owner are listed in it and in the PR.
- decided by: owner
- status: final
- Reasoning: the owner's word in chat, 2026-10-24, as relayed by the coordinating session; the first credible verdicts should not wait a year for a monthly setup to collect 40 forward decisions, and the post-publication years are the agreed honest fast track.

## 2026-10-25 | ADR 0065 amendment (PR 967) | The eight owner decisions
- Question: the eight owner decisions listed at the end of the ADR 0065 amendment 2026-10-25: label wording, which `close` setups, the Edges list headline, deflation on the post-publication basis, one setup per paper, the attestation, the window, the short-side cap.
- Options: the recommended answer to each / another answer to any.
- Decision: the recommended answers. (1) "after publication <years>", or "after the paper's sample" where they differ; (2) accept the 12 `close` setups, each with its named difference recorded; (3) two labelled columns, forward first; (4) Works deflated by the site-wide trial count; (5) `lazy_prices_10k_change` only, not `risk_factor_change`; (6) the per-setup attestation that parameters came from the paper's text, given at registration; (7) a closed window that stops at `frozen_from`; (8) short-side setups on a survivors-only universe capped at Not enough data.
- decided by: owner
- status: final
- Reasoning: the owner's words in the orchestrating session, 2026-10-25: "Accept the recommended answers on #966, #967 and #968. Tell each session to record them and release its PR (#966 first, then #968's renumber, then #967)."
## 2026-10-24 | Workflow-first trader site (ADR 0083) | TRADER bar, verdict-backed Ideas, historical exit rule, product rules
- Question: how does the paid trader product's site fit the workflow (find, check, test) and what are its list and legal rules?
- Options: as proposed in the use-case brief and workflow design (research artifacts of the 2026-10-24 sessions).
- Decision: TRADER bar Ideas, Setups, Test, Calendar; Explore by ⌘K; Backtests dropped; Settings (no account size or risk profile); Ideas from the picks of setups with a stored verdict `works` / `promising`, one ranking rule, licence-filtered per viewer, cap 15, "Unproven" until one exists, no per-viewer index; the setup's historical exit rule (stop = the drawdown 80% of winning trades never exceeded, fallback 2 x ATR(14), hold = horizon); product rules (one nightly batch, no alerts or broker links, "publishes setups", the model only translates, every statistic labelled backtested (hypothetical) or forward paper record, methodology and risk statement, US-only launch).
- decided by: owner
- status: final
- Note: the owner accepted the recommended answers on the ADR's gaps (2026-10-25, relayed by the orchestrating session: "Accept the recommended answers on #966, #967 and #968."): evidence strength = verdict level, then `lift_pts`, then out-of-sample trades; Regime and Explore off the bar but routed; the brief carries the shared list only; Unproven keeps today's size rule.
- Note: recorded in ADR 0083, which supersedes the 2026-10-22 "Ideas ranking rule, store and licence" index decision. The legal rules are research, not counsel's opinion.
- Reasoning: the research found two open jobs at $20-100 (an evidence-backed shortlist, an honest test); the bar follows them and the list rests only on stored verdicts.

## 2026-11-01 | French factors (ADR 0089) | Residual returns v2, licence, point in time
- Question: how should Kenneth French's daily factors make residual returns measurable before 2013, and under which licence and point-in-time rules?
- Options: (i) French factors before 2013-05 and ETFs after (a splice), or (ii) French factors throughout, as v2 beside v1; licence `personal` or `open`; the lag and `knowledge_ts` rules.
- Decision: (ii), with `factor_betas@v2` and `residual_returns@v2` beside v1 and v1 unchanged. Licence `personal` (no terms stated, CRSP-derived; loosening it means scoring the v2 verdicts again). Lag of 70 days, `revised = true`, each pull's changed values stored as a new vintage. A v2 label's `knowledge_ts` is the later of the window close and the vintage date (a 0053 amendment).
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Owner action: email kfrench@dartmouth.edu asking to use the daily files as regression inputs on a paid US ideas site that serves only our betas and residuals, with attribution. A yes makes the series `open`.
- Reasoning: a splice puts a structural break in the label in 2013 (long-only ETF spreads vs long-short research factors), and CAPE set the precedent for the licence.
## 2026-11-01 | Options-setups backend ADR 0088 | licence of market states, scope of the strictest-field rule, gate licence, holdout dates
- Question: (A) are the stored `market_conditions@v1` states open or personal; (B) does the strictest-field licence rule reach screener and universe fields; (C) does it apply to a gate; (D) what `holdout_from` does each research source give?
- Options: A open (recommended) or personal; B gate/entry/case/exit only (recommended) or every site; C confirm the reading or not; D per-source dates.
- Decision: A open; B gate, entry, case and exit only (0064 decision 10 not amended); C confirmed, a gate's fields are recorded in the trial licence; D first session after each source's data end: 2026-10-26 default for the three option-setups research files (earliest verdict 2027-01-26), Spintwig 2025-01-02, Lambda 2026-01-02, ORATS-only earnings 2026-03-02, AI study 2026-11-02.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Note: reversible; decided while the owner was asleep.
- Reasoning: A follows the `regime@v3.label` precedent and flips by `Feature.licence` with no recompute; B keeps existing setups visible; C follows from a gate being a rule; D never lets a gate be judged on data its research read. Recorded in ADR 0088 (PR #984).
## 2026-11-01 | Survivorship-free listing history (ADR 0087) | Delisting return convention; pull the data now
- Question: (1) which return to book for a bankruptcy or listing-standards delisting with no OTC print; (2) renew Tiingo Power, or pull the data now?
- Options: (1) (a) CRSP-style replacement -30% NYSE / AMEX, -55% NASDAQ, zero figure shown beside / (b) unmeasured / (c) zero. (2) renew one month / do not renew and wait / rush PR2 and backfill before 2026-11-09 / renew longer.
- Decision: (1) (a): a delisted name a setup would have bought is penalised, never flat. (2) pull the data now: the Massive delisted list was started on 2026-11-01; the Tiingo bars for the new ids follow PR2's ids; the renewal is raised again only if PR2 and that pull cannot both finish before 2026-11-09.
- decided by: owner
- status: final
- Reasoning: the owner's words in chat, 2026-11-01: "Ideally anything delisted if the setup suggests buying them it is a problem we should pick any options which penalizes picking a delisted stock is traded" and "let us pull the data. we still have enough time to do it. Let us start the backfill immediately." Decisions 3 to 5 of the ADR stay open.

## 2026-11-01 | Survivorship-free listing history (ADR 0087) | Decisions 3 to 5
- Question: (3) hold the 2010 `outcomes` backfill and `evaluate-edges` until the backfills (PR3) are done; (4) ETF closures before 2016 stay out of the universe, disclosed; (5) Norgate Platinum ($630 a year, Personal Use licence)?
- Options: as recommended in the ADR / the alternatives named there.
- Decision: (3) hold, as recommended. (4) stay out, disclosed, as recommended. (5) not now, as recommended; at most an owner-only cross-check.
- decided by: owner
- status: final
- Reasoning: the owner's word in chat, 2026-11-01: "3 to 5 aligned with your suggestion."

## 2026-11-01 | fundamentals@v5 IFRS share count (PR #965) | refetch and backfill, retiring v4, the net_share_issuance frozen period
- Question: (1) authorise the live-store refetch and history backfill; (2) retire `fundamentals@v4`; (3) how to treat the `net_share_issuance` edge's frozen period (from 2026-04-01) now that its input moves to v5?
- Options: as recommended by the architect re-review / the alternatives (no backfill, keep v4, restart the frozen period).
- Decision: (1) yes: `shares --force`, then the rollups backfill `--only fundamentals@v5`; (2) yes, retired only after the v5 backfill covers the full history (`retire-features --dry-run` first); (3) keep `frozen_from = 2026-04-01`: v4 values carry over unchanged and v5 only adds names that had no count, recorded as a coverage change in the edge notes and the run's trial log.
- decided by: owner
- status: final
- Reasoning: the owner's word in chat, 2026-11-01: "Yes, all three" (the architect's recommendations). `SHARE_CONCEPTS_VERSION_DATE` = 2026-11-02, the first nightly with the merged code.

## 2026-11-01 | Setups as positions and rules (ADR 0088) | Exits as values or rules, share path exits in P1, X1 monthly entry
- Question: (a) can an exit (and an entry) be a fixed value or a rule; (b) do share setups get path-aware exits in P1 or P2; (c) does X1 `index_put_write` enter every session or monthly?
- Options: (a) values only / values or rules; (b) P2 / P1; (c) `every_session` / the Cboe PUT roll date with the ladder as a variant.
- Decision: (a) both: a fixed value or a rule, compiled to one ordered list (ADR 0088 decision 4). (b) P1: build-table row E3c, a share path walker over `bars/1d` reusing E3b's exit evaluator, its trades in the trade contract, needing E3b and E6a, architect review (point in time); a setup without `[outcome.exit]` changes no stored verdict. (c) X1 enters on `calendar:after_monthly_expiry` (the first session after the monthly expiry, gated); the every-session ladder becomes a variant.
- decided by: owner
- status: final
- Reasoning: the owner's words in chat, 2026-11-01: `every_session` opens overlapping puts daily, so a fixed monthly entry matching the PUT index is the honest baseline; exits and entries are values or rules alike; share setups should get rule exits now. Recorded in `docs/options/backend-build.md` and `backend-concepts-1.md` (2.4a).

## 2026-11-01 | ADR 0083 amendment (Evening Desk site) | Ideas tabs, idea page, watchlist, sign-up answer, derived option figures
- Question: how do Ideas, the idea detail, a watchlist, the sign-up answer and option quotes work on the Evening Desk site?
- Options: as the mockups show / as amended below.
- Decision: (a) Ideas has Stocks | Premium tabs; the default comes from one sign-up answer; the cap of 15 and the Unproven fallback apply per tab. (b) A per-pick idea page, its sections filled from the setup: why it is here, the plan (the setup's historical exit rule), evidence, what could go wrong, learn this setup. (c) A watchlist: a per-user ticker list stored as user config (ADR 0029), filtering Ideas; tickers only, no quantities, basis or positions. (d) The sign-up answer is stored as a preference. Option quote display B: option screens show only our own derived figures (yield %, delta bands, return on collateral), never raw bid / ask, because the Cboe feed is unlicensed for display.
- decided by: owner
- status: final
- Reasoning: the owner's decisions of 2026-11-01 on the Evening Desk mockups, relayed by the orchestrating session. Recorded as the ADR 0083 amendment 2026-11-01; build plan `docs/ui/evening-desk-plan.md`.

## 2026-11-01 | Evening Desk plan | Product questions the mockups raised
- Question: (1) which option figures count as derived; (2) the raw-quote Options tab and `GET /chains/{underlying_id}/live`; (3) watchlist filter before or after the cap, and its size; (4) a "Yours" Ideas tab; (5) Past lists now; (6) what "Both" defaults to, and a start-page choice; (7) Settings scope; (8) the buying-power inputs; (9) typed sold-at price and cost basis; (10) the idea page's wording; (11) a Sunday premium edition; (12) premium strategy tests for traders; (13) the tab of an Unproven screener that implements no setup.
- Options: per question, the mockup / the plainest default within the fixed rules.
- Decision: (1) our computed mid premium, spread as % of mid, open interest and volume, a straddle from mids, IV, IV rank, delta, yield %, return on collateral, breakeven and probability below the strike are shown; never a vendor bid, ask, last or size. (2) Both stay, admin-only (role gate and REST `redact`); the plan's V6 removes the raw columns from trader screens. (3) After the cap (it only narrows tonight's list); at most 50 instruments. (4) No: Ideas is Stocks | Premium; the watchlist lives in Settings and the ticker Watch toggle, followed and own setups on Setups. (5) Deferred to its own ADR (ADR 0083 decision 2). (6) Both -> Stocks; one preference (the default Ideas tab), no start-page choice. (7) In: theme, default tab, country shown read-only (US), sign out; out: nightly brief toggle, plan / trial, data download, account deletion. (8) A typed contract count (component state only), Reg-T only, no named broker rules. (9) Never stored: not in the URL, `localStorage`, user config or logs. (10) "The setup's rule holds Monday at a premium of $0.55 or more"; "Copy exit rule as text"; "The plan" shown as the historical exit rule. (11) No: the same nightly list. (12) Owner-only now (ADR 0088 decision 12). (13) Stocks.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: each keeps the fixed rules (publisher only, no sizing or stored positions, one nightly batch, labelled statistics, decision B) with the plainest default; a mid, a spread ratio and a straddle are our computations and OI / volume are exchange statistics, not quotes; billing, brief delivery and the scorecard have their own ADRs; HOD-derived evidence stays owner-only until its terms are read.

## 2026-11-01 | Evening Desk plan | Vertical slices, no new components, the option grid's grain open
- Question: how is the Evening Desk build cut, and how are the architect's and the simplicity review's findings folded in?
- Options: slices by layer (design system, pages, reads) / vertical slices that each ship one screen end to end.
- Decision: vertical slices V1-V12 on data that exists today, then O1-O4 following the options backend (E4, E6, E9-E12b); every mockup element mapped to an existing component or a variant (no `Stepper` or `Breadcrumb`); the Ideas setup-picks read gets its own owner (`ideas-setup-picks`, `services/read/ideas/`) with `ideas-list` narrowed to Unproven, the inverse pick reads outside `pick_edges.py`; Reg-T stays in `services/preview/options/`, not `quant/`; the option grid's grain (a read over the stored chain plus a small catalogue group, or a catalogue group only) is the architect's first call in V6; `put_wing@v1` / `call_wing@v1` unchanged.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the owner's instruction of 2026-11-01 ("new screens are available and work end to end, incrementally"); the architect review (file-disjointness, ownership, licence, cache key) and the simplicity review (cut two components, merge slices).

## 2026-11-01 | V7 onboarding | The sign-up question has two answers and the skip button starts with shares
- Question: the mockup offers Stocks / Options / Both plus an optional watchlist; the amendment stores one `[ideas] default_tab` of `stocks` or `premium`. What does the question offer, and what does the skip store?
- Options: three answers with Both = stocks / two answers (mostly shares, mostly options), Skip stores shares / Skip stores nothing and asks again.
- Decision: two answers, "Mostly shares" (`stocks`) and "Mostly options (selling premium)" (`premium`); Skip stores `stocks`, so the question is asked once; the watchlist is added in Settings or with the Watch button, not in the question.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the stored value has two states; asking again on every visit after a Skip would nag; the user can change it any time in Settings.
## 2026-11-01 | V8 Calendar PR (#1027) | /calendar distant-link budget raised by the Earnings week table
- Question: the Earnings week table (FeatureTable, the column factories and the column picker now load on `/calendar`) puts the route at 357013 B gzip on the wire against the shrink-only `network` budget of 334800 B (+22 kB). Raise once, or make the week view lighter?
- Options: raise the one route budget to measured + the 5 % headroom with a dated reason / a lighter week view (a lazy table chunk, the picker split out) / drop the table for a list.
- Decision: raise `network./calendar.wire_gzip_bytes` once to 374900 B (CI 357013 B + 5 %, the #909 headroom), with a `reasons` entry "2026-11-01 #1027 the Earnings week table is the Calendar's default view: FeatureTable, its column factories and the picker load with the page; the table is the feature, not a shared-code move"; no other budget changes. No lighter view: the table is the default view, so a lazy chunk would still load on first paint and add a request over the request budget, and the picker split out saves well under a kilobyte.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the same shape as #939's Explore raise (+23 kB, "the table is the feature"), the owner's only precedent for a wire raise that is not filter-bar shared code; the 5 % headroom is the owner's rule of 2026-10-23 for route budgets; a feature's cost belongs in its budget, and shrink-only means a hand raise with a reason, never `PERF_UPDATE`.

## 2026-11-01 | V8 Calendar PR (#1027) | Earnings week table: filter-bar exemption, time-boxed
- Question: `architecture/web_filter_bar.toml [exempt]` gains `src/pages/trader-calendar/ui/EarningsWeek.tsx` (the week's reports of the scope list or one screener's picks, narrowed by the source picker). The rule says a table of many rows is never exempt and `[migrating]` takes no new line. Exempt, or build it on `SurfaceFilterBar` now?
- Options: exempt with a dated follow-up / build on the bar now over a `calendar_week` surface (`config/site/filters/calendar_week.toml` with filters on `rollup.earnings@v1.next_earnings_date`, `earnings_time`, `feature.earnings_move_vs_usual`, the overpaid counts and chain liquidity; their Guide terms in `guide/glossary/filters.toml`; `FeatureTable` in server mode with `keys` and `filters`, which the instruments read already combines; a views scope) / build on the bar now reusing the `universe` surface's filters with a scope of its own.
- Decision: exempt, time-boxed: the reason line names the follow-up slice V8c and its date, due by 2026-11-08 (the PR after the earnings pricing features' first nightly), and V8c builds the `calendar_week` surface above and deletes the line; the exemption is not a precedent for any other many-row trader table (the two admin "not yet on the bar" lines are the only other ones, and both carry a follow-up).
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: a `calendar_week` surface built today would serve every meaningful filter as `withheld` (NOT_STORED): `earnings_moves@v1` and `implied_move@v1` have no rows until their first nightly after this PR merges, so the bar would be empty chrome on the Calendar's default view; reusing the `universe` surface (sector, market cap, liquidity) is less code but filters a week's reports by the wrong axes and would conflate saved views with Explore's. The rule's intent (every many-row table gets the bar) holds through the dated line; the owner may instead choose the `universe` reuse now, which costs a filter-bar shared-code raise on `/calendar` (pre-approved) on top of the raise above.
