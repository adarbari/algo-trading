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
1. **The default session is the latest session whose nightly workflow is complete.** A session
   is complete when its latest `nightly` run record (by start time) is `COMPLETE` (SUCCEEDED:
   every critical step SUCCEEDED or was waived by hand; an optional step's failure does not
   count) and it has a `bars/1d` partition. PARTIAL (records written before 0039), FAILED,
   WAITING and RUNNING are not complete. The check reads run records through the store reader,
   in `services/read/session.py` (`last_complete`); the read side never imports the ingestion
   app.
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
   every GraphQL response key holds the runs generation, and the cache warmer warms again when
   the served session or `newer` changes: pages flip to the new session without a restart.
7. Writes are out of scope as in 0036: an on-request screen run still targets the latest
   session with data (`latest_session`, ADR 0033).

## Consequences
- A failing night no longer blanks the pages: they show the previous whole session and a notice
  until the retry (or a deliberate waive) completes it.
- A session completes only when every critical step has: chains (2 to 4 h) now gate what users
  see, so the new session appears later than its bars did.
- `Session.is_latest` now means "the date a read with no date serves".
- Every response is re-read once after any saved run record (a job's too), because the key
  holds the runs generation for all operations, not only the run ones.
- A partially failed or waived session counts as complete once the owner waives its steps:
  waiving is the owner's explicit acceptance, as in 0039.
