# The page-latency bar and its history

Owner decisions of 2026-10-22 (`docs/decisions/log.md`): the "1 s bar" is judged **per view on
its critical path**: the view's slowest request, the empty-cache first request, under 1 s. The
**shell** requests every screen asks for (Viewer, SessionDate, Regime, StatusStrip, EdgeDesk and
GuideEntries, a variant counted at its slowest) are judged together, a separate limit of 1 s. A
view whose critical-path operation is a named exception may exceed 1 s until its fix. The rule is
data: `benchmarks/perf_bar.toml` (limits, shell operation names, and each exception with its
reason and date; the owner withdraws one there).

## Run it

On a **clone** of the store only (`--data-url` is required and the real store is refused, as in
`api_latency.py`); never in CI (it needs the clone; the nightly run is described below).

    make api-latency-fast ARGS="--data-url file://<clone>/data"            # judge: exit 1 over the bar
    make api-latency-fast ARGS="--data-url file://<clone>/data --record"   # and append to the history
    make api-latency-fast ARGS="--data-url file://<clone>/data --ratio-mode"  # busy machine
    make api-latency-fast ARGS=--history                                   # the trend, no measuring
    make api-latency-fast ARGS="--data-url file://<clone>/data --only IdeasPage,EdgesPage"  # a re-measure
    make api-latency-fast ARGS="... --out <dir>"   # ops.json, views.json, samples-partial.json per pass

One API process (warmer off, `release_reads=false`), a patched endpoint empties every cache before
each timing, each distinct operation is timed 5 times and averaged (3 when over 10 s), the 1-minute
load is gated at 4. A run takes at most 5 minutes (below). The views and their documents come from the committed capture
`benchmarks/api_latency_views.captured.json`: a generated data file (the crawler's output with the
browser's real documents and variables, ids substituted), never hand-edited, like
`benchmarks/baseline.json`. Without it the tool falls back to the static list
`benchmarks/api_latency_views.json` and warns loudly: that list has no variables, so it is not
the real load. A view with no captured document is listed as not measured.
`--ratio-mode` divides every time by the shell's slowdown against the last recorded run (the shell
is untouched by the work judged), never below 1: use it when `uptime` shows the machine busy.

Run it only on a quiet machine: 1-minute load at most 4 and at least 8 GB free on the clone's
volume (the guards `--min-free-swap-mb` / `--min-free-disk-gb` default to those floors; the tool
waits up to 3 minutes for them and never lowers them). An operation timed above `--load-max` is
`noisy`; a noisy run, or an `--only` subset, is not appended by `--record` (`--record-noisy`
keeps it, flagged). Exit codes: 0 every view and the shell within the bar or a named exception;
1 something over, or an integrity failure (an operation that failed, answered empty, or was not measured); 2 refused (no clone).
Do not point it at `var/`, the real store, launchd or the live API, and never export
`ALGOTRADE_DATA_URL`.

## Refresh the capture

Refresh it when the gate reports an operation that returns an error or null, when
`make api-latency-docs` says the documents drifted, when the catalogue renames fields, or when a
page's reads change (the committed-capture tests name the first two). On the clone, about 22 minutes:

    make api-latency-views-capture ARGS="--data-url file://<clone>/data --max-views 200 \
        --views-file benchmarks/api_latency_views.captured.json"

(copy `benchmarks/api_latency_views.json` there first when the file is missing; stop the crawl
once `captured` is set on every static view), then run the gate. The gate **fails loudly** on an
operation that errors (HTTP error or a GraphQL error: "operations that failed (a fast failure is
no pass)", exit 1), so a stale capture cannot pass silently; two tests fail CI when the capture
names an operation the web no longer has or a feature the catalogue no longer has.

## The time budget

A round must stay under 5 minutes, so `--budget-s` (default 270 s) caps the timed passes: after
each pass the tool stops when the next one (predicted as the mean of the passes so far) would
overrun it. At least 2 passes always run, at most `--reps` (default 5); an operation over 10 s on
its first timing still gets 3 only. The output states the passes done and the budget used, and a
view's critical path is the average of the passes done. A run of fewer than 3 passes is
`LOW-CONFIDENCE` and, like a noisy run, is not recorded. The wait for the load gate ends after
60 s: the pass runs and its operations are flagged noisy. With the process start and the op-set
build the run ends under 300 s; the nightly wrapper's total, with its CoW snapshot (about 4
minutes), is about 6-9 minutes.

## Read the table

One row per view, slowest first: the view's critical path (its slowest operation, averaged), that
operation, and the verdict: `ok`; `EXCEPTION` (over, but its slowest operation is a named
exception); `OVER` (fails the gate). The last line gives the views over 1 s, the seconds above the
bar and the shell's combined time. Fix the slowest operation, not the view: one operation is on
many views (EdgesPage on every edges list view).

## Read the history

`benchmarks/critical_path_history.jsonl`: one JSON line per recorded run, written **only** by
`--record` (`--history-file` picks another file, as the nightly does) or by a PR: date, git sha, a
`method` (`empty-cache`; rounds 1 and 2 are `cache-mode`, a different method that `--history`
marks "not comparable"), the passes done in `mode`, load before and after, a machine note, per view `crit_s` (critical
path), `sum_s` and `slowest_op`, and `totals` (`views_over_1s`, `seconds_above_bar`,
`shell_total_s`). `--history` prints a summary line per run and the critical-path trend of every
view that was ever over 1 s. Compare runs only when the machine notes allow: round 3 ran with the machine 2x slower than round 4; the shas of the round 3 and 4 lines are inferred from
merge times. Fitness tests: `tests/scripts/perf/test_fast_bench.py`.

## The nightly run (a description; the owner installs it)

`scripts/ops/perf_gate_nightly.sh` runs the gate once a night at **03:00 America/Los_Angeles**,
and as soon as possible after 03:00 when the machine was not available then (an ingest holds the
lock, free disk under 12 GB, 1-minute load over 4, or the Mac was asleep).

**Why a clone.** The gate empties every cache before each of about 300 timings: pointed at the
live data or the live API it would load the live site, and the store changes under it (an ingest
mid-copy gives a torn snapshot). It runs on a copy-on-write clone of a store no writer
touches; the tool itself refuses the real store, by design. **What is copied:** only what the API
and the bench read: `tables/`, `runs/` and `serving/` (`locks/` is created empty). `raw/` (vendor
payloads, 4 GB and 121k files) and `staging/` (transient, 124k files) are not copied: nothing in
the read path (`services/read`, the API) opens them, so the clone has about 1.14M files instead
of 1.38M. The list is explicit in the wrapper (`copy_entries`) and tested with a fixture store.
**Cost:** the clone shares every block with the store (APFS `cp -c`), so near-zero disk; the copy
runs at low I/O priority (`taskpolicy -b`, `nice` where there is none) so it does not slow the
live site: the effect on the copy time is to be measured on the first night. The clone is renamed
to a sibling `data.trash.<date>` at the end (instant) and deleted afterwards, detached, at low
priority; a leftover trash of an earlier run is deleted first, in the background, never blocking
the start (a free-disk refusal then says the trash is still being deleted). Only a sibling
`<PERF_CLONE_ROOT>.trash.*` (for example `/Users/adarbari/perf-clone/data.trash.2026-10-23`) is
ever deleted. The clone must be on the store's volume (`cp -c` silently copies every byte across
volumes): the wrapper refuses, exit 2, when the device ids differ.

**Idempotent per local date, one instance at a time.** Before 03:00, or when
`var/logs/perf_gate.status` already holds a finished run for today, it exits 0 at once. An atomic
lock (a symlink to the holder's pid, `var/logs/perf_gate/lock`; a dead pid, an empty or garbage target or a pid with another process start time (a reused pid) is stale and taken over under a guard; released
on every exit including TERM / INT, which also kill the bench's process group and drop the clone)
makes a second instance (the 900 s retry) exit 3 "busy" without touching the first one's clone.
A guard (a writer in `ps`, disk, load, a writer that started during the copy: the clone is
discarded) also exits 3; it is not a finished run and appends no `summary.csv` line, so retries
continue. After the copy **every** outcome is a finished day (one notification, never a re-copy
at the next retry): `ok`, `over-the-bar`, `integrity` (an integrity failure: its own notice lists the failures, not "0 views over"), `over-time`, `refused` (the bench refused) and
`crashed` (it died without a result). Exit codes: 0 done (clean) or nothing to do today; 1 a view
over the bar without a named exception, an integrity failure (below), or a crash; 2 refused (a
path guard, an empty or relative `PERF_CLONE_ROOT`, or the bench refused); 3 busy, retry; 4
over-time (the bench hit its 300 s cap); 143 stopped by a signal. Each finished run appends
`date= sha= views_over= seconds_above= exit= finished= outcome=` and the phase timings to
`var/logs/perf_gate.status` and keeps the output in `var/logs/perf_gate.last.log`.

**Nothing leaves `var/logs`.** The nightly records its history to `var/logs/perf_gate/history.jsonl`
(`--history-file`), never to the repo: a modified tracked file in the main checkout would make
`deploy.sh` stop ingest deploys. The tracked `benchmarks/critical_path_history.jsonl` changes only in
a PR: copy the rounds worth keeping (`tail -n 1 var/logs/perf_gate/history.jsonl >>
benchmarks/critical_path_history.jsonl`) with the estimate-against-actual note. A noisy,
low-confidence, `--only` or integrity-failing run is not recorded at all.

**Integrity failures.** Whatever the times, the gate fails (exit 1) on: a view that did not parse
or an operation with no document, views with no operations, an operation that failed or answered
null / empty (a stale capture), and a shell operation that was not measured (its budget is then
unknown). `perf_bar.toml` lists, with an expiry, the views the capture cannot cover
(`unmeasured_views`: none; the 8 parametrised guide routes are measured with ids picked from the
clone at run time) and the operations that are empty by design (`empty_ok = ["MyScreens"]`: the
benchmark viewer owns no screens; approved by the owner 2026-10-23, expires 2026-12-22); an entry
needs the owner's approval like an exception. Variables the capture cannot hold (a harness run id,
a guide key) are resolved from the clone at run time (`VARIABLE_RESOLVERS` in `fast_bench.py`:
HarnessRun, GuideField, GuideHelpField, GuideSituation, GuideScreener, GuideScreenerEdges,
GuideScreenerCategory); one that finds no real id fails the gate. Other captured values that can
go stale and are not resolved yet: session dates (`date`, `start`, `end`), the option `expiry`,
the instrument `AAPL`, the screener `amihud_illiquid` (a stale one answers empty and fails). Operations the capture never recorded are resolved from the web's own documents
(generated `gql.ts`, or typed by hand in the source: `page_docs.hand_written_documents`) with the
capture's edge id and the first-render values of the trades ledger; one that cannot be resolved
fails the gate. Expired exceptions and an expired list are reported at run time, not in CI.

**Timing, and the 5-minute cap.** The cap applies to the benchmark phase; the snapshot is a
separate step. Expected breakdown: the copy about 3.5-4 minutes [I] on a quiet machine (inferred: fewer files than the 4m17s-5m07s
measured for the whole store, 9m41s under load), the bench at most 5 minutes by
its budget (typically 2.5), the cleanup an instant rename: about 6-9 minutes wall, worst case
10-11. The bench is hard-capped: a watchdog runs it in its own process group and at 300 s kills
the whole group (the bench and its API child), marks the run over-time (exit 4; a finished day,
so no retry loop; nothing is recorded) and the clone is renamed away. The copy has its own cap:
over 10 minutes it is killed, the partial clone discarded the same way (outcome
`snapshot-over-time`, exit 4, one notification, a finished day). Every run appends
`wait_s snapshot_s bench_s cleanup_s total_s` (and `over_time=`) to `var/logs/perf_gate.status`;
`cleanup_s` is the rename, and `trash_delete_s` is added to `status.json` (and
`trash_delete_s.txt`) when the background delete finishes. The history line carries `wait_s` and
`snapshot_s` (`--timings`). The owner is notified when `bench_s` is over 300, `total_s` over 12
minutes, the snapshot is killed, or any view is over the bar.

**Reading a run.** Each run leaves `var/logs/perf_gate/YYYY-MM-DD/` (the last 14 kept; nothing is
written outside `var/logs`) and one line in `var/logs/perf_gate/summary.csv` (date, sha, total_s,
snapshot_s, bench_s, passes, views_over_bar, seconds_above, noisy, notes: the trend is that one
file). Which file answers which question:

| question | file |
|---|---|
| what happened, how long was each phase, why did the bench stop (reps / budget / low-confidence / over-time / guard) | `status.json`, `run.log` |
| why was the snapshot slow | `snapshot.json` (copy seconds, free disk before and after, an ingest during the copy), `load.csv` (load and free disk every 10 s across all phases) |
| why was the run noisy | `procs-start.txt` and `procs-end.txt` (top 10 processes by CPU at the start of the snapshot and the end of the bench), `load.csv` |
| which view or operation is slow, and is it stable | `views.json`, `ops.json`, `samples-partial.json` (every operation's time per pass), `run-meta.json` (passes, budget) |
| why is an operation over the bar | `profiles.md` (`page_profile.py`: cProfile buckets, files opened, top functions, for the 3 slowest operations over the bar, 60 s at most; written only when something is over) |

The desktop notification names the directory. The file count of the snapshot is skipped by
default (counting 750k files costs more than it tells; `PERF_COUNT_FILES=1` counts).

**The launchd entry** (not written or loaded by anything in this repo; the owner installs it like
the nightly's, `docs/hosting.md`): label `com.algotrade.perf-gate`, `ProgramArguments`
`/Users/adarbari/workspace/algo-trading/scripts/ops/perf_gate_nightly.sh`, `StartCalendarInterval`
`Hour=3 Minute=0` plus `StartInterval` 900 (launchd also fires after wake or login), and
`EnvironmentVariables` `ALGOTRADE_PORT_BASE` 15990 (the wrapper exports it itself: a block outside
the worktrees' 10000-14990 and the live API's 8000), and `StandardOutPath` /
`StandardErrorPath` under `var/logs/`. The wrapper copies with `cp -cR` (APFS clonefile);
`PERF_COPY_CMD` replaces it where cp has no `-c` (the tests). Retries every 15 minutes cost nothing
once the day is done: the script exits at the first check.

## An exception

A view may exceed 1 s only through an `[[exception]]` in `benchmarks/perf_bar.toml` naming the
slowest operation, with: the owner's approval (recorded in `docs/decisions/log.md`, linked in the
reason), the **reason** (the named fix and why it is not done), the **date** granted and an
**expiry** date after which the entry no longer counts and the gate says so when it runs (CI
never depends on the date) until it is removed or renewed by the owner. An agent never adds, renews or widens one. There are none today.

## How every view stays under 1 s

1. **Design time**: a new or changed page read states its critical-path budget and its store
   choice (the Choosing a store section of the storage doc, added by the harness PR) in the PR
   description.
2. **PR time**: a CI-safe test that every GraphQL operation the web sends is measured
   (`test_every_web_query_operation_is_measured_so_no_page_ships_unmeasured` in
   `tests/scripts/perf/test_page_docs.py`: the operation is in `benchmarks/api_latency_pages.json`
   or in a view of `benchmarks/api_latency_views.json`; its baseline of nine unmeasured
   operations only shrinks): this is the enforced check. A files-opened-per-request budget test
   for reads that touch stored partitions is PLANNED (a follow-up), not in force.
3. **After merge**: this gate runs nightly on a clone and records the history; any view over 1 s
   fails unless it has a named exception with reason, date, expiry and the owner's approval.
4. **Learning loop**: every round's estimate against actual is appended to
   `benchmarks/critical_path_history.jsonl`, and the PR that moved a number states
   "estimated X, measured Y".
