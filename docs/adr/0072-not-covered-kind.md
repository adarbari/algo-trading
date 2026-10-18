# ADR 0072: The NOT_COVERED kind and `uncovered_statuses`

**Status:** accepted (2026-10-17; architect-approved design). Amends
[0056](0056-role-scoped-causes.md) (the public kinds of a gap) and
[0042](0042-not-applicable-and-illiquid-values.md) / [0046](0046-explained-absences.md)
(the precedence of an absence).

## Context
The analyst vendors of [0068](0068-analyst-data-vendors.md) cover few names: the free FMP key
reaches about 15% of the universe. For analyst-derived fields most instruments will have no value
and nothing wrong behind it, and the instrument is not "not stored" (a later fetch cannot fill it)
nor "not applicable" (an analyst could cover it). A trader needs a word for it, and the Guide a
term, without the vendor, the endpoint or the fetch state being named.

## Decision
1. **A new public kind `NOT_COVERED`** (`UnavailableKind` and `UnknownCode`, public words "not
   covered by our analyst data", Guide term `unavailable_not_covered`). Like every kind it names
   no table, vendor, step or status; the chain behind it stays admin-only (0056 decision 2-3).
2. **`Feature.uncovered_statuses`**: the `null_status` values that mean the source does not
   cover the instrument. It is its own list beside `illiquid_statuses` and `explained_statuses`
   (a status is in at most one of the three; `null_status` needs at least one) and the fifth slot
   of `StatusRule`, inherited by an expression feature from the features it reads.
3. **Precedence of an absence**: a present value, then NOT_APPLICABLE, ILLIQUID, NOT_COVERED,
   EXPLAINED, no row, null. NOT_COVERED sits after ILLIQUID and before EXPLAINED.
4. **NOT_COVERED and NOT_FETCHED read the same publicly.** A feature declares both statuses (the
   source has nothing for the name, and the name was never asked) in `uncovered_statuses`; a
   trader reads "not covered" for each, while the admin cause names the stored status and so tells
   them apart.
5. **A stale analyst value reads as NOT_STORED**, not as the old value and not as NOT_COVERED:
   the read serves one session (0036) and a value past its freshness is not stored for it.
   It is not an `uncovered_statuses` member.

6. **The nightly coverage check exempts uncovered statuses** like illiquid and explained ones
   (`tasks/maintenance/coverage.py`, not in `GAP_IN_CORE`), else most names would grade as gaps
   and fail the step (0055). That hides the never-asked backlog (NOT_FETCHED) from coverage, so it
   needs its own measure: an analyst fetch-backlog check (names never fetched / universe), added
   with the analyst reader.
7. `uncovered_statuses` is for analyst-sourced features until the public words are generalised.
   The table cell word "Not covered" shares its words with the Describe-it "Not covered" note
   (`describe_not_covered`); the two are unrelated and the glossary keeps separate terms.

## Consequences
No stored feature declares `uncovered_statuses` yet: this ADR adds the mechanism, its word and its
Guide term; the analyst reader and feature groups use it later. A screen treats NOT_COVERED as
missing data (a hard criterion rejects). The GraphQL enums `UnavailableKind` and `UnknownCode`
gain `NOT_COVERED`, the web words it as "Not covered".

**Update (the analyst reader PR):** `analyst_estimates@v1` and `analyst_targets@v1` are the first features
to declare `uncovered_statuses` (`NOT_COVERED`, `NOT_FETCHED`). The never-asked backlog of decision 6 is the
`analyst_backlog` acceptance check on the `analyst-snapshot` step (`tasks/analyst/backlog.py`, WARN only, `[quality]
max_analyst_backlog`); a fitness test (`tests/apps/ingestion/tasks/analyst/test_backlog.py`) fails when a
feature declares `NOT_FETCHED` and the step does not run it.

**Update (the ratings and revisions PR):** `analyst_ratings@v1` (Finnhub) and `analyst_revisions@v1` (the estimates' status passed through) also declare `NOT_FETCHED`; it reads Finnhub, so the
`finnhub_backlog` check (same module, same `max_analyst_backlog`, Finnhub's own refresh windows, a WARN with the reason when the run skipped Finnhub)
is on the step too, and the fitness test's list maps each declaring group to the check of its vendor.
