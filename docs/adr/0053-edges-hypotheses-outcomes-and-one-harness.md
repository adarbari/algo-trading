# ADR 0053: Edges: hypotheses with evidence, an outcomes grain and one point-in-time harness

**Status:** accepted, amended by [0065](0065-verdict-basis-fixed-before-the-frozen-period.md) (the verdict's basis) (2026-10-07; owner decisions 2026-10-06 and 2026-10-07; the plan and items
are [edges-plan.md](../edges-plan.md), the long form is the owner's PRD "Winners-Derived Screener:
Product Requirements"; the open decisions below are the owner's before the item that needs each); amended by [0064](0064-edge-evidence-series-and-trade-ledger.md) (the optional `[published]` table of an edge document).
Extends [0005](0005-ingestion-is-the-only-writer.md) (ingestion writes the outcomes),
[0007](0007-point-in-time-data.md) (an outcome is knowable only when its window closes),
[0015](0015-configs-selections-users.md) (the edge document is a layered settings file),
[0021](0021-option-pricing-conventions.md) (the statistics live in `quant/`) and
[0033](0033-screeners-run-nightly-and-on-request.md) (a screener run for a past session). Makes
one confined exception to [0036](0036-session-strictness-for-reads.md). The winners study's
historic listings (ED6) get ids by the amendment to [0018](0018-figi-instrument-ids.md)
(`EQ:TIINGO:<permaTicker>`).

## Context
The platform screens: a rule screen or a Python `Screener` picks names for a session from stored
features. Nothing says whether its picks did better than the names it passed over. A screen is
an opinion with no track record, and the owner's question about any idea ("if it worked, someone
would already be using it") has no answer in the system. The owner first asked for a study of
past winners to derive screens from what they had in common, then reframed it (2026-10-06): the
unit is not a screen and not a model but an **edge**, a written hypothesis with a reason it
persists, a defined outcome and evidence gathered point in time. Screens are ways of
implementing an edge; a learned model is one more implementation, and is never what decides
whether the edge is real (a model that finds patterns in the same history it is scored on is the
overfitting the harness exists to catch).

Two facts shape the first version. The store's daily bars start 2024-10-03 (2018 for the event
scope names, ADR 0050), so only short horizons (5 to 60 sessions) have complete outcomes today;
the harness is proven on those before any decade-long backfill. And every read today serves one
session (ADR 0036); judging a pick needs what happened after it, which no read may see.

## Decision
1. **The edge document.** An edge is a typed settings file `config/site/edges/<id>.toml` (an
   `Edge` settings type through the one settings loader; a user may draft one under
   `config/users/<id>/edges/`, layered per ADR 0015): thesis, mechanism and persistence reason,
   the **outcome** (horizon in sessions, benchmark, path condition such as a drawdown cap), the
   evaluation schedule and universe, top K, the frozen period, status (`candidate`, `evidenced`,
   `retired`, `rejected`, `blocked`, with the reason) and the **screeners** that implement it.
   `docs/edges.md` is generated from the documents by `make features-doc`.
2. **Screeners are implementations; one edge lists many.** A screener stays what it is (a site
   preset rule screen, ADR 0029, or a Python `Screener`); the edge names it by id. Nothing about
   screener presets, their nightly and on-request runs (ADR 0033) or their reads changes.
3. **The outcomes grain.** `outcomes/instrument/<name>@v1` in `architecture/tables.toml`, one row
   per (instrument, start session S): `session_date` = S, `knowledge_ts` = the close of the
   window's last session, the outcome fields (forward return, excess return over the benchmark,
   the path fields). Rows are written only by ingestion: a task in
   `apps/ingestion/.../tasks/derived/` writes every window the session closes (a nightly step of
   `market-daily` after the rollups, ADR 0039) and a one-off backfill writes the past, with the
   rule that backfilled rows equal nightly rows. A window not yet closed has no row.
4. **Outcomes are quarantined.** They are read only by `algotrade.data.outcomes`, and that module
   is importable only from `services/evaluation`: an import-linter contract, plus a fitness test
   in `tests/architecture/` that no screener, strategy, feature group or read loader imports it.
   A screener cannot see the future because nothing it can import serves it.
5. **One cross-section harness**, `services/evaluation/cross_section.py` beside `suite.py` and
   `regime_scorecard.py`. For each session S in the edge's schedule (spaced at least one horizon
   apart, from `engines/selection/schedule.py`) it runs each listed screener for S through
   `engines/screening/runner.py` on what was known at S, takes the top K, and joins the closed
   outcomes. Measures: hit rate (an unclosed window is excluded, never a miss), base rate over
   every eligible name at S under the same condition, lift, mean excess return of the picks,
   decile spread over all eligible names ranked by score; each per year, per `regime@v3` label
   and for the frozen period alone, with the number of independent sessions beside every number.
   Every variant tried is a row of the run's trial log. The size and 12-1 momentum screens run on
   the same sessions as baselines (the quality bar's question 9).
6. **Statistics in `quant/`** (numpy only, rule 1): lift, standardised effect size, decile spread,
   deflated Sharpe ratio, probability of backtest overfitting. `architect` reviews the module.
7. **Results.** A harness run is a run (run id, config hash, ADR 0015) written to
   `results/edge_eval` by the backtest app's CLI `algotrade-backtest evaluate-edges [--edge ID]
   [--from --to]`, the same writer as backtest results. `make evaluate` prints a golden subset
   against `benchmarks/baseline.json`. The read object, GraphQL type and trader UI (odds line on
   Ideas, track-record chip on Screeners, the Edges list) come later through the read model
   (ADRs 0037, 0038) and the Guide (ADR 0051).
8. **ML is discovery and one implementation, never the judge.** An offline study of past winners
   proposes candidate documents; a learned scorer is a stored feature and an `impl = "model"`
   screener scored by the same harness as any rule. Promotion is site config, after it beats the
   rule implementation of the same edge in the frozen period.
9. **The quality bar.** A document is accepted only when it answers all nine questions of the
   plan: mechanism, persistence, outcome, trigger timing (`known_from` and the first session we
   act), faithful replication of the source's rule first, expected size and sample (at least 40
   independent events in the history held), capacity and costs, failure modes and the retirement
   rule, and decoys (the simpler explanation, compared with the baselines). Rejected and blocked
   candidates stay on file with the reason.

Rejected: scoring screens by backtest P&L alone (it mixes the edge with sizing, exits and costs,
and has no base rate); letting a model rank edges (it would grade itself on its training history);
computing outcomes on the fly in the harness (a second reader of future bars outside ingestion's
acceptance checks; a stored grain is backfilled once and verified like any table).

## Consequences
- **The one exception to ADR 0036's one-session rule:** the outcomes grain is read across
  sessions, and only by the harness. Every page read, screener, strategy and loader keeps reading
  one session; the import contract and the fitness test make the exception mechanical, not a
  convention.
- New: a config folder (`config/site/edges/`, declared in `architecture/layout.toml`), a
  settings type, a generated doc, a table family (`outcomes/instrument/*`), a `results/edge_eval`
  table, and the responsibilities `forward-outcomes` and `edge-evaluation` in
  `architecture/ownership.toml` (ED1 to ED3 add them with their owners). `src/algotrade/data/` is
  at its module cap, so ED2 may make `algotrade.data.outcomes` a package; the import name and the
  contract do not change.
- Unchanged: screener presets and their runs (ADR 0033), catalogue reads by name (ADR 0038), the
  writers (ADR 0005: ingestion writes outcomes, the backtest app writes results), the regime gate.
- Only edges whose horizon fits the stored history can be evidenced now; a long-horizon edge
  stays `candidate` until the history it needs is backfilled (ED6). An edge with fewer than 40
  independent events waits.
- The trader sees numbers only with their base rate, event count and run; an edge never shows a
  bare hit rate.

## Open decisions (owner)
- ~~The frozen period~~: decided 2026-10-08, 2026-04-01 (amendment below).
- The ED4 outcome definitions (proposals in the PRD): the volatility risk premium, realised below
  implied over the option's horizon with a drawdown cap on a short-straddle proxy; post-earnings
  drift, excess return over SPY over 20 and 60 sessions with a cost assumption; the earnings
  announcement premium, excess return over SPY from five sessions before to one after.
- The cap threshold for the drift edge: proposal, below $2B (the harness reports by bucket either
  way).
- ~~The runtime home of learned scorers (ED7)~~: decided 2026-10-08, see the amendment below.
- If ED2 finds the grain must differ from decision 3, it amends this ADR in the same PR.

## Amendment (2026-10-07, ED2): the grain as built
Decision 3 holds; ED2 fixes what it left open.
- **One table, no stored hit.** `outcomes/instrument/forward_returns@v2` (fixed schema in
  `storage/tables/schemas.py`), one row per (instrument, start session S, horizon, benchmark):
  `window_end` (T, the h-th exchange session after S), `fwd_return`, `fwd_excess_return`,
  `fwd_max_return` and `fwd_max_drawdown` (intraday highs and lows after S: the path a drawdown
  cap tests), `fwd_realised_vol`, `outcome_status` (COMPLETE, or DELISTED when the latest reference
  snapshot records the name delisted after S: measured to its last bar, a zero return and no
  volatility when that bar is S; the delisting return itself is not measured; a gap at T, or a
  name not yet recorded as delisted, has no row and a reason in the run). `delisted_on` is the
  session the weekly reference build noticed the delisting, after the last bar, so each night
  recomputes the last 10 window ends and a reason becomes a DELISTED row once it is recorded;
  runs merge, so a re-run never retracts a row it no longer computes. Whether an
  edge's outcome held (its target, direction and drawdown cap; for `realised_to_implied_vol` the
  implied volatility at S, a one-session read) is computed by the harness from these fields
  (ED3), so a document edit never rewrites the grain.
- **Horizons and benchmarks come from the documents.** The union over the site's edges that are
  not rejected or blocked, plus 20 sessions over SPY (the harness default); the benchmark ticker
  becomes an id through the resolver (ADR 0018). A new edge needs no code change.
- **`knowledge_ts` is the write time**, as for every stored row (ADR 0007), never before the
  close of `window_end`: the task refuses a window that has not closed. Partition S receives one
  run per horizon on different nights, so runs merge, the latest row winning per (instrument,
  horizon, benchmark); a backfill is one run per window end (exactly the nightly's), and
  `read_outcomes` filters rows by `knowledge_ts` as well as runs.
- **Return basis**: price return, split-adjusted as of T; total return is a later `@v2`.
- **Eligible names** are the universe at S with a bar at S. Universe snapshots start 2026-10-02,
  so every earlier window uses that snapshot (`pre_snapshot` in the run's stats): survivorship
  the harness must report until ED6's listing history. Bars restated after T are read as stored
  when the backfill runs.
- The nightly step `outcomes` needs `bars` and `corporate-actions` (the splits), is optional,
  and its acceptance recounts the eligible names: each has a row or a reason. The task reads
  each window's bars through `data.prices.session_bars` (split-adjusted as of the window's
  end, the read rollups use), an `allowed` reuse under `feature-input-loading`.

## Amendment 2026-10-08: learned scorers run in the ingestion app (owner decision)

The runtime home of learned scorers (ED7) is `apps/ingestion`: the `edge_score.<edge>@v1` scoring
task trains and scores there, and its model dependency goes in the ingestion app's pyproject (rule
8). No fifth app. Ingestion stays the only writer of the scores (ADR 0005); screeners read them
as catalogue features (ADR 0038).


## Amendment 2026-10-08: the frozen period starts 2026-04-01 (owner decision)

Every open edge document sets `frozen_from = 2026-04-01` (the last two quarters of the stored
sessions when ED4 starts): fixed, never rolling; the harness reports it as its own slice and an
edge is `evidenced` only on it. A fitness test pins the date
(`tests/architecture/data/test_edge_outcomes_expressible.py`); moving it is a further amendment.

## Amendment 2026-10-08: ED4 (decision and entry sessions, events, variants, `expires_otm`)

Decided on the owner's behalf on 2026-10-08, from the owner's inputs. The owner judges short
premium by how often the option is not assigned, trades 21 to 45 days to expiry, and accepts IBKR
IV for a private evaluation. The research (with sources) is in the ED4 PR descriptions; `architect`
corrected it on point-in-time grounds.

1. **Decision and entry sessions.** A harness row has a decision session D and an entry session
   S, always with S > D. The screen, eligibility, IV and the event set are read at D. The
   outcome is the partition at S. An event counts only when `known_from <= D`.
   - Non-event schedules: S = D + `start_offset_sessions`, with an offset of at least 1. The
     screen runs after D's close, so the first fill is at S's close.
   - Event schedules: the offset places the entry relative to the event's anchor session,
     S = anchor + offset and D = S - 1.
     - Post-earnings drift: anchor E+1 (the reaction's end), offset 1, so S = E+2 and D = E+1.
     - Earnings announcement premium: anchor A (the expected report), offset -5, so S = A - 5
       and D = A - 6.
     - A negative offset is allowed only for an event announced ahead. An event class not
       announced ahead needs an offset of at least 1.
   - The offset lives in the documents and the harness, never in the grain. Only a new horizon
     needs an outcomes backfill.
2. **Expected report dates, never actual dates.** The stored history knows a report date only
   from that day (`known_from` = the report date before 2026-10-13). So the pre-announcement
   window reads `earnings_expected@v1`, whose `expected_basis` is one of:
   - SCHEDULED: a date known by D;
   - PRIOR_YEAR: the year-ago same-quarter report + 364 days, known from that report
     (Frazzini and Lamont's method);
   - UNKNOWN: excluded with a reason, never read as "no earnings".
   The VRP earnings exclusion reads the same group.
3. **Post-earnings drift's surprise** is the two-session excess return over SPY, close(E-1) to
   close(E+1) (Brandt, Kishore, Santa-Clara and Venkatachalam 2008). 72% of report times are
   unknown, so a single reaction session is unreliable. The anchor is E+1 and the entry is
   E+2's close. Liquidity is read on a pre-event 20-day ADV. The edge is long-only (a long-short
   variant is a trial row), with 40 bps of cost.
4. **`expires_otm`, the VRP win rate.** A new outcome kind for a short option that expires out
   of the money.
   - Structure: `put` | `call` | `strangle`.
   - The strike comes from an exact Black-Scholes delta with r = q = 0,
     K = P·exp(∓zσ√T + σ²T/2) for the entry close P at S (what `fwd_return` is measured from), - for
     the put and + for the call, δ = |delta|, z = N⁻¹(1 - δ) > 0, and σ the `iv_field` read at D
     (or `otm_pct`).
   - The hit compares `fwd_return` with K/P - 1.
   - The reference rate is the mean risk-neutral N(d2) per name (the joint form for a
     strangle), not 1 - δ.
   - A touch rate (the strike crossed intraday) is reported beside the hit, never inside it.
   - Horizons: 15, 21 and 31 sessions (21, 30 and 45 calendar days).
   - Caveat: a win rate carries no premium and no P&L, and overstates expectancy (the short
     left tail). `realised_to_implied_vol < 1` stays as a second row.
5. **Edge variants.** Cap buckets, structure, delta, the earnings exclusion, Savor and Wilson's
   [-1, +1] window and the realised-to-implied row are `[[variants]]` in the document, with
   outcome, universe, base and picks overrides. They are not session slices. Each variant is a trial in the
   deflated Sharpe ratio. `results/edge_eval` gains the key column `edge_variant` (null read as
   "main") and the columns `iv_source`, `licence`, `reference_rate` and `touch_rate`.
6. **One IV field per variant row** (`iv_field` on the outcome; a run parameter is the default):
   never a mixed-source feature. The row records
   `iv_source`, and the licence comes from the catalogue's `Feature.licence` (personal for
   IBKR's).
7. **Event schedules.** `on_event:<class>` takes the event names at D from a declared field per
   class (the classes are `earnings_reaction` and `earnings_expected`, replacing `earnings` and
   `earnings_scheduled`):
   - `earnings_reaction@v1.sessions_since_reaction == offset - 1`;
   - `earnings_expected@v1.sessions_to_expected_report == 1 - offset`.
   Both read at D = S - 1, consistent with item 1. Events are deduplicated by (name, quarter)
   when a PRIOR_YEAR expectation turns SCHEDULED. A name with no row is UNKNOWN (excluded with
   a reason), never "no earnings" (the VRP earnings exclusion included).
   Event days are pooled into blocks, one statistic per block: a day joins a block while it is
   fewer than h decision sessions after the block's first day, so a block spans at most h
   sessions (measured from the last day, daily earnings chained two years into one block,
   2026-10-08). The last windows of one block overlap the first windows of the next by up to
   h - 1 sessions, the price of keeping every event; with dense events only common moves carry
   it (a lag-1 correlation of at most about 0.17), so t statistics and the deflated Sharpe ratio
   are overstated by at most about 15% on event edges; plain schedules have no overlap. The picks are the screener's
   qualified names within the event names (`picks = "event"`, the default; `picks = "universe"`, settable per variant, takes them from every eligible name on the event sessions: a decoy). The base (`base = "event" | "universe"`) is the
   event names, or the universe for the announcement premium. A name eligible at D with no row
   at S is excluded as `no_entry_bar`.
8. **Train and test split in the UI** (ED5). The site `frozen_from` stays the only evidence
   gate: an edge's status changes only from a run whose split equals it. A user may set
   `split_from` per run, or, in a copy of an edge, its own `frozen_from` (the user-wide
   `evaluation.toml` was deleted by the amendment of 2026-10-09; ADR 0015 layering: site < user < run). The run records it with its config hash. Every number from a split that
   is not the site's is labelled EXPLORATORY in the read model and the UI. The track-record chip
   never reads one, and a fitness test forbids a status change from one.
9. **Option history.** No free source has usable history. The Cboe chains captured daily since
   2026-10-02 are the evidence set going forward. Massive's free Options Basic tier (EOD
   aggregates of expired contracts, 2 years, 5 calls a minute, no bid/ask or IV) is the
   candidate backfill when real premiums are needed (a later item).

## Amendment 2026-10-08: ED7a, the first learned scorer (a probit in site config)

Decided on the owner's behalf (architect review of the diff). ED7a ships the machinery for
learned scorers; the model is the regime probit (`quant/probit.py`, the expression engine's
`ncdf`), not a new dependency. A logistic would need a new `exp` built-in in the engine, and the
probit is the same model class with the precedent already in place. LightGBM (ADR amendment above:
`apps/ingestion`) comes only if the probit loses to the rule screener in the frozen period (ED7d).

1. **The training boundary.** Labels reach a fit only through
   `services/evaluation/training/frame.py` `training_frame`. With `cross_section/harness.py` it is
   the only importer of `algotrade.data.outcomes` (a fitness test checks both; the import contract
   still allows `services.evaluation`). Rows are (instrument, decision session D) of the edge's
   schedule; the features are the document's `[scorer] features`, read at D only; the label is the
   edge's hit for the window starting at S. A row with a missing feature is dropped, never filled.
2. **The fit never sees the frozen period.** A window is kept only when it closes (`window_end`)
   before the session one horizon before `frozen_from` (purged: no label overlaps the frozen
   period; embargoed: one horizon between the last training window and the first frozen one).
   `window_end` is read, not `knowledge_ts`, which is the write time (a backfill writes old windows
   today). `fitted_through` is the latest kept `window_end`.
3. **Coefficients are a TOML expression feature.** `algotrade-backtest fit-edge-scorer --edge ID`
   (through the `edge-score-fit` job) writes `[edge_score_<edge>]` in
   `config/site/features/edge_scores.toml`: `ncdf(b0 + sum w_i * (x_i - m_i) / s_i)` with every
   coefficient a param, and the fit (`fitted_through`, rows, sessions) in the description. A site
   config change reviewed via PR: the command writes the file, the owner commits it. A re-fit
   bumps the feature version. Nightly scoring is the expression engine reading the file: no label
   exists at score time and no ingestion task is needed.
4. **Fitness test.** Every `edge_score_*` feature names an edge with `frozen_from` and records
   `fitted_through` strictly before it, and reads exactly the features the document declares.
5. **Refusals.** A fit needs at least 40 independent decision sessions before the frozen period (the quality bar's count) and refuses with the count it has: no scorer file is committed while the stored history gives fewer (momentum_12_1 has 3). A declared `rollup.<group>@v<n>` must be the registry's current version of its group (a fitness test and the renderer check it), and the description records `horizon` and `fitted_through`, which must precede the purge cutoff.
6. **Not yet.** Event schedules and outcomes that read an implied vol are not fitted (the
   command refuses). Shipped in ED7b and ED7c (7 and 8 below).
7. **The model screener (ED7b).** `impl = "model"` is a rule screen (same base gates) with
   `score = "feature.edge_score_<edge>"`: the score is a last gate (`>= 0`: a missing score never
   passes) and the only rank. Every slice of a model screener that holds a session before
   `frozen_from` (all, year, regime, an earlier exploratory split) carries `in_sample = true` on
   its `results/edge_eval` rows; only the frozen slice is evidence, and the track record skips
   in-sample rows. A fitness test requires its score's `fitted_through` before the purge cutoff.
8. **Promotion (ED7c).** `[implementation] promoted = "<screener>"` on an edge document names the
   screener that implements the edge for use. Allowed only for a model screener the edge lists,
   on an evidenced or live edge citing its frozen run, with a rule screener to beat. The model
   beats them when, at every horizon of the edge, the frozen slice of that run shows its lift AND
   its decile spread strictly higher than each rule screener's, every compared row with at least
   40 independent sessions (`MIN_INDEPENDENT_SESSIONS`, the fit's bar too); a missing number or
   row fails (`services/read/evaluation/promotion.py`). Two enforcements: the document commits the
   compared numbers (`[[implementation.compared]]`) and a fitness test runs the comparison over
   them; and the reader (`load_promotion`) honours `promoted` only when the same comparison over
   the cited run's stored rows is clean, else the edge is reported NOT promoted with the reasons.


## Amendment 2026-10-08: Report containment (diagnostic)

For an `on_event:earnings_expected` edge, the harness may read `events/earnings` rows known after
D (as of the run's `as_of`, through `data.events.stored_events` and `earnings.valid_events`) only
to count how many closed windows contained the real report (`cross_section/report_containment.py`).
It is a diagnostic: never a pick, filter, weight, hit or status input; it is reported only (run
record trial log, job result, CLI report). It is an allowed reuse under `feature-input-loading`,
like the forward outcomes' bar read. A fitness test keeps `stored_events` out of every other
module of `services/evaluation/cross_section/`.

## Amendment 2026-10-09: ED6, the winners study

ED6 asks what was true of the biggest winners before they won: instruments in the top 2% of
excess return over SPY across 504 sessions, against matched controls, over a grid of start
sessions. Plan: `docs/edges-plan.md`. W1 (this change) is configuration and the horizon; the study
itself follows.

1. **The study is a second reader of outcomes.** Besides the edge harness, the winners study reads
   `outcomes/instrument/forward_returns@v2` (through `data/outcomes`, from `services/evaluation`
   only: the exception to the one-session rule stays confined to that package). Its horizon (504)
   and benchmark (SPY) are declared in `config/site/studies/winners.toml` (typed by
   `config/edges/winners.py`), and the outcomes task's `horizons_and_benchmarks` adds them to those
   of the open edge documents. 504 exceeds `NIGHTLY_MAX_HORIZON`, so it is computed only in a
   `--from/--to` backfill.
2. **Results are a table, `results/winners_study`.** One run per table version, rows per
   feature x block plus pooled; written atomically by the backtest app (point 4). Its schema and
   `architecture/tables.toml` entry arrive with the job (W3).
3. **Drafts live in `var/`, never `config/site/`.** The study may propose edge documents
   (`var/edge_drafts/<id>.toml`, status `candidate`, `frozen_from` 2026-04-01, the nine answers
   left TODO); the owner promotes one by hand into `config/site/edges/`. A draft declares a 63 or
   252 session outcome, not 504, so it is evaluable by the harness.
4. **The proposer lives in the backtest app.** Decided by the orchestrator on the architect's
   advice, overturnable by the owner: the study, its probit proposer (`quant/probit.py`, rows
   `proposed_by=model`, no verdict) and its drafts run in `apps/backtest`
   (`algotrade-backtest study-winners`, job kind `winners-study`), not in ingestion. Ingestion must
   not write results (ADR 0005); this narrows the 2026-10-08 amendment that put learned scorers in
   ingestion, which stays for scorers that write stored features. LightGBM only if the probit
   proposes nothing.
5. **Lookahead in history.** The edge documents' universe filter `instrument.status = ACTIVE` is
   today's status: used over past sessions it removes the delisted and is lookahead. The study's
   eligible set is `universe_asof(S)` (survivors and the delisted alike) with a bar at S. Company
   snapshots start in 2026, so sector is never a control; Russell reconstitution stays blocked (no
   historical membership).
6. **2026-10-09 (W4): controls are matched on a pre-S hv60 quintile as well; a tell must also
   separate winners from losers (g_WL, sign-stable, above the threshold); the null shuffles
   winner, control and loser within (session, cell); clusters at rank correlation 0.5.** The first
   real run passed on volatility and range tells that mark the names which moved most, winners
   and losers alike.

## Amendment 2026-10-09: historical eligibility before the first snapshot

For a decision session before the first reference snapshot (2026-10-02) the harness read today's
names: `data.reference` falls back to the earliest snapshot, so a delisted name has no row, the
rest carry today's `status`, and every edge was measured on survivors. **Owner decision
2026-10-09, "today's flag + proxy"**: such a session reads the names of the listing history alive
on it (`data.listings.universe_asof`: survivors and the delisted alike, `status` ACTIVE). A name
alive in today's snapshot keeps today's `optionable` flag and `security_type`; a name absent from
it (delisted) counts as a common stock (Tiingo `Stock`; an ETF stays an ETF) and its `optionable`
is replaced by the liquidity proxy: the universe's own close and `adv_usd_20d` floors (for
`liquid_common_stocks`, above $5 and $50M; the vrp edge's `liquid_optionable_floored` carries the
same values, the orchestrator's choice the owner can change), so a universe that reads `optionable` without both is
a `ConfigurationError`, never a number of our own. After 2026-10-02, the real snapshot. This
applies to the frozen period before 2026-10-02 as well, and to the training frame, which calls the
same `eligible`.

**Disclosed tilt.** Today's flag is lookahead: it favours names that later grew into optionable
ones, so every number over these sessions is read with it. The run says so: its record
(`stats["historical_identity"]`) and its report (`HISTORICAL IDENTITY`) carry the rule, the number
of such sessions and the names by path (today's flag, liquidity proxy), eligible and screened.
These sessions no longer count as `pre_snapshot` (a store with no listing history or S&P 500 membership raises `MissingDataError`: never today's
names unsaid). The read is opt-in (`historical=True`
through `fields_view` / `select` / `screen_session`): reads, backtests and the API are unchanged.
`end_date` stays behind `universe_asof` (a name is in only while `start <= S <= end`).

## Amendment 2026-10-09: user edges extend, never shadow; per-user state; publish by download (ED8)

Decided on the owner's behalf by the architect, 2026-10-09 (owner away; decisions D1 to D5 of
the ED8 plan, accepted as recommended). It finishes the Edges Lab and Desk (prototype screens 1
to 14) on the existing documents, with one new grain still to come.

1. **A user's edge extends; it never shadows (D1).** The same-id merge of a user document over a
   site edge (ADR 0015 layering of the first decision) is removed: nothing could show "my copy"
   beside the site edge, nor several copies. A user document
   `config/users/<u>/edges/<id>.toml` is now one of three things. With `extends = "<edge id>"` it
   is a COPY under its own id: the extended document (a site edge, or the user's own, so v2
   extends v1) is deep-merged under it (tables deeply, lists replaced; the screener-copy pattern
   of `services/authoring/presets.py`). Without it, and with an id that is no site edge's, it is a
   new edge. The file of a site edge's own id holds nothing but `[follow]`. What the site decides
   (`status`, `rejection_reason`, `evidence`, `implementation`) is never inherited nor set: a
   copy is a `candidate`. `frozen_from` is a copy's own to set; the run is exploratory when it
   differs from the `frozen_from` of the site edge the chain started from
   (`Edge.site_frozen_from`), or when the user moved the split after seeing the result (below).
   No user edge file shadows a site id today (verified), so nothing migrates.
2. **The user-wide split is deleted (D2).** `config/users/<id>/evaluation.toml`, `PUT
   /evaluation/split`, `Query.evaluationSplit`, `EvaluationSettings` and the web form go: the
   split is per edge, the copy's own `frozen_from` (the builder's step 6, PR-C). The first
   decision's "the split is the site's, a user's is exploratory" stands, now per copy.
3. **State is the user's, in their own document (`[follow]`).** `state` (researching, following,
   rejected, retired, trial), `since`, `reason`, `replaces` (a new version's trial: the edge it
   would replace), permanent `labels` and `oos_revealed`. The table is never inherited and never
   published. Following a site edge without copying it is a `[follow]`-only file. One file per
   (user, edge), no table: state is a user choice (ADR 0029), low volume, and `config/users/`
   being git-ignored (the Mac only) is accepted, as for screens. The server decides the
   transitions (`researching -> following | rejected | trial`, `following -> retired |
   researching`, `trial -> following | rejected | researching`, anything closed `-> researching`)
   and the labels, which are warnings, never blocks: `followed_against_verdict` (following while
   the verdict is Not working), `oos_viewed_during_tuning` (the out-of-sample result shown while
   not following), `replaced_without_forward_test` (a trial replaced its edge before
   `forward_sessions` (site setting, default 20) sessions), `split_moved_after_viewing` (the
   copy's `frozen_from` moved after the result was shown; the run is then exploratory for good).
4. **The fair test is withheld server side.** A copy's out-of-sample result stays hidden until the
   user shows it (Follow does it too; `oos_revealed`). Until then the one run reader
   (`services/read/evaluation/runs.py::load_run_rows`) serves its in-sample rows only (the whole
   history, the years and the regimes all contain out-of-sample sessions), its verdict is judged
   on in-sample figures with the reason saying so (so it is at best Not enough data or Not
   working, never Promising or Works), and the comparison with the edge it extends and its
   baselines (`Edge.compare`) carries in-sample figures and `oosHidden`. The browser filters
   nothing. The Admin harness-run reads, admin only, still show every run.
5. **Publishing site-wide is a read (D3).** The site's config changes only by PR (ADRs 0005 and
   0015): there is no API write to it. An admin reads the edge's whole layered document as TOML
   (`Query.publishedEdgeDocument`, admin only; `extends` resolved, `[follow]` left out) and lands
   it as `config/site/edges/<id>.toml` by pull request. Not a REST GET: the REST allow-list only
   shrinks (ADR 0037).
6. **Writes.** Only through `services/authoring/edges.py` into `config/users/<id>/edges/` (ADR
   0029): copy (optionally as a trial version), save (validated as the harness reads it, fail
   closed, nothing written on an error; a site edge's id is refused), delete (archived, an id not
   reused), state (`PUT /edges/{id}/state`). The writer gains one generic
   `save_user_document` / `archive_user_document` for the kinds in `USER_DOCUMENT_KINDS`; its
   TOML serialiser moves to `storage/configs/toml_text.py` so the read model can render the
   published document.
7. **Paper trades and nightly signals (ED8 PR-D, landed).** One new job-written grain
   `results/edge_paper` (ADR 0005's list has it; D4: Ideas shows ahead or behind only after
   settlement). A paper trade is stored when it is made, never derived at read time: the read
   model may not reach the harness or the outcomes, and re-deriving history from today's
   documents would rewrite the record when the user edits an edge. The nightly `edge-signals`
   step (after `screens` and `outcomes`, not critical) runs one `edge-signals` job per user with
   a followed, tried or retired edge (`services/evaluation/forward/`): for each edge in state
   `following` or `trial` whose schedule fires that night (the harness's decision sessions from
   the state's `since`), the harness's own picks at the session (`cross_section/picks`, only what
   was known then) become open trades with buy and sell sessions from the trading calendar; every
   open trade whose sell session has come is closed from the stored outcome read as of now,
   judged by the edge's own `[outcome]` (`cross_section/hit`) as won or lost, or skipped with
   the reason (no entry bar, a value that cannot be computed, no outcome five sessions after the
   window closed, the edge's outcome changed since the signal): a missing result is never a loss.
   Rows are partitioned by signal session and merge per (user, edge, signal session, name), so a
   settlement rewrites its own row and `as_of` still gives the book as an earlier night saw it;
   one atomic run and one run record `edge-paper:<user>` per user per night; a re-run writes the
   same rows. Event schedules (`on_event:`) and implied-vol outcomes (`expires_otm`, the vol
   ratio) are paper traded (ED8 PR-E): the legs are the harness's own (`sessions.leg_blocks`: the
   event names read at D with the dedupe looking back `EVENT_LOOKBACK` sessions, S = D + 1) and a
   trade settles with `hit.apply_outcome` over the implied vol read at D (`harness.implied_at`),
   a missing or invalid vol skipped with its reason, never a loss; what is still unsupported (no
   screener, a mixed-source vol field) is skipped with its reason in the run record, never an
   empty record. The read model
   (`services/read/edge_desk/`, `Query.edgeDesk`, `Query.edgePaper`: `Edge` has no session) serves
   the Ideas signals and an edge's live record against the backtest's usual range, the 10th to
   90th percentile of the wins `n` closed trades would show if the official win rate held
   (`quant.edge_statistics.win_rate_band`, thresholds `live_min_sessions`, `live_low`, `live_high` in
   `config/site/verdict.toml`), and a trial's forward test beside the edge it would replace.
   The web follow and builder UI is still to come; it lands with its own tests. (Which edges
   record, and for whom, is superseded by item 6 of the 2026-10-10 amendment.)

## Amendment (2026-10-09, ADR 0061): the grain is `forward_returns@v2`
A window that needs a bar `bar-quality` flagged is `outcome_status = UNMEASURED` with
`outcome_reason = BAD_BAR` and null returns (the three return columns are nullable); the harness
counts it per pick (`excluded_unmeasured`, `unmeasured_base`: "unmeasured, not a miss"), and a
session is `excluded_coverage` only when more than half its picks are UNMEASURED. The table name carries the new version,
every reader follows it (`data/outcomes`, `services/evaluation`, the winners labels), and the v1
table is no longer read.

## Amendment 2026-10-10: one status per edge; follow is a bookmark (owner decision)

Owner decision 2026-10-10. It replaces decision 3 of the 2026-10-09 amendment (the `[follow]`
state with its transitions, and `trial`): two vocabularies (the site's status, the user's state)
for one thing is removed.

1. **One status per edge.** `researching`, `candidate`, `evidenced`, `live`, `retired`,
   `rejected`, `blocked` (`document.STATUSES`; lifecycle researching, candidate, evidenced, live,
   retired; `rejected` and `blocked` sit off it). A site edge's is the site's (a PR to
   `config/site/edges/`); the user sets the status of their OWN edge, from `USER_STATUSES`
   (a clone starts `researching`, a new version `candidate`). Transitions (the server decides):
   researching to candidate or rejected; candidate to live, rejected or researching; live to
   retired, candidate or researching; rejected or retired to researching. A candidate that goes
   live retires the edge it `replaces`. `trial` is gone: a trial is a candidate.
2. **The owner comes from where the document lives** (`config/site/edges/` is `site`,
   `config/users/<id>/edges/` that user), never a key (`Edge.owner`).
3. **Following is a bookmark of a site edge**: the file under the site edge's id holds only
   `[follow]` with `since` and `labels` (`followed_against_verdict`); it never changes the site's
   status. A rejected or retired site edge is not a personal state any more. The server's
   bookkeeping of an own edge (`status_since`, `status_reason`, `replaces`, `labels`,
   `oos_revealed`) is a server-written `[audit]` table, never the browser's.
4. **Surfaces.** `Edge` serves `status`, `followed`, `followedSince`, `statusSince`,
   `statusReason`; `state`, `since` and `stateReason` stay as deprecated derived fields until
   the web speaks status (PR 4). `PUT /edges/{id}/state` takes `{follow?, status?, reason,
   reveal_oos}`: `follow` for a site edge, `status` for an own one, never both.
5. **Migration.** `follow.LEGACY` reads the old `[follow]` states tolerantly (following to live,
   trial to candidate; on a site edge following and trial keep a bookmark, rejected and retired
   are archived), and `scripts/migrate_edge_follows.py (--user U | --all) [--dry-run]` rewrites
   the files, idempotently and atomically. Both go once every file is migrated (PR 5).
6. **Paper trades follow the edge's owner (replaces the follow-based rule of the 2026-10-09
   amendment, item 7; owner decision 2026-10-10).** An edge records while its status is
   `evidenced` or `live` (`config.edges.loading.RECORDING`); a user cannot set `evidenced`, so
   their own edge records from `live`. The record's owner is `site` for a site edge, else the
   user whose edge it is: `results/edge_paper` and its key are unchanged, `user_id` now means the
   record owner (no migration), and the nightly runs one `edge-signals` job per record owner
   (`site` first), under that owner's context, so a follower's own presets and universes never
   change the shared record. Following is a bookmark and creates no paper trade; every follower
   of a site edge reads the one `site` record ("tonight", "missed", the trades), and a user's own
   edge record is read only by that user (`data.paper.read_paper(reader, owners)` maps each edge
   to its record owner). A record starts on the first night its job sees the edge recording
   (never backfilled to the status's date); `missed` fills only gaps between nights of edges the
   previous night recorded; a `retired` or `rejected` edge takes no new picks and its open
   trades still settle. A follower's rows written while followers traded are never rewritten
   into `site`: the follower's job only settles them until none is open, and readers leave them
   out of the shared record.
7. **Run identity.** `run_hash` hashes `asdict(edge)`, which now includes the owner, status,
   bookmark and audit: every edge's run hash changes once, and moving a status or following
   changes the hash of that user's next run of the edge (it seeds the random-pick draws, so
   they differ between runs of an unchanged definition; no figure of the verdict depends on a
   particular draw). The trial log is NOT affected: a trial's identity is `_trial_hash`
   (screener config hash, edge variant, outcome, universe), which does not read the document's
   status or follow fields. Excluding bookkeeping from `run_hash` is a follow-up if the draw
   stability matters.

## Amendment 2026-10-17: calendar windows as schedules (edge build H5a)

The schedule kinds are now `every_session`, `month_end`, `calendar:<window>` and
`on_event:<class>`. A calendar window is a stretch of sessions the exchange calendar fixes ahead
of time, a closed set in `core/time/windows.py` (owner `session-calendar`):

| window | placement (from `core/time/calendar.py` alone) | length |
|---|---|---|
| `turn_of_month` | the month's last session and the three after it | 4 |
| `opex_week` | the sessions ending on the monthly option expiry | 5 |
| `quarter_end` | the last sessions of March, June, September, December | 5 |
| `pre_holiday` | the session before a scheduled full-day holiday | 1 |

1. **S and D.** A window's entry session S is the session before its first session; D = S - 1
   as for every schedule, so `start_offset_sessions` must be 1 (a document that says otherwise is
   refused).
2. **One horizon.** A window has a fixed length, so the outcome's `horizon_sessions` is exactly
   `[length]`, validated by the document parser (variants too). No outcome-grain change: the
   existing `forward_returns` partition at S serves it.
3. **No overlap, no peeking.** Windows of one kind never overlap by construction. A window rule
   may use only the calendar, which is known ahead; an unscheduled closure (a day of mourning,
   a storm) is not a holiday window, and a window tied to an event date is `on_event:<class>`,
   never a calendar window. A window cut by the end of the evaluated range is not a window.
4. **Guide.** Each window has its own glossary term `calendar_<window>`, kept complete by a
   fitness test (`edge.schedule` is a plain String, so `guide_coverage.toml` cannot map it).
5. The time-series base for one instrument timed by a window (`base = "out_of_window"`) is not
   part of this amendment; it is a new comparison and gets its own ADR (H5b).

## Amendment 2026-10-18: the decoy battery (edge build H6)

Quality bar 9 asks every edge to beat the cheap explanations of its picks. The battery makes
them standard, measured on the same sessions, and reports how much each overlaps the edge.

1. **`baselines = ["@standard"]`.** The one token a document's `baselines` may hold besides
   screener ids. Where the edge loads (`config/edges/loading.py`) it is replaced, in place, by
   `config/site/verdict.toml [decoys] standard`, dropping a decoy already listed and the edge's
   own screeners (a screener is never its own baseline). `Edge.baselines` is the expanded list,
   so the run hash, the evaluation and every reader see plain ids; a changed standard list is a
   new run (baselines are in `RUN_INPUTS`), never a changed trial (a baseline is not a trial).
   Existing edges keep their own lists: no trial hash and no run hash of an edge that does not
   write the token changes.
2. **The standard decoys.** `size_small`, `momentum_12_1` and four new rank presets, one
   anomaly each: `ivol_high` (idiosyncratic volatility, Ang et al. 2006), `max_ret_high`
   (MAX, Bali et al. 2011), `amihud_illiquid` (Amihud 2002), `beta_low` (Black, Jensen and
   Scholes 1972; Frazzini and Pedersen 2014). `composite_mispricing` joins once filed. A fitness
   test (`tests/unit/config/edges/test_decoys.py`) requires every decoy in the list to be a site
   preset with a Guide playbook.
3. **Their features.** `factor_betas@v1` (relative/): OLS loadings of the daily log returns on
   free ETF factors over the 252 sessions ending at D: SPY market, IWM-SPY size, MTUM-SPY momentum
   and VLUE-SPY value for every name (`beta_mkt`, `beta_size`, `beta_mom`, `beta_value`, and
   `ivol_252d`, the residual volatility of that four-factor fit, annualised). `beta_sector` (the
   sector SPDR-SPY) comes from a five-factor fit and only where the session has a sector ETF for
   the name; `relative_strength@v1`'s `sector_etf` is null before the first company snapshot
   (2026-10-02), so over history it is null with `factor_status` `NO_SECTOR` while the other
   columns stay set (a sector gate on the decoys would have emptied `ivol_high` and `beta_low`
   across history). A window the four ETFs do not cover (MTUM and VLUE start in 2013) or fewer
   than 200 joint sessions is UNKNOWN throughout (`NO_FACTOR_HISTORY`, `SHORT_HISTORY`), never a
   market-only fit. `relative_strength@v1` is a required input, so a missing table is not read as
   "no sector". `illiquidity@v1` (activity/): `amihud_63d`; MAX is `max_return@v1`'s `max_ret_21d` (landed on main as its own group). The
   residual-returns grain (H11) will read the same betas.
4. **The report.** Per screener of an edge variant and horizon and per baseline: the mean over
   the sessions both held picks of the Jaccard index of the pick sets at D, and the edge's decile
   spread less the decoy's (whole history; out of sample when the run has a split). It is in the
   `edge-eval` job result and its text report (`reporting/decoys.py`), computed from the results
   the harness holds; no stored table gains a column for it.
5. **Sector-stratified random picks.** A second random baseline beside the uniform one of ADR 0053
   ED8: at each out-of-sample session the screener's counted picks are counted per sector
   (`instrument.sector` at D, `UNKNOWN` for a name with none) and each count is drawn uniformly,
   without replacement, from that sector's pickable counted names (all of them when fewer).
   An edge that is only a sector tilt does not beat these. It has its own generator, the session's
   labelled `sector`, so the uniform draws are unchanged; both are a function of the leg key,
   the edge variant, the horizon and the session only (ADR 0063). It is stored as
   `strat_picks`, `strat_value_sums` and `strat_hit_sums` beside `rand_*` in `results/edge_legs`
   (leg v3) and as `random_sector:<screener>` draw rows (role `random`) in `results/edge_eval`;
   the verdict still reads the uniform `random:<screener>` rows only, so what users see does not
   change. Showing the stratified percentile beside it is a follow-up. The decoy criteria of the
   verdict count a baseline with no lift or spread as not measured ("n of m measured"), never
   leave it out; the decoy report flags a decoy with no common session as not measured.
6. **`LEG_VERSION` 3.** Every screener's out-of-sample leg now holds the stratified draws, so
   no stored leg is the one a run would compute: all legs recompute once. H7 (buy/hold bands)
   bumps it again (to 4); run the one full re-run after both merge, not after each.

## Amendment 2026-10-18: the event-class list and subtypes are a contract (edge build H4)

`on_event:<class>[:<subtype>]` names what triggers an event schedule. The classes and their
subtypes are a closed list in `config/edges/document.py` (`EVENT_CLASSES`, `EVENT_SUBTYPES`,
`SUBTYPE_REQUIRED`) and the harness reads each from a declared field of a feature group
(`cross_section/events.py`, `EVENT_FIELDS`); fitness tests keep the three equal, require every
field to be a catalogue feature, and require a Guide term per class and subtype
(`event_class_<class>[_<subtype>]`). A new class follows one recipe: a stored event table with
`known_from` (ADR 0050), a feature group read at D with a sessions-since (or sessions-to when
announced ahead) count and a date, the two entries, and the Guide terms.

| class | subtypes | read from | anchor (the session of `known_from`) |
|---|---|---|---|
| `earnings_reaction` | none | `earnings_reaction@v1` | the reaction's last session |
| `earnings_expected` (announced ahead) | none | `earnings_expected@v1` | the expected date's session |
| `index_change` | `addition`, `deletion` | `index_changes@v1` | the first session the change is stored (never the announcement) |
| `filing_8k` | an item: `1.02`, `2.05`, `3.01`, `4.01`, `4.02`, `5.02` (required) | `filing_events@v1` | the session whose close first follows the acceptance |
| `nt_late_filing` | none | `filing_events@v1` | same (NT 10-K, NT 10-Q) |
| `tender_offer` | none | `filing_events@v1` | same (SC TO-I, SC TO-T) |
| `earnings_date_shift` | `later`, `earlier` | `earnings_date_shift@v1` | the session the shifted date was first stored |

1. **Subtypes fail closed.** An unknown subtype, a subtype of a class that has none, and a
   `SUBTYPE_REQUIRED` class without one are refused by the document parser and by
   `event_field`. A subtype is its own count and date fields (an 8-K item) or a label field that
   must read a value (`index_changes@v1.last_index_change`, `earnings_shift_direction`).
2. **Base.** `base = "event"` is the names with the event at D of the schedule's own class AND
   subtype (4.02 filers are compared with other 4.02 filers); `base = "universe"` is everyone.
   A name whose label reads another subtype is no event of this one and is not UNKNOWN; one with
   no label is UNKNOWN (`no_event_row`). The leg key carries the subtype only when set, so no
   existing leg is invalidated.
3. **Known-from rules.** Filings: ADR 0050 amendment 2026-10-18. `earnings_date_shift`: the
   shift is the next stored report date less the year-ago report plus 364 days, an event when it
   is at least 7 days; known from the session the date was FIRST stored in a calendar known by
   S, and a date first stored at or before the first calendar snapshot is never an event
   (vendor backfills carry no time), so the history starts at our first stored snapshot.
   `index_change` keeps ADR 0050's first-stored session, later than the announcement (a lag by
   design: nothing is lookahead, the rebound window starts after the effective date).
4. **Not in the list yet** (no field to read, each a follow-up): `ex_dividend` (needs a sessions
   count: `dividend_schedule@v1` counts calendar days), `macro_release` (a market-entity field
   the harness does not read), `lockup_expiry` (the IPO table of D8 is not merged), `insider_buy`
   (Form 4, H12), `spin_off` (needs data).

## Amendment 2026-10-17: outcome sides (owner decision 2026-10-17, `docs/decisions/log.md`)

An outcome has a **side**, `[outcome] side = "long" | "short" | "long_short"` (default `long`; a
`[[variants]]` row may override it, each a trial as before). Edges that never name one are
byte-identical to before: the side keys are left out of the trial hash, the run hash and the leg
key when the side is `long` (`identity_dict`), so no stored leg or run is recomputed.

1. **`short`**: the picks are the bottom `top_k` of the scored, pickable names of the screen's
   ranking (by score, as the deciles, never the rule rank), among names whose 20-day dollar
   volume at D is known and at least `capacity_adv_floor_usd` (`verdict.toml`: the existing
   liquidity threshold; an unknown volume is not liquid, and no short leg is drawn from a
   microcap). The value of a pick is `-excess_return - cost_bps - borrow`; a hit is a value above
   zero. The base rate is the share of every eligible name that would have hit the same way, so
   the lift still compares the picks with doing it blindly. The decile spread (`top - bottom`,
   long oriented) is the ranking's and does not change with the side. A short edge needs an
   `excess_return` outcome, no `max_drawdown` (the dip of a short is the rally) and an integer
   `top_k`. Unscored names are in neither leg, a session with too few scores has no legs (the
   `MIN_SCORE_COVERAGE` rule, fail closed), and a delisted name is measured to its last bar.
2. **`long_short`**: the session value is the mean of the top `top_k` plus the mean of the short
   leg (each net of its costs, the short leg of borrow), `SessionStat.spread_value`; a session
   with no counted name in either leg has no value, never half a spread. It has no base rate: the
   hit rate, base rate, lift, effect size and equal-weight floor are null (the Guide term
   `side_long_short` says why, they are never 0), and it has no cost rows. The trial statistics
   (Sharpe, deflated Sharpe, PBO) read the spread.
3. **Borrow** is an assumption: `[edge_costs] borrow_bps_annual` (default 100 bp a year) in
   `config/site/verdict.toml`, or the outcome's own `borrow_bps_annual`, scaled by
   `horizon / 252`. No borrow data exists; the Guide says so. Limitation: a hard-to-borrow name
   costs more than the flat rate and is not excluded (nothing stored says which names are); the
   dollar-volume floor stands in for it, and a short result is read with that in mind. The resolved rate is in the trial
   hash and the liquidity floor in the leg key of a non-long edge only.
4. **Random picks** follow the side with the same seeded generator: `short` draws from the liquid
   pickable names and its value is the short's; `long_short` is two draws, the long's then the
   short's, summed (`random_picks.long_short_stat`).
5. **Storage**: `results/edge_legs.short_values` (null for every other side; the picks'
   `SHORT` flag bit says which leg a pick is on; no `LEG_VERSION` bump: an absent field reads
   back as null), `results/edge_trades.side` and `results/edge_eval.side` (null in rows from
   before: read as `long`). The ledger lists both legs of a `long_short` run, ordered by side.
6. **Read**: a `long_short` result is a diagnostic and never a verdict basis (owner decision
   2026-10-17): its verdict is its own state, Diagnostic only (`diagnostic_only`, Guide term `verdict_diagnostic_only`), with `EdgeVerdict.side`; a `short`
   result is judged like any, its headline says "(short leg)". The edge page shows the side
   beside the basis, with a Guide entry per value (`side_long`, `side_short`, `side_long_short`).

## Amendment 2026-10-17: `option_model_pnl`, a modelled option P&L (EB H8)

A fourth outcome kind, harness-side like `expires_otm`: it adds no grain, no table and no
column, and reads the stored `forward_returns@v2` window and the implied vol at D.

1. **Document.** `[outcome] kind = "option_model_pnl"` names `structure` (`atm_straddle_long` |
   `atm_straddle_short` | `delta_hedged_atm` | `delta_hedged_atm_short`, `MODEL_STRUCTURES`), the `iv_field` it reads at D
   (required, as for `expires_otm`) and `benchmark = "none"` (a P&L on the underlying has no
   benchmark); no strike key is allowed (at the money). `cost_bps` is optional. A variant may
   switch to or from the kind like any other kind change. **One tenor prices every horizon**:
   the IV field is a 30-day figure (`iv30`, 21 sessions) read once at D, so the parser refuses
   a horizon outside half to double the field's tenor (10..42 sessions for `iv30`; the tenor is
   read from an `iv<days>` in the field name, and a name without one is refused). A
   pre-earnings window of a few sessions is therefore not expressible; it needs a short-tenor
   IV field first.
2. **Value** (`cross_section/hit.py`, `T = horizon_sessions / 252`, r = q = 0, per straddle as a
   fraction of the entry close `P` that `fwd_return` is measured from):
   - long straddle: `|fwd_return| - straddle_price(iv, T)`; short: its negative;
   - delta-hedged straddle (long; `delta_hedged_atm_short` is its exact negative):
     `straddle_vega(iv, T) * (fwd_realised_vol^2 - iv^2) / (2 iv)`,
     the standard gamma-P&L approximation. The vega-unit P&L per unit of vega is
     `(rv^2 - iv^2) / (2 iv)` (no `T`: the gamma P&L already carries it); multiplied by the
     straddle's vega (`2 sqrt(T) n(iv sqrt(T) / 2)`) it is in the same unit as the unhedged
     value. The design note's `... * T / (2 iv)` is the same quantity before that
     multiplication and was not carried as a literal.
   The closed forms (`atm_straddle_price`, `atm_straddle_vega`, `delta_hedged_vega_pnl`) are in
   `quant/black_scholes.py`, tested against the call-plus-put price, a finite-difference vega
   and a seeded delta-hedged simulation (a martingale underlying: the hedged long straddle earns
   in expectation `price(rv) - price(iv)`, which the vega form overshoots by about 7% at
   rv 34% against iv 30% and matches within 2% at 31%). `fwd_realised_vol` is a demeaned standard deviation of daily
   returns (ddof = 1): the drift of a trending window is taken out of it, so the realised
   variance, and with it the gamma P&L, is slightly understated against what a hedger who pays
   the path's full movement would see.
3. **Costs.** `cost_bps` is charged once, in bps of `P`, after the sign (the excess return's
   convention; a short position pays it too). No hedging cost, spread, fill or margin is
   modelled. The cost grid (`CostGrid`, a sensitivity over a stored gross return) does not
   apply: `is_return` is false, so `cost_applies` is false, as for `expires_otm`. Unlike a
   cushion, the value is a P&L: `counts_wins` is false for the `pnl` unit and for an
   `option_model_pnl` edge's settings, so the trial statistics (Sharpe, deflated Sharpe, PBO,
   haircut) read the picks' mean P&L per session and never the win rate. A short straddle that
   wins 80% of its windows and loses on average cannot read as evidence.
4. **Missing inputs.** A row with no usable IV (`no_implied_vol`, `invalid_implied_vol`), no
   stored `fwd_return` / `fwd_realised_vol` or no horizon is excluded with its reason
   (`missing_value`), an `UNMEASURED` window as `unmeasured`; never a zero and never a miss.
5. **Unit, basis and licence.** The series unit is `pnl`, a return-like unit (`RETURN_UNITS`):
   the evidence curve adds up the picks' mean P&L against the field's. The outcome is labelled `basis = "model"` (`Outcome.basis`, `MODEL_BASIS`): its text
   on the edge and builder pages says "model, not a quote", and the Guide terms
   `outcome_option_model_pnl`, the four structures and `model_basis` explain it. The licence
   is inherited from the `iv_field` through the existing `needs_implied_vol` path (IBKR-derived
   IV: `personal`). No stored column carries the basis; a second basis (a chain P&L, the
   `outcomes/option/structure_pnl@v1` grain of the design note) will need one and its own
   amendment.
6. **Not here.** The chain P&L grain (H13) and a short-put P&L (needs a strike key and a put
   price) are a follow-up PR. The short delta-hedged side is its own structure value
   (`delta_hedged_atm_short`), not a `side` key. The stored basis column is left to H13.

## Amendment 2026-10-18: residual returns, a factor-neutral outcome (edge build H11)

A momentum or small-cap edge can look like alpha when it only holds a cheap, small or
high-momentum basket. The harness gets a second outcome grain whose value is the return left
after the loadings the name had before the entry session, so the same statistics can be read
factor-neutral.

1. **A sibling grain, v2 untouched.** `outcomes/instrument/residual_returns@v1`, partition S,
   runs merge per (instrument, horizon): `fwd_residual_return`, `fwd_factor_return` (the part
   removed), `beta_session`, `outcome_status` (COMPLETE, DELISTED, UNMEASURED), `outcome_reason`.
   `forward_returns@v2` is unchanged, so no stored leg is invalidated and a document that never
   names the measure hashes as before (`measure` is already in the outcome's identity as None).
   Written only by ingestion (`tasks/derived/residual_returns.py`, a registered task; the arithmetic
   is `residual_paths.py`), read only through `algotrade.data.outcomes` (`residuals.py`: the same
   import contract, importable only from `services/evaluation`).
2. **The maths.** `residual = fwd_return - sum_k beta_k x factor_k return`, the factor returns the
   simple returns over S..end of the proxies of `factor_betas@v1` (market SPY; size IWM - SPY;
   momentum MTUM - SPY; value VLUE - SPY). `end` is T, or a delisted name's last
   bar, as in the forward row. The betas come from log returns and the window sums simple
   returns: a first-order match, stated rather than hidden. The sector loading is
   left out (review decision): `factor_betas@v1` stores the four betas of one four-factor fit and
   `beta_sector` from a different five-factor fit, so adding it counts sector exposure twice.
   Sector would need a `factor_betas@v2` storing all five betas of the five-factor fit.
3. **Point in time.** The betas are the `factor_betas@v1` rows of the session before S
   (`previous_session(S)`), estimated on the 252 sessions ending there, read through
   `data.rollups`. Nothing of the
   window enters them; for the usual offset of 1 they are exactly the betas known at the
   decision session D. A later partition is never read (the exact session, not "on or before").
4. **Gaps are UNMEASURED with a reason, never market-only, never zero.** `NO_FACTOR_HISTORY` (a
   factor ETF has no bar at S: MTUM and VLUE start in 2013, so every earlier window; or the betas
   row says so), `NO_BETAS` (no partition or no row before S, or a non-finite beta),
   `SHORT_HISTORY` (the betas say too few joint returns), `NO_FACTOR_BAR` (a factor ETF
   has no bar at the end), `BAD_BAR` (carried from the forward row). The harness treats such a
   row like an `UNMEASURED` forward row: excluded as `unmeasured`, counted, and a session most of
   whose picks are unmeasured is not measured. A forward row with no residual row at all
   (`NO_RESIDUAL_ROW`: the task has not run for its window) is the same.
5. **The document.** An `excess_return` outcome may set `measure = "residual_return"`
   (`EXCESS_MEASURES`); any other measure on an `excess_return`, and this one on a `hit_target`,
   is refused. Everything else is the excess return's: the cost is charged once, a short side
   is minus the residual less cost and borrow, the trial statistics are over a return. The
   benchmark key stays (SPY) and is unused by the value. In `hit.py` the field is
   `fwd_residual_return` where the excess return's is `fwd_excess_return`; `measuring.py` reads
   the residual rows once beside the forward ones and attaches them (`attach_residuals`) for the
   horizons whose edges measure it. A read that did not attach them (the training frame, the
   paper settlement) fails loudly for a residual edge instead of reading the excess return.
6. **The verdict says so.** `EdgeFacts.neutral`: the headline names the figure "factor-neutral:
   market, size, momentum and value taken off". The Guide term `outcome_residual_return`
   explains it; `tests/architecture/guide/test_outcome_measures.py` fails until every
   `EXCESS_MEASURES` value has its term.
7. **Leg reuse and settlement.** The leg-reuse stamps (ADR 0063) cover the residual partitions
   when any plan measures a residual return: each partition's sequence is the forward one times
   `SEQ_SCALE` plus the residual one, and a (S, horizon) stamp is the later of the two
   `knowledge_ts`, so a backfill of the residual grain re-measures exactly the legs stored with
   `NO_RESIDUAL_ROW` (an edge that does not measure it is unaffected). The paper settlement
   (`forward/settle.py`) attaches the residual rows for a residual edge: a trade whose residual
   row is not stored stays open until the grace window ends, then is skipped with the reason; it
   never reads the excess return and never stops the other edges' settlement. The training frame
   still refuses a residual edge loudly (no attach there).
8. **The nightly step.** `residual-returns` (needs `outcomes` and `rollups`, optional) runs the
   task each night and is accepted by `check_residual_returns`: every forward outcome of the
   session's windows has a residual row (FAIL otherwise), UNMEASURED rows are a WARN naming
   their reasons (the ETFs themselves have no betas row, so a WARN is the normal state).
9. **Not here.** Sector: a `factor_betas@v2` storing all five betas of the five-factor fit would
   be needed to add it (point 2). Delisted names are residualised over their own window, so
   their delisting return is not in it (as in the forward row).

## Amendment 2026-10-18: buy/hold bands for turnover-aware cost (edge build H7)

`[outcome] hold_rank` (optional integer) turns an edge's flat cost into a turnover-aware one: a
name enters at rank <= `top_k` and is held while its rank is <= `hold_rank`.

1. **Document rule.** `hold_rank >= top_k` and `top_k` is an integer (config error otherwise, for
   the edge and for each variant's outcome). Allowed only for a `long` or `short`
   `excess_return`, on `month_end`, or `every_session` at `horizon_sessions = [1]`: a band carries
   a name from one decision session to the next. The schedule limit is stricter than needed (windows
   never overlap on a plain schedule); loosening it is a later PR. Refused for
   `long_short` (a spread: no cost rows, and two legs with no single book to turn over), a
   `hit_target`, an event or a calendar schedule. Unset, nothing changes: `identity_dict` drops
   the key, so the run and trial hashes of every existing edge are as they were. Set, it is part
   of the trial and the run, and of the leg key.
2. **What a leg holds (leg v4, ADR 0063 amendment).** A leg stays one session's own: the counted
   picks (ranks `1..top_k`) and, from a `hold_rank`, the band's names (`top_k + 1..hold_rank`)
   with their oriented net values (`band_ids`, `band_ranks`, `band_values`; a name with no counted
   value has a null value, never 0 and is never held). The `short` band is the next-worst liquid
   names. `LEG_VERSION` 4; an edge without a band stores null columns.
3. **The turnover pass** (`reporting/turnover.py`) runs over a variant's decision sessions in
   order, after the legs are decoded, so legs and picks stay independent (ADR 0063): held at a
   session = the counted picks plus the band names the previous session held. An entry pays half
   a round trip and an exit half; a name held through pays none. A session the screen did not
   measure (coverage) closes every position; the last session's names exit, charged. It sets
   `banded_values` (each held name's value net of its own entries and exits) and `round_trips` on
   the stat, never stored. The decile spread, hit rate, base rate, lift and every gross figure
   are untouched; the net series (`pick_mean`, so Sharpe, deflated Sharpe, PBO), `mean_excess_picks`
   and the cost rows use the banded values. The cost rows scale the mean's slope in the cost by
   the turnover (`round_trips` per held name), so each is exact; the break-even is the gross mean
   over that turnover (`break_even_cost(..., trips)`), read from the slope of the stored cost rows
   (no stored column). Hit counts at the cost levels stay per round-trip trade, and the
   trade ledger and `bh_mean` (the floor) stay as the legs have them: follow-ups.
4. **Side interplay.** `long`: the band follows the qualified order. `short`: the worst-ranked
   liquid names; a short's borrow still accrues for every held period (only the trading cost
   changes). `long_short`: refused (item 1).
5. **One full re-run.** `LEG_VERSION` 3 (H6) and 4 (this) both invalidate every stored leg once:
   the owner pays one full re-run after both merge: `algotrade-backtest evaluate-edges --full` (every
   open edge; `--edge ID` for one), from the main checkout's environment against the real store.
6. **Accepted limits (architect review, non-blocking).** A month end the schedule skips counts a
   name as held through it at no cost. A period with a single cost row has no slope, so the
   break-even falls back to a full round trip per name: conservative. No exit reason is recorded
   per name. `LEG_VERSION` 4 recomputes every leg (item 5).
