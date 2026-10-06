# ADR 0039: Ingestion workflows by cadence; steps succeed or fail by an acceptance rule; a failed critical step holds the workflow back

**Status:** accepted (2026-10-05; owner decisions; implementation: roadmap WF1-WF5), amended 2026-10-05 (below) and by [0043](0043-waiting-on-publication-tiered-and-coverage-acceptance.md). Amends the nightly workflow of R5
(`docs/architecture.md`, "The nightly workflow"), [0033](0033-screeners-run-nightly-and-on-request.md)
(when the screens step runs), [0034](0034-instrument-descriptions.md) and
[0035](0035-etf-holdings.md) (descriptions and ETF holdings leave the nightly), and
[0036](0036-session-strictness-for-reads.md) (which session a read defaults to).

## Context
On 2026-10-05 Massive returned HTTP 403 for that session's grouped daily bars. The nightly
behaved as designed, and the design let the gap through:

- The `bars` step was PARTIAL and every later step still ran. Only `screens` names hard
  dependencies (`chains`, `rollups`); nothing depends on `bars`.
- `rollups` reported the session's price rollups as `no_input` (not a failure), so `screens`
  ran on a session without prices.
- `overall` turns any mix of results into PARTIAL, and a PARTIAL nightly counts as done:
  the hourly watchdog and the next night never retry it. The nightly bars step fetches only
  its own session, so the 10-05 bars would never have been fetched.
- From the next session on, lookback rollups (`_Bars.at` takes the last N stored sessions)
  would have computed over the gap without noticing: a 10-02 to 10-06 move treated as one
  day's return.
- `quality` (where `bars_fresh` FAILs) runs last, after the screens are published.

PARTIAL also does not say whether the data is usable. It covers both "3 of 6,000 companies
had no SEC facts" and "no prices today".

The nightly also mixes cadences. Market data must be fetched on the session (chains: 2 to 4 h
for ~4,200 underlyings). Reference data changes slowly (company details, shares, IBKR conids,
ETF holdings, descriptions) and already refreshes each key once per 7 to 365 days
(`tasks/framework/refresh.py`), but it sits in the same chain, adds to its runtime and status,
and screens do not need it that night.

## Decision
1. **Three workflows, each with its own schedule, run record and status.**

   | Workflow | When | Steps |
   |---|---|---|
   | `market-daily` | weekdays after the close (launchd 15:00 PT), hourly watchdog | `universe-build`, `bars`, `rates`, `corporate-actions`, `earnings`, `chains`, `ibkr-iv` (session snapshot only), `rollups`, `screens` |
   | `reference` | weekly (Saturday 08:00 PT), and on demand | `company-details`, `shares`, `ibkr-contracts`, `etf-holdings`, `descriptions` (each keeps its refresh slots, so the SEC and vendor load stays spread over the window) |
   | `enrichment` | after a SUCCEEDED `market-daily`, capped per night | `ibkr-iv` history backfill, `verify` |

   Tickers new to the universe are picked up by the next `reference` run (at most a week).
   Until then their reference facts are UNKNOWN (ADR 0036), as today. `purge-raw` runs at
   the end of every workflow.

2. **Each step declares `needs` (the steps it depends on) and runs only when all of them
   SUCCEEDED.** The workflow is a DAG executed in topological order. A step whose need did not
   succeed is NOT_RUN (with the reason), never run on partial input. `market-daily`:

   ```
   universe-build → chains → ibkr-iv ┐
   bars ┐                            │
   rates ├──────────────── rollups ──┴→ screens
   corporate-actions ┤
   earnings ┘
   ```

3. **A step either SUCCEEDS or FAILS, by its acceptance rule.** Each step has a declared
   acceptance rule, checked right after it runs (the relevant `quality` checks move here; the
   separate end-of-session `quality` step goes). Errors within the rule are warnings, carried
   in the run record and the summary email; outside it the step FAILS. SKIPPED stays only for
   "not applicable" (a latest-only step during catch-up, a source not configured). A workflow
   run is **SUCCEEDED** or **FAILED**; there is no PARTIAL at the workflow level. Task run
   records keep their own statuses and atomic publication (ADR 0022); the acceptance rule is
   what maps a task's record to SUCCEEDED or FAILED. Thresholds live in
   `config/site/nightly.toml`.

4. **Critical and optional steps.** A critical step that fails holds the workflow back: its
   dependents are NOT_RUN and the run is FAILED. An optional step that fails is a warning and
   does not change the run's status. All `market-daily` steps are critical except `ibkr-iv`
   (IV rank falls back to ours, labelled, ADR 0028). Initial rules:

   | Step | Critical | Acceptable |
   |---|---|---|
   | universe-build | yes | size within 5% of the previous snapshot |
   | bars | yes | the session fetched; rows within 10% of the previous session; at most 1% of tickers unresolved |
   | rates, corporate-actions, earnings | yes | the fetch succeeded |
   | chains | yes | at least 98% of underlyings fetched (the screener's coverage bar) |
   | ibkr-iv | no | gateway down is SKIPPED |
   | rollups | yes | every rollup computed for the session; a required input missing is a failure, and so is a gap in a lookback window |
   | screens | yes | each screener reaches its coverage threshold |
   | `reference` steps | no (the workflow alerts on any failure) | per-key "no facts" / 404 |
   | `enrichment` steps | no | gateway down is SKIPPED |

5. **A FAILED run is retried, resuming where it stopped.** The hourly watchdog reruns a FAILED
   `market-daily` session; steps that already SUCCEEDED for it are not rerun. Every retry that
   still fails notifies (macOS) and the summary email names the failing step and rule.

6. **Sessions are processed in order and a failed one holds everything.** No newer session
   runs until the oldest FAILED one SUCCEEDS or is waived, so lookback windows never span a gap.

7. **Snapshot steps that can no longer be fetched are waived by hand.** `chains` and
   `universe-build` serve only the current snapshot. When one fails and the next session
   opens, the session cannot succeed by retrying: it stays FAILED and alerts until the owner
   runs `algotrade-ingest nightly --date D --waive chains --reason "..."`. The waiver (step,
   reason, user, time) is stored in the session's run record and shown in the summary email,
   and the session then counts as SUCCEEDED with a waived step. Nothing is waived
   automatically.

8. **Reads default to the latest SUCCEEDED `market-daily` session**, not the latest session
   with bars, so a page never shows a session whose workflow has not finished. An explicitly
   requested session is still served as in ADR 0036.

## Consequences
- A bad source day stops the screens instead of publishing them on missing data. Results for
  that day appear late (after a retry or a waiver), not wrong.
- One failed session can hold the store back for days if nobody acts. The alert repeats on
  every retry and the email says which step, rule and command (`--waive`) unblock it.
- `market-daily` loses the reference steps (about 15 to 25 min of a normal night, more on
  refresh-heavy nights) and gets one meaning for its status. Chains remain the long pole
  (2 to 4 h); making them faster is a separate item.
- Acceptance thresholds are judgement calls and will need tuning; they are config, and every
  rule that fires says which threshold it crossed.
- Code: `workflows/` gains the DAG runner, `needs`, `critical`, acceptance rules and resume;
  `steps.overall` becomes SUCCEEDED / FAILED; `sessions.plan_sessions` stops at the oldest
  FAILED session; `quality` checks become per-step acceptance; the CLI gains `--waive` and the
  `reference` / `enrichment` commands; `ops/schedule.py` writes three launchd agents; the read
  model's default session changes (`services/read/session.py`). Run records written before
  this ADR keep PARTIAL; the planner reads a PARTIAL nightly as SUCCEEDED.

## Amendments (2026-10-05, while implementing WF1-WF3)
Decisions the owner delegated while away (a Fable review), and details settled in the code:

- **Chains need a universe snapshot, not today's build** (amends the graph in 2): chains can be
  fetched only for the current session, and a failed `universe-build` already fails the
  session (it is critical) and holds the screens back. Blocking chains on it would lose the
  day's chains for no extra safety. Chains still start after the build ends.
- **Stale chains FAIL**: over `max_chain_stale_share` (20%) of chains STALE_DATA fails the
  `chains` step (was a WARN), so the hourly retry refetches them instead of the screens
  failing on UNKNOWN names with chains already marked done. Follow-up: a retry should
  refetch only the STALE_DATA / FETCH_ERROR names, not all ~4,200.
- **Thresholds live in `sources.toml [quality]`** (where the quality checks already read
  them), not `nightly.toml`; new: `max_bar_unresolved` (0.01); `max_chain_fetch_failures` is
  0.02 (the 98% of 4).
- **Catch-up drops no session**: one run takes the oldest `max_catch_up` pending sessions and
  the rest wait for the next run; a dropped session would be a permanent gap.
- **A critical step whose source is not configured FAILS** (an optional one is SKIPPED).
- **The NYSE calendar gains special closures** (2025-01-09 and 2018-12-05, national days of
  mourning): the gap check found 2025-01-09 "missing" from the stored bars.

## Amendment (ADR 0043)
A step whose source has not published the latest session yet is WAITING, not FAILED, until
its deadline (`nightly.toml [schedule]`); a WAITING session is not done, holds later sessions
back like a FAILED one, is resumed by the hourly run and sends no alert. After the deadline it
is FAILED as above.
