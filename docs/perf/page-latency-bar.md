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
load is gated at 4. A run takes minutes. The views and their documents come from
`benchmarks/api_latency_views.json`; its `captured` entries are filled by
`make api-latency-views-capture` on the clone (re-crawl when `make api-latency-docs` says the
documents drifted); a view with no captured document is listed as not measured.
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

A launchd agent, `com.algotrade.perf-bar`, started after the nightly workflow completes (so the
clone is refreshed from the real store first, `cp -c` on the same volume), runs

    make api-latency-fast ARGS="--data-url file://<clone>/data --record --out <var/logs dir>"

on the clone in the main checkout's `.venv` with the same guards (load, disk, swap: a refused or
noisy night records nothing and is not a pass), and writes the exit code and the table to
`var/logs/`. The history line is committed by the next harness PR, never by the agent. Nothing in
this repo installs or loads it; `scripts/` writes no plist for it until the owner asks.

## An exception

A view may exceed 1 s only through an `[[exception]]` in `benchmarks/perf_bar.toml` naming the
slowest operation, with: the owner's approval (recorded in `docs/decisions/log.md`, linked in the
reason), the **reason** (the named fix and why it is not done), the **date** granted and an
**expiry** date after which the entry fails `test_fast_bench.py` until it is removed or renewed by
the owner. An agent never adds, renews or widens one. There are none today.

## How every view stays under 1 s

1. **Design time**: a new or changed page read states its critical-path budget and its store
   choice (`docs/data/storage.md`) in the PR description.
2. **PR time**: a CI-safe test that every GraphQL operation the web sends is measured
   (`test_every_web_query_operation_is_measured_so_no_page_ships_unmeasured` in
   `tests/scripts/perf/test_page_docs.py`: the operation is in `benchmarks/api_latency_pages.json`
   or in a view of `benchmarks/api_latency_views.json`; its baseline of nine unmeasured
   operations only shrinks), and a files-opened-per-request budget test for reads that touch
   stored partitions (not written yet: the first read PR that opens partitions adds it).
3. **After merge**: this gate runs nightly on a clone and records the history; any view over 1 s
   fails unless it has a named exception with reason, date, expiry and the owner's approval.
4. **Learning loop**: every round's estimate against actual is appended to
   `benchmarks/critical_path_history.jsonl`, and the PR that moved a number states
   "estimated X, measured Y".
