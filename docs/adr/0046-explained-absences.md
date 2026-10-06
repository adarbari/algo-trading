# ADR 0046: Explained absences

**Status:** accepted (2026-10-06; owner request, architect-approved plan). Extends
[0042](0042-not-applicable-and-illiquid-values.md) (one more `UnknownCode`, one more declared
status list) and [0036](0036-session-strictness-for-reads.md) (the vocabulary of a value missing
for the session). Selections are unchanged ([0015](0015-configs-selections-users.md)).

## Context
After ADR 0042 the Explore table still said "Unknown" for cells whose null is itself a fact.
On session 2026-10-02 (11,427 tickers): 139 closes had no bar on the session (the instrument
did not trade; last bar 1 to 5 sessions earlier), 367 next-earnings dates were null because the
company has not announced one, and about 2,170 `pct_from_high_52w` cells were null because the
listing is younger than the window or trades too rarely to fill it. None of these is a gap in
our data, and "Unknown" hides the cells that are.

## Decision
1. **One new `UnknownCode`, `EXPLAINED`, with a closed `NullReason`**
   (`features/framework/feature.py`): `NO_TRADE` (no bar on the session), `NOT_ANNOUNCED` (no
   next report date announced), `NEW_LISTING` (too few sessions since listing for the window),
   `FEW_BARS` (trades too rarely to fill it). `Unknown` gains `reason`, set exactly when the code
   is `EXPLAINED`. A new reason is an addition to the enum (and its web label), never free text.
   `ILLIQUID` stays its own code (ADR 0042).
2. **Declared, not inferred**, like ADR 0042: `Feature.explained_statuses` lists the values of
   the feature's `null_status` column that explain its null; the status value *is* the reason
   (`bar_status` `NO_TRADE` reads `EXPLAINED` / `NO_TRADE`), so each must be a `NullReason`
   value and a declared category of the status column (fitness test). A `null_status` needs
   `illiquid_statuses`, `explained_statuses` or both; one status value is never in both. Any
   other status value leaves the null as it was.
3. **Precedence** (`services/read/instruments/features.py::_absence`): no partition, a present
   value, `NOT_APPLICABLE`, `ILLIQUID`, `EXPLAINED`, `NO_ROW`, `NULL`. `EXPLAINED` wins over
   `NO_ROW` so a close with no `price_stats` row on the session reads "no trade" when a stored
   status for that session says so; without that status it stays a gap. The status is a fact
   stored for the session (ADR 0036): an older partition's value is never served. An
   explained status covers a missing row only in the table of the feature that declares it:
   when a value reads several tables, `EXPLAINED` needs every table without a row to be
   covered, so one input's "not announced" never hides another input's dropped row.
4. **Inherited by expressions** like ADR 0042's statuses (`FeatureSet.applicability`).
5. **The read model carries the reason**: GraphQL `Unknown.reason: NullReason`, and the
   columnar `FeatureTable` / `ScreenResultPage` gain `reasons[i][j]` beside `unknown[i][j]`.
   The web labels each reason from one exhaustive switch ("No trade", "Not announced",
   "New listing", "Too few trades").
6. **Coverage** (ADR 0043) counts an `EXPLAINED` null as covered, except `NO_TRADE` for a core
   tier name: a vendor-dropped bar for a large stock must not pass as "no trade".

## Consequences
- The statuses come from features: a stored price-history group with `bar_status` and a
  range status (high since listing), and a status-only group `earnings_schedule@v1`
  (`next_status`) beside `earnings@v1`; each is its own PR under this ADR. A status column
  is added as its own small group, not by re-versioning the group it explains: a re-version
  would rewrite the published screener presets that name the old fields (their config
  hashes, ADR 0015).
- Screeners, backtests and `core.views` still see a null (ADR 0015): an explained null never
  passes a filter.
- GraphQL and the web codegen gain `EXPLAINED`, `NullReason` and `reasons`.
