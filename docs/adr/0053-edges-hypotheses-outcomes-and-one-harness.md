# ADR 0053: Edges: hypotheses with evidence, an outcomes grain and one point-in-time harness

**Status:** accepted (2026-10-07; owner decisions 2026-10-06 and 2026-10-07; the plan and items
are [edges-plan.md](../edges-plan.md), the long form is the owner's PRD "Winners-Derived Screener:
Product Requirements"; the open decisions below are the owner's before the item that needs each).
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
- **One table, no stored hit.** `outcomes/instrument/forward_returns@v1` (fixed schema in
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
   `split_from` in `config/users/<id>/evaluation.toml`, or per run (ADR 0015 layering:
   site < user < run). The run records it with its config hash. Every number from a split that
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
   `outcomes/instrument/forward_returns@v1` (through `data/outcomes`, from `services/evaluation`
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

## Amendment 2026-10-09: historical eligibility before the first snapshot

For a decision session before the first reference snapshot (2026-10-02) the harness read today's
names: `data.reference` falls back to the earliest snapshot, so a delisted name has no row, the
rest carry today's `status`, and every edge was measured on survivors. **Owner decision
2026-10-09, "today's flag + proxy"**: such a session reads the names of the listing history alive
on it (`data.listings.universe_asof`: survivors and the delisted alike, `status` ACTIVE). A name
alive in today's snapshot keeps today's `optionable` flag and `security_type`; a name absent from
it (delisted) counts as a common stock (Tiingo `Stock`; an ETF stays an ETF) and its `optionable`
is replaced by the liquidity proxy: the universe's own close and `adv_usd_20d` floors (for
`liquid_common_stocks`, above $5 and $50M), so a universe that reads `optionable` without both is
a `ConfigurationError`, never a number of our own. After 2026-10-02, the real snapshot. This
applies to the frozen period before 2026-10-02 as well, and to the training frame, which calls the
same `eligible`.

**Disclosed tilt.** Today's flag is lookahead: it favours names that later grew into optionable
ones, so every number over these sessions is read with it. The run says so: its record
(`stats["historical_identity"]`) and its report (`HISTORICAL IDENTITY`) carry the rule, the number
of such sessions and the names by path (today's flag, liquidity proxy), eligible and screened.
These sessions no longer count as `pre_snapshot` (that caveat stays for a store with no listing
history, where the earliest snapshot still stands in). The read is opt-in (`historical=True`
through `fields_view` / `select` / `screen_session`): reads, backtests and the API are unchanged.
`end_date` stays behind `universe_asof` (a name is in only while `start <= S <= end`).
