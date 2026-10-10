# ADR 0059: An edge evaluation can be run on request

**Status:** accepted (2026-10-08; owner decision: "yes we need ability to run evaluation").
Amends [0005](0005-ingestion-is-the-only-writer.md) (the API's write paths),
[0037](0037-domain-read-model-served-by-graphql.md) (one more REST route that is job plumbing) and extends
[0033](0033-screeners-run-nightly-and-on-request.md), [0053](0053-edges-hypotheses-outcomes-and-one-harness.md).

## Context
The edge harness (ADR 0053) runs only from `algotrade-backtest evaluate-edges` (job kind
`edge-eval`). A trader who edits their split (ED5a) or opens an edge cannot refresh its runs
without the owner at a terminal. A run takes about a minute (`month_end`) to 30 to 40 minutes
(event edges) and writes `results/edge_eval` and a run record.

## Decision
1. **The same job, on request.** `POST /edges/{id}/evaluate` starts the CLI's `edge-eval` job
   (`services/ondemand/edges.py`, `OnDemandEdges`), never inline in a request (ADR 0010), and
   answers 202 with the job; `GET /jobs/{job_id}` polls it (moved there 2026-10-08, ADR 0037
   amended; it was `GET /edges/{id}/evaluate/{job_id}`). The decision sessions
   are the stored outcome sessions, outcomes known now, the split the edge's own `frozen_from`
   (a copy's, ADR 0053 amendment 2026-10-09) (a run under any other split is EXPLORATORY, as from the CLI).
2. **Whose rows.** Any signed-in user may evaluate an edge for themselves: the job runs as that
   user and its rows are keyed by their `user_id`. An admin may run it as the site (`?as_site=true`:
   the site's canonical run); anyone else asking for it gets 403. A job is read by its owner or
   an admin; a site run is readable by everyone (as a site preset's screen run is).
3. **One at a time per user.** Evaluations are heavy on the owner's Mac. A request while another
   evaluation of the same owner is queued or running (any edge) is refused with 409; the check
   and the submit are one step under a lock (one API process is assumed, ADR 0028). A job older
   than two hours counts as dead (a stopped process; the longest run is ~40 minutes) and jobs a
   stopped process left in flight are failed on start.
4. **The API's write path stays narrow.** Like ADR 0033's, a dedicated runner with its own single
   worker (an evaluation never holds a screen run behind it) whose only kind is `edge-eval`; it
   does not wait for ingestion (the harness reads committed data and publishes atomically, ADR
   0022) and writes only `results/edge_eval` and run records through `ResultWriter`. Market,
   feature and outcome data stay ingestion's alone (ADR 0005, 0053).
5. **REST allow-list.** The poll was one more `GET` kept REST by design (job polling):
   `max_get_routes` went from 4 to 5 with an amendment of ADR 0037. Superseded 2026-10-08: both
   polls are the one `GET /jobs/{job_id}`, count back to 4.

## Consequences
- The Edges page's edge detail has a "Run evaluation" button; it shows the job's state and reads
  the edge's runs again when the job completes.
- A second API process would not see the first's in-memory lock: the guard assumed one process (superseded 2026-10-10: the lock is the store's).
- A request to run an edge with no stored outcomes is a 400.

## Amendment 2026-10-10: owner-only runs, a lock across processes, who and what in the run stats
(owner decisions 2026-10-10; the owner-driven-edges series, PR 3)

- **Only the owner runs an edge** (replaces decision 2). Every edge has a Run button, but a user
  runs only an edge they own (`Edge.owner` is their id: their own edges, a clone of a site edge
  included, which is theirs). A site edge by a non-admin, or by an admin as himself, is refused
  with 403 (`PermissionDeniedError`). Admins run a site edge with `as_site` ("Run as site"): the
  run uses the site owner and is the site's canonical run. An edge the caller cannot see (another
  user's) is a 404, never a 403, so an id's existence is not disclosed. A run is recorded under
  its owner with `trigger = ui`. Replaces "any user runs a site edge for themselves, exploratory".
- **One at a time per owner, across processes, for every caller** (replaces decision 3's
  in-process lock and the consequence that one API process is assumed). `claim_edge_eval`
  (`services/jobs/exclusive.py`) is the one claim: the API, the CLI (`run_edge_eval_claimed`) and
  the nightly all take it. It holds `Backend.lock("edge-eval:<owner>")` without waiting for the
  check-and-submit (the CLI holds it for its whole run) and refuses while an evaluation job of
  the owner is queued or running; a held lock or an in-flight job is `EdgeEvalBusyError` (the API
  answers 409, the CLI prints it and exits 2). The runner stays single-worker.
  **Limitation:** liveness is the job record's age (`EDGE_EVAL_STALE`, 2 hours), not a lock held
  for the whole run: that needs the runner's worker to hold the lock around each job, which is a
  restructuring of `LocalJobRunner` left for later. A crashed API run blocks its owner for up to
  two hours, or until the next API start fails it (`recover`).
- **Who and what in the run stats.** The run record's `stats` carry `owner` (the edge's), `trigger`
  (`nightly` | `ui` | `cli`) and `job_id` (the job that wrote it), written by `write_edge_eval`; the
  job takes `trigger` as a param (default `cli`; the CLI passes `cli`, the on-request runner `ui`,
  the nightly `nightly`). The job name `edge-eval:<edge>:<owner>` stays the lookup key, built only
  by `job_name`. No new table. A run written before this has no trigger: the read model and
  GraphQL (`EdgeRun.trigger`, `EdgeRun.legacyOwner`) serve null, never an invented value.
- Guide terms "Who may run what" and "Run trigger" explain both to users (ADR 0051).
