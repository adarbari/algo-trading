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
`api_latency.py`); never in CI (it needs the clone; a nightly or post-merge run is the next step).

    make api-latency-fast ARGS="--data-url file://<clone>/data"            # judge: exit 1 over the bar
    make api-latency-fast ARGS="--data-url file://<clone>/data --record"   # and append to the history
    make api-latency-fast ARGS="--data-url file://<clone>/data --ratio-mode"  # busy machine
    make api-latency-fast ARGS=--history                                   # the trend, no measuring

One API process (warmer off, `release_reads=false`), a patched endpoint empties every cache before
each timing, each distinct operation is timed 5 times and averaged (3 when over 10 s), the 1-minute
load is gated at 4. A run takes minutes. The views and their documents come from
`benchmarks/api_latency_views.json`; its `captured` entries are filled by
`make api-latency-views-capture` on the clone (re-crawl when `make api-latency-docs` says the
documents drifted); a view with no captured document is listed as not measured.
`--ratio-mode` divides every time by the shell's slowdown against the last recorded run (the shell
is untouched by the work judged), never below 1: use it when `uptime` shows the machine busy.

## Read the history

`benchmarks/critical_path_history.jsonl`: one JSON line per recorded run, written **only** by
`--record`: date, git sha, load before and after, a machine note, per view `crit_s` (critical
path), `sum_s` and `slowest_op`, and `totals` (`views_over_1s`, `seconds_above_bar`,
`shell_total_s`). `--history` prints a summary line per run and the critical-path trend of every
view that was ever over 1 s. Compare runs only when the machine notes allow: round 3 (the first
line) ran with the machine 2x slower than round 4; the shas of both seed lines are inferred from
merge times. Fitness tests: `tests/scripts/perf/test_fast_bench.py`.
