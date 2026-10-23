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
1 something over, or an operation that failed (a fast failure is no pass); 2 refused (no clone).
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
build the run ends under 300 s; the nightly wrapper's total, with its CoW snapshot (about 5
minutes), is about 10 minutes.

## Read the table

One row per view, slowest first: the view's critical path (its slowest operation, averaged), that
operation, and the verdict: `ok`; `EXCEPTION` (over, but its slowest operation is a named
exception); `OVER` (fails the gate). The last line gives the views over 1 s, the seconds above the
bar and the shell's combined time. Fix the slowest operation, not the view: one operation is on
many views (EdgesPage on every edges list view).

## Read the history

`benchmarks/critical_path_history.jsonl`: one JSON line per recorded run, written **only** by
`--record`: date, git sha, load before and after, a machine note, per view `crit_s` (critical
path), `sum_s` and `slowest_op`, and `totals` (`views_over_1s`, `seconds_above_bar`,
`shell_total_s`). `--history` prints a summary line per run and the critical-path trend of every
view that was ever over 1 s. Compare runs only when the machine notes allow: round 3 (the first
line) ran with the machine 2x slower than round 4; the shas of both seed lines are inferred from
merge times. Fitness tests: `tests/scripts/perf/test_fast_bench.py`.

## The nightly run (a description; the owner installs it)

`scripts/ops/perf_gate_nightly.sh` runs the gate once a night at **03:00 America/Los_Angeles**,
and as soon as possible after 03:00 when the machine was not available then (an ingest holds the
lock, free disk under 12 GB, 1-minute load over 4, or the Mac was asleep).

**Why a clone.** The gate empties every cache before each of about 300 timings: pointed at the
live data or the live API it would load the live site, and the store changes under it (an ingest
mid-copy gives a torn snapshot). It runs on a copy-on-write clone (`cp -cR var/data
/Users/adarbari/perf-clone/data`) of a store no writer touches; the tool itself refuses the real
store, by design. **Cost:** the clone shares every block with the store, so near-zero disk (a
clone only grows by what the bench rewrites, and is deleted afterwards); about 5 minutes for the
copy of 64 GB, 3-15 minutes for the run. The wrapper removes only a path ending in
`/perf-clone/data` that is not the real store.

**Idempotent per local date.** Before 03:00, or when `var/logs/perf_gate.status` already holds a
finished run for today (clean or over the bar), it exits 0 at once. A guard (a writer in `ps`,
disk, load, a writer that started during the copy: the clone is discarded) exits 3 "busy, retry";
a start refused by a guard is not a finished run, so retries continue. Exit codes: 0 done (clean)
or nothing to do; 1 finished with a view over the bar without a named exception (the owner is
notified, as `deploy.sh` does, by a desktop notification), or an operation failed; 2 refused (a
path guard, or the bench refused); 3 busy, retry. Each run appends `date= sha= views_over=
seconds_above= exit= finished=` to `var/logs/perf_gate.status`, keeps the output in
`var/logs/perf_gate.last.log`, and records the history line (`--record`: a noisy or
low-confidence run is not recorded). The history is committed by the next harness PR, never by the agent.

**The launchd entry** (not written or loaded by anything in this repo; the owner installs it like
the nightly's, `docs/hosting.md`): label `com.algotrade.perf-gate`, `ProgramArguments`
`/Users/adarbari/workspace/algo-trading/scripts/ops/perf_gate_nightly.sh`, `StartCalendarInterval`
`Hour=3 Minute=0` plus `StartInterval` 900 (launchd also fires after wake or login), and
`StandardOutPath` / `StandardErrorPath` under `var/logs/`. Retries every 15 minutes cost nothing
once the day is done: the script exits at the first check.

## An exception

A view may exceed 1 s only through an `[[exception]]` in `benchmarks/perf_bar.toml` naming the
slowest operation, with: the owner's approval (recorded in `docs/decisions/log.md`, linked in the
reason), the **reason** (the named fix and why it is not done), the **date** granted and an
**expiry** date after which the entry fails `test_fast_bench.py` until it is removed or renewed by
the owner. An agent never adds, renews or widens one. There are none today.

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
