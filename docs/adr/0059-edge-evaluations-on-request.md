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
   are the stored outcome sessions, outcomes known now, the split the user's `evaluation.toml`
   else the edge's `frozen_from` (a run under any other split is EXPLORATORY, as from the CLI).
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
- A second API process would not see the first's in-memory lock: the guard assumes one process.
- A request to run an edge with no stored outcomes is a 400.
