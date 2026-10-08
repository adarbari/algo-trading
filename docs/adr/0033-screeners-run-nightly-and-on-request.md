# ADR 0033: Every screener runs nightly; a screener can be run on request

**Status:** accepted (2026-10-05; owner decisions). Amends [0029](0029-rule-screener.md) (the
schedule switch), [0005](0005-ingestion-is-the-only-writer.md) and
[0024](0024-api.md) (the API's one new write path, below).

## Context
The nightly runs only screeners whose `schedule` is `nightly`. A user's screen has a separate
switch for it, a site preset has none unless its file says so, and the shipped `vrp_scanner`
presets did not: nothing ever ran them, so the Results page had nothing to show. A screener
that was never run, or changed since it last ran, can only be run from the CLI.

## Decision
1. **No schedule switch.** The nightly `screens` step runs every site screener preset (as the
   `site` user) and every finalised screener of each user. Finalising a screen is what puts it
   on the nightly; a draft that was never finalised is not run. `schedule.toml`,
   `PUT /screeners/{id}/schedule`, the Builder toggle and the list's Schedule column go. A
   `schedule` key in an older document is accepted and ignored (the immutable `vrp_scanner`
   v1 to v3 presets still carry a "not scheduled" comment; their files are hash-locked).
   `services.configs.nightly_screeners` replaces `scheduled`.
2. **A screener can be run on request** from the API (`POST /screens/{id}/run`):
   for the latest session with data, unless results for this screener version (config hash)
   and session are already stored, in which case nothing runs and the stored ones are
   reported. (Amended 2026-10-07: only COMPLETE results count; a PARTIAL run read a table
   with no rows for the session, which may have landed since, so a request runs it again.) The request returns a job id; the page polls `GET /jobs/{id}` (ADR 0010).
3. **Results of an on-request run are stored like the nightly's**: the same `screen` job
   writes `results/rule_screen*` atomically (ADR 0022) and a run record, so the next view,
   the Ideas list and the nightly's "new / dropped" comparison all see it.
4. **The API's write path is narrow.** A dedicated library entry (`services/ondemand`, like
   `services.live` in ADR 0028) hosts a local job runner whose only job kind is `screen`,
   does not wait for an ingestion run (a backfill holds the ingest lock for hours; a screen
   reads committed data and publishes its results atomically under the store's commit lock,
   ADR 0022), marks jobs a stopped process left running as failed on start, and writes only
   result tables and run records through `ResultWriter`. Market and
   feature data stay ingestion's alone (ADR 0005).

## Consequences
- A user's finalised screen and every site preset appear in the next nightly with no setup.
  A screener the nightly cannot fully run (a missing source table) makes the step PARTIAL,
  as for any screener.
- Rule screens cost about 11k rows each per night; the nightly's screens step grows with the
  number of finalised screens. If that becomes slow, the step can parallelise (the job
  runner already has a pool).
- Part 1 (the nightly) shipped first; part 2 is `services/ondemand`, `POST /screens/{id}/run`
  with `GET /screens/{id}/run/{job_id}`, and "Run now" on the Results page.
