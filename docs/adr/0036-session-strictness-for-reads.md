# ADR 0036: Reads serve one session: point-in-time strictness for everything a page shows

**Status:** accepted (2026-10-05; owner decision). Extends [0007](0007-point-in-time-data.md)
(point in time, the one snapshot rule). Spec: [docs/api/read-model.md](../api/read-model.md)
("Session resolution"). Implemented over read-model PRs 2-10; PR 1 records it.

## Context
Six different rules decide which partition a read sees today: `instrument_view` reads the exact
session, `rollup_row` and `partition_for` the latest partition on or before the date (each group
on its own), `latest_session` the latest bars else reference partition, expression features the
latest date any input has, holdings their issuer date. Ideas takes each screen's latest run
from up to 20 sessions back. So one page can show a value for session S next to one for S-3
with no marker (the MRVL earnings display bug: the rollup's partition, the raw events and the
browser's "today" disagreed). The browser re-derives stored facts from raw rows, adding a
seventh clock.

## Decision
1. **One resolved session per read.** A request resolves one `Session` once: the date asked
   for, else the latest `bars/1d` partition (no bars: the latest reference snapshot). Every
   value in the response is for that date. One owner: `services/read/session.py`
   (`resolve_session`; ownership `session-resolution`).
2. **Session-grain tables are read for exactly that date** (`rollups/instrument/*`, `chains/*`,
   `results/*`, the day's bar, `verification/*`, `live/*`). A fact not calculated or pulled for
   it is **UNKNOWN with a reason** (`NO_PARTITION`, `NO_ROW`, `NULL`, ...; `services/read/values.py`),
   never an older partition.
3. **A screener with no run for the session is `NOT_RUN`.** The Ideas 20-session lookback goes.
4. **Other grains keep their one rule, disclosed.** Snapshot tables (reference, company,
   universe, id map, IBKR contracts) use ADR 0007's snapshot rule (latest on or before, else
   earliest flagged `pre_snapshot`) and every response says which snapshot it used
   (`referenceSnapshot`, `preSnapshot`). Events are read by event date among the rows known on
   or before the session (`known_from`, ADR 0050); splits, dividends, reference and index
   changes, facts of record the adjusted bars use, by event date unbounded. ETF holdings use
   the latest issuer `as_of` on or before the date and disclose it. Descriptions are the latest row.
   Ranges (bars, series) are explicit `[start, end]`, never "latest".
5. **Writes are out of scope.** An on-request screen run picks the latest session with data to
   run (ADR 0033); it writes results, it is not a read, and may call the latest-session helper.
6. Loaders read session-grain tables only through `partition(ctx, table)` for
   `ctx.session.date`; a loader that needs another date takes it as a named argument
   (`previous_session`). Nothing else computes "latest".

## Consequences
- Pages show more UNKNOWN cells on sessions a rollup missed: correct, and visible in
  `session.missing`; the nightly's catch-up gaps become visible in the UI.
- Ideas lists only screens that ran for the session and names the others `NOT_RUN`.
- `?date=` changes meaning from "latest on or before" to "exactly": breaking for REST readers,
  one reason REST reads retire (ADR 0037).
- Identity is not strict: making it strict would blank every ticker on a day the universe build
  did not run; disclosure keeps it honest. Strict identity would need a universe build per
  catch-up session first (an ingestion change, a new ADR).
- `partition_for`, `latest_session`, `rollup_row` in reads, `_latest_runs` and the other ad hoc
  rules are deleted as their callers move; the ownership rule fails any new caller now.
