# ADR 0062: Reads serve the last complete session and disclose the newer one

**Status:** accepted (2026-10-10; owner decision). Amends [0036](0036-session-strictness-for-reads.md)
(which session a read defaults to) and implements decision 8 of
[0039](0039-ingestion-workflows-dependencies-and-acceptance.md), which was never built. Spec:
[docs/api/read-model.md](../api/read-model.md) ("Session resolution").

## Context
`resolve_session(None)` was the latest `bars/1d` partition. On 2026-10-09 the bars landed and
the chains step failed its stale-chain acceptance check, so the rollups, the screens and the
history copy were NOT_RUN and every page served 10-09 with UNKNOWN / NOT_RUN gaps while 10-08
was whole. ADR 0039 decided "reads default to the latest SUCCEEDED session" but left the
default at the latest bars. The owner decided: until a session's whole nightly workflow has
completed, reads serve the last complete session and say so; failed steps are retried (the
nightly already retries hourly), never waived to unblock.

## Decision
1. **The default session is the latest session whose nightly workflow is complete**, by the
   one rule the ingestion planner already uses (`sessions.last_done` -> `run.last_finished_session`):
   a session is done when **any** of its `nightly` run records is COMPLETE (SUCCEEDED; a step
   waived by hand counts, as 0039 says) or PARTIAL (records written before 0039). FAILED, WAITING
   and unfinished records are not done. The rule is written once, `storage.runs.done_sessions`
   (owner `run-records`); the planner and `services/read/session.py` (`completeness`) both call
   it, so they cannot disagree, and the planner's behaviour is unchanged. The session also needs
   a `bars/1d` partition. The read side reads the records through the store reader; it never
   imports the ingestion app.
2. **Still exactly one session per read.** Nothing mixes partitions: the newer, incomplete
   session is not read at all.
3. **An explicitly requested date is unchanged** (ADR 0036): served as asked, no notice.
4. **Disclosure.** `Session.newer` is the newest session after the one served that has bars or
   a run record but is not complete: its date, its state (`IN_PROGRESS`: running, waiting for a
   source, or not started; `FAILED_RETRYING`: a critical step failed, the hourly nightly
   retries it) and, for a failure, the public `UnavailableKind` only (`SYSTEM`). The failing
   step, table and error stay admin-only (ADR 0056). `Session.complete` says whether the served
   date's workflow is complete. Every page shows a notice from `newer` (the status strip, on
   every route); its words and the term it opens are Guide content (ADR 0051).
5. **Empty history.** When no session is complete (a store with no nightly records, or all
   failing) the latest bars are served as before and `complete` is false: flagged in the read
   model, not an error.
6. **The caches follow the run records.** A workflow turning COMPLETE saves a run record, not a
   table, so no publish moves. The resolved session is kept per publish and runs generation,
   every GraphQL response key holds the resolved default session (date, newer date, state,
   public kind), the run operations also the runs generation, and the cache warmer warms again when
   the served session or `newer` changes: pages flip to the new session without a restart.
7. **One default.** `session.default_session(reader)` (the latest complete session, else the
   latest bars) is used by `resolve_session` and by the on-request screen run (ADR 0033), so a
   run with no date never targets the incomplete day while pages show the previous one.

## Consequences
- A failing night no longer blanks the pages: they show the previous whole session and a notice
  until the retry (or a deliberate waive) completes it.
- A session completes only when every critical step has: chains (2 to 4 h) now gate what users
  see, so the new session appears later than its bars did.
- `Session.is_latest` now means "the date a read with no date serves".
- A job's or checkpoint's run record changes no session, so it evicts only the run operations;
  a nightly completing a session changes every key at once.
- A waived session counts as complete: waiving is the owner's explicit acceptance, as in 0039.
- Old PARTIAL sessions count as done, as they do for the planner (no retry of them).
