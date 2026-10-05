# ADR 0032: Screener results are the default surface; a review table over the stored run

**Status:** accepted (2026-10-04; owner decision, mockup option B). Extends
[0029](0029-rule-screener.md) and [0030](0030-rule-screener-simplification.md).

## Context
A trader spends most of the time reviewing what a screener found and little building it. The
Builder page is organised around editing (criteria first, a 50-row preview at the bottom), the
preview and Explore render tickers with different column models, and Explore cannot be scoped
to a screener. A v3 run now stores a row for every snapshot instrument (about 11.4k), so a
review surface must filter, sort and page on the server.

## Decision
1. **Results are the default view of a screener** (`/screeners/$id`); editing the criteria is
   a tab or drawer beside it, with the live preview on the same grid.
2. **One review table** over a rule screen's stored run: `GET /screens/{id}/table` returns one
   row per instrument with the decision, score and reasons, every criterion's value and
   PASS / NEAR / FAIL / MISSING, the screen's display columns, any catalogue features the
   caller asks for (`columns=`), and what changed since the previous run (`new` / `dropped`:
   a ticker is picked when its decision is not REJECT, SKIPPED or UNKNOWN, as in Ideas).
   Filter (decision, change, search), sort (rank, score, a criterion, a column or a feature)
   and paging happen in the query, cached per query and published state. Nothing is recomputed.
3. **Columns are layered**: fixed (rank, ticker, decision, score), from the screen (its
   criteria and display columns), the user's own catalogue features, then the reasons.
4. **The user's column choices are a per-user view of the screener, not part of it**: stored in
   the user's `preferences.toml` (as `ideas.priority` is), never in a screener version, so
   changing a column creates no version and does not change the screen's hash.
5. `result_table` maps an impl to `results/<impl>`; rule screens all live in
   `results/rule_screen`, so `run_rows` names that table for `impl = "rules"`.

## Consequences
- The Builder preview and the results page share one grid (a design-system cell tint for
  near misses and failures comes first).
- The view endpoints and the web pages follow in later PRs; this one is the read query.
- `GET /screens/{id}/results` now also answers for rule screens (it read a table they never
  wrote); its rows stay thin, the table is the review surface.
