# ADR 0086: A failed older session no longer stops the latest session's snapshot steps

**Status:** accepted (2026-10-31; owner decision after the 2026-10-26 to 10-31 incident; an
architect reviewed this ADR). Amends [0039](0039-ingestion-workflows-dependencies-and-acceptance.md) decisions 6
and 7.

## Context
Session 2026-10-26 FAILED at `rollups` (a row without `known_from` in the point-in-time guard,
fixed in PR 982) and was retried about 90 times. Rule 6 held 10-27 to 10-30 behind it, so the
`chains` snapshot of 10-27 (the vendor serves only its current snapshot) was never fetched; the
option screeners for 10-27 to 10-29 can now never complete without an owner `--waive chains`.
A bug in a computing step cost data that no later run can fetch.

## Decision
1. **Snapshot steps run for the latest closed session even when an older session is FAILED or
   WAITING.** Every step with `latest_only = SNAPSHOT` (`universe-build`, `chains`, `ibkr-iv`,
   `analyst-snapshot`, ...) runs in a *snapshot-only pass* of that session, in the same
   nightly, after the older session stops. Only that session's own partition is written
   (`session_date`, `ts`, `knowledge_ts` as ADR 0007): no lookahead and no older partition
   touched.
2. **Everything else stays held.** Rollups, screens, edge-signals, edge-picks and every other
   step of the held session are recorded `NOT_RUN` ("held: session D not done"), so rule 6
   stands for them: nothing computed from a later session until the oldest one SUCCEEDS or is
   waived. The pass writes a `nightly` run record for the held session (FAILED, snapshot steps
   filled in); it never makes the session complete, and reads (ADR 0062) still serve the latest
   complete session.
3. **No refetch later.** When the older session clears, the held session runs normally and its
   snapshot steps are reused from the pass ("succeeded in an earlier attempt", ADR 0039
   amendment 2026-10-10), cited by origin run. A snapshot step that failed in the pass and
   whose session is no longer the latest expires as before (decision 7: owner `--waive`).
4. **Only the latest closed session**, whether it is held behind a failed session or lies past
   the catch-up cap (`max_catch_up`; the incident had six pending sessions and a cap of five): an intermediate held session stays untouched (the source
   no longer serves its snapshot, so there is nothing to take). The disk floor
   (`[resources] min_free_gb`) is checked at the CLI before any run and still applies.
   `FINALLY` steps and the summary keep their reference to the sessions that ran; the pass is
   listed under `snapshot_runs`.

## Consequences
- A computing-step bug no longer loses the snapshot of the newest session; it still blocks
  everything derived (the data is complete, the derivations catch up in order).
- The hourly retry re-enters the pass; its steps are carried, so a retry costs no refetch.
- A failed critical snapshot step of the pass is named in the notice ("snapshot pass D") and
  its optional ones are warnings, since the next day it can no longer be fetched.
- The "newer session" disclosure of ADR 0062 may name the held latest session (its pass
  record is FAILED); its public kind is unchanged.
- Code: `run_nightly` / `run_session(held_behind=...)` in `workflows/nightly/nightly.py`; tests
  in `tests/apps/ingestion/workflows/nightly/test_nightly_snapshots.py`.
