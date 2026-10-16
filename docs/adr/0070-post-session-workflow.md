# ADR 0070: The post-session workflow: what does not decide a session leaves the nightly

**Status:** accepted (2026-10-16; design: the architect's plan for this change). Amends
[0039](0039-ingestion-workflows-dependencies-and-acceptance.md) (a workflow after the
market-daily one; WF4 builds on it), [0063](0063-incremental-edge-evaluation.md) amendment 6
(when the audit is due) and [0034](0034-instrument-descriptions.md) (where descriptions run).
[0062](0062-reads-serve-the-last-complete-session.md)'s cutoff is unchanged. Code:
`apps/ingestion/algotrade_ingestion/workflows/post_session/`; fitness test
`tests/architecture/test_post_session_split.py`.

## Context
A session is served only when its `nightly` run record is COMPLETE (ADR 0062:
`services/read/session.py` `completeness`, `session_cutoff`). Three optional steps ran after the
screens and delayed that record by 3 to 20 hours, for data no session read depends on:
`edge-eval` (190 minutes on 2026-10-14; 1,227 minutes, a failed audit, on 2026-10-12),
`descriptions` (~25 minutes) and `verify` (~40 minutes, behind it). Their failures were warnings
already: they never decided anything, they only made the decision late.

## Decision
1. **A new job `post-session`** (`workflows/post_session/`, `algotrade-ingest post-session`) with
   its own run record (`post-session`, one per attempt, COMPLETE once it ran: every step is
   optional, so a failing step is a warning, never an hourly retry). The `nightly` keeps the
   critical steps, the screens, `edge-signals` (`edge_paper` is read as of
   `knowledge_ts <= cutoff`, so the picks must be in before the cutoff) and `history-copy`;
   `edge-eval`, `descriptions` and `verify` move out. A nightly step after the first critical one
   must write tables read bound to the session (fitness test).
2. **One session, once.** It runs only for `max(done nightly sessions)`: on a catch-up night the
   earlier sessions get no post-session run, as `latest_only` steps had none. It is a no-op when
   a published post-session record of that session exists (so a 30-minute launchd watchdog
   costs nothing), and `--force` runs again.
3. **Locks.** `descriptions` and `verify` write tables: they run under the ingest run lock
   (`exclusive_run`; taken: `busy`, exit 3, no record, a later start retries). `edge-eval` runs
   after, outside it, under the per-owner evaluation claim (ADR 0059) plus the named lock
   `post-session`, which the CLI holds for the whole run so two never overlap.
4. **No silent gaps.** When the session's `outcomes` step did not succeed in the nightly,
   `edge-eval` is SKIPPED with that reason in the record and the report.
5. **The audit** (amends 0063 amendment 6) is due on the last session of the ISO week (the
   exchange calendar's, so a Good Friday week audits on the Thursday), or when the edge's last
   audit is more than 9 days old; every other run is incremental. "The week's first night that
   runs the step" no longer fits a step that runs once a day after the nightly.
6. **Scheduling.** A second launchd agent (`com.algotrade.post-session`: `RunAtLoad` and a
   30-minute watchdog, under `caffeinate`), written by `algotrade-ingest schedule`, never installed
   (ADR 0044).
7. **Reporting.** The report gets a post-session section (status, steps, the verification
   lines); `[post] max_duration_minutes` in `nightly.toml` is its duration alert; the
   `nightly_duration` WARN measures the market-daily path alone. `make status` shows the last
   post-session line; the admin run reads and the availability `explain` also read post-session
   records (a verify gap cites the post-session run).
8. **Alerts** (owner decision, 2026-10-16): a failed post-session step, or a run over `[post]
   max_duration_minutes`, sends the same alert as a failed nightly step, through the nightly's
   notifier (`default_notifier`, `[notify] enabled`); a quiet run sends nothing.
9. **Unchanged:** ADR 0062's cutoff and completeness read the `nightly` record alone, so a
   post-session run finishing hours later never moves a session's cutoff.

## Consequences
- A session is served when the screens, edge signals and history copy are done; the 3 to 20
  hours of optional work no longer wait in front of it.
- `descriptions` and `verify` are no longer waivable nightly steps (they were optional).
- Edge-eval may read tables the next nightly is publishing: safe through the partition stamps of
  ADR 0063 (the stored legs and the partitions they read carry stamps, so a half-published
  night is detected, never mixed in).
- `recover_unpublished` (run by a nightly's start under the ingest lock) touches only runs
  whose record is RUNNING, FAILED or WAITING and that have pending writes: ingest runs. An edge
  evaluation commits outside the lock but writes its results pending with no run record
  (saved just before the commit), so recovery never rolls it back (test
  `test_recovery_leaves_an_edge_evaluation_committing_outside_the_ingest_lock`).
- A crash between the locked steps and edge-eval leaves no post-session record: the next start
  repeats `descriptions` (capped) and `verify` (read-only). Carrying finished steps across
  attempts, as the nightly does, is not built: the cost of a repeat is small.
- WF4's `market-daily` / `reference` / `enrichment` split builds on this: a second workflow
  already exists, with its own record, command and agent.
