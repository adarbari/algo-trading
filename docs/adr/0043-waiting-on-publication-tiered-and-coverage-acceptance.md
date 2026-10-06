# ADR 0043: Waiting on publication; tiered stale limits and coverage acceptance

**Status:** accepted (2026-10-05; architect-approved design). Amends
[0039](0039-ingestion-workflows-dependencies-and-acceptance.md) (a step gains a third
outcome, WAITING, before its deadline). Tiered stale limits and coverage acceptance (below)
follow in later PRs under this ADR.

## Context
On 2026-10-05 the nightly started at 17:21 PT. Massive's grouped-daily bars answered HTTP 403
for the current session (not published yet), so `bars` FAILED `bars_fresh`; Cboe had not
rolled its chains yet, so `chains` FAILED `chains_stale` (53.5% against 20%). Both resolve
themselves within hours, but ADR 0039 has only SUCCEEDED and FAILED: each failure mailed an
alert and the hourly retries kept the session FAILED until the owner read it. "The source has
not published yet" is not a failure until the day's deadline has passed.

## Decision
1. **A step can be WAITING.** An acceptance check may be marked `pending`: its FAIL only means
   "the source has not published the session yet". `judge()` turns a step whose failing checks
   are all pending into WAITING (reason: "not published yet: ...") while `wait` holds, and
   into FAILED otherwise. `pending` never applies to a fetch failure (`chains_fetch`, a task
   that raised, a 5xx), to a count or ratio check that compares stored data (`bars_count`), or
   to anything else.
2. **`wait` holds only for the latest session, before the step's deadline.**
   `config/site/nightly.toml`: `[schedule] data_deadline = "23:00"` (America/Los_Angeles
   wall-clock time on the session's date, converted per session, so DST is right) and
   optional `[steps.<name>] deadline`. A catch-up session (not the latest) is already past its
   deadline: its pending failure is FAILED, as before.
3. **A session with a WAITING critical step and no FAILED one is WAITING.** `overall()`
   returns WAITING; the steps that need the waiting step are NOT_RUN ("needs bars (WAITING)")
   and do not make the session FAILED. A critical step NOT_RUN for another reason, with
   nothing waiting, is FAILED as before; while something waits such a step is masked as
   WAITING and surfaces as FAILED at the deadline. Optional steps never wait.
4. **WAITING is not done and still holds back.** The nightly run record is stored WAITING
   (`RunStatus.WAITING`, publishes nothing like FAILED), so `last_done` ignores it and the
   next hourly launchd run resumes the session from where it stopped (steps that SUCCEEDED
   are reused, a WAITING step runs again). A WAITING session holds later sessions back
   exactly as a FAILED one does (0039, 6): the run stops there. A latest-only step that was
   WAITING and whose session is no longer the latest is FAILED as expired, never SKIPPED
   (a WAITING attempt counts as tried).
5. **Bars: a 403 or an empty answer means "not published" only if the session before answers
   200.** For the last closed session, `bars` probes the previous session once (no retries,
   outside the circuit breaker); 200 records the item NOT_PUBLISHED (the vendor works, it has
   not published this session) and `bars_fresh` is pending. Anything else (the probe also
   403s or errors, the status is not 403, the session is not the last closed one) stays a
   FETCH_ERROR / NO_SESSION failure: an expired key or plan must fail, not wait.
6. **Chains:** `chains_stale_core` and `chains_stale_rest` above their limits are pending.
7. **Notifications.** A WAITING run writes its summary file and nothing else: no desktop
   alert, no email (the hourly runs would repeat it). The run that ends the wait (SUCCEEDED,
   or FAILED at the deadline) reports as before. The email and the Admin ingestion page show
   WAITING with its own label and the `info` badge tone (not a failure colour).

## Later PRs under this ADR (not in this change)
- [x] **Tiered stale limits** (implemented): `max_chain_stale_share_core` (2%) for core names (S&P 500, priority symbols, HIGH liquidity; `chains/status.tier`, recorded at fetch time), `max_chain_stale_share` (20%) for the rest; checks `chains_stale_core` / `chains_stale_rest`.
- [x] **Coverage acceptance** (implemented): per key feature and tier, the share of the
  instruments the feature applies to (`Feature.applies_to`, decided by the function the read
  layer uses for NOT_APPLICABLE, ADR 0042) that have a value for the session; a null explained as
  an illiquid chain counts as covered, a missing value never as zero. Config
  `sources.toml [quality.coverage.<group>.<column>]`: `core_min`, `rest_min`, `max_drop` (against
  the previous session, recomputed from its stored partitions), `level` WARN or FAIL
  (`core_level`), `covered_by` `value` or `row` (earnings: a row without a next date is not a gap).
  The `coverage_<feature>` checks (`tasks/maintenance/coverage.py`) accept the `rollups` step (a
  FAIL fails it and holds the screens back; WARN is reported), run with `run_quality`, and the
  email's Coverage section shows feature x tier with the change and the missing names.
- [x] **Overdue earnings** (implemented): `covered_by = "recent"` grades a date rather than its
  presence: of the names with a row, a `last_earnings_date` over `max_age_days` (100) before the
  session with no `or_value` (`next_earnings_date`) is missing, listed with its last date. Core
  only (`rest_min` 0), WARN. It catches a hole in the source that the row rule counts as covered:
  FDX on 2026-10-02, last report 2026-06-23 and absent from Nasdaq's calendar for Sep-Dec 2026.

## Consequences
- A late source no longer pages the owner; the session still FAILS at 23:00 PT if the data
  never arrives. The deadline is a config value, per step if one source is habitually later.
- While a session waits, later sessions wait too (no gaps in lookback windows), as for FAILED.
- The probe costs one request in the rare 403 case only; the run record says why a step
  waits, so a real outage reads differently from a late publication.
- `RunStatus` gains `waiting`: run records are read by name, so Admin shows it as is.
