# ADR 0053: Edges: hypotheses with evidence, an outcomes grain and one point-in-time harness

**Status:** accepted (2026-10-07; owner decisions 2026-10-06 and 2026-10-07; the plan and items
are [edges-plan.md](../edges-plan.md), the long form is the owner's PRD "Winners-Derived Screener:
Product Requirements"; the open decisions below are the owner's before the item that needs each).
Extends [0005](0005-ingestion-is-the-only-writer.md) (ingestion writes the outcomes),
[0007](0007-point-in-time-data.md) (an outcome is knowable only when its window closes),
[0015](0015-configs-selections-users.md) (the edge document is a layered settings file),
[0021](0021-option-pricing-conventions.md) (the statistics live in `quant/`) and
[0033](0033-screeners-run-nightly-and-on-request.md) (a screener run for a past session). Makes
one confined exception to [0036](0036-session-strictness-for-reads.md).

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
- The frozen period: proposal, the last two quarters of stored sessions when ED4 starts, recorded
  here by amendment.
- The ED4 outcome definitions (proposals in the PRD): the volatility risk premium, realised below
  implied over the option's horizon with a drawdown cap on a short-straddle proxy; post-earnings
  drift, excess return over SPY over 20 and 60 sessions with a cost assumption; the earnings
  announcement premium, excess return over SPY from five sessions before to one after.
- The cap threshold for the drift edge: proposal, below $2B (the harness reports by bucket either
  way).
- The runtime home of learned scorers (ED7): `apps/ingestion` or a fifth app, by amendment.
- If ED2 finds the grain must differ from decision 3, it amends this ADR in the same PR.
