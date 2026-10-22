# API latency, truly uncached: how to run it

Tool: `scripts/perf/api_latency.py --uncached` (generated outputs: `docs/perf/api-latency-uncached.md`,
`benchmarks/api_latency_uncached.json`). By hand, never in CI, never against the real store
while ingest, compaction or a backfill runs.

## What it measures

- **cold**: first call on a freshly started process, one process per operation.
- **uncached**: neither the response cache nor the loaders' `ResultCache` answers (patched in the
  launched process: `ResponseCache.get` / `get_stale`, `ResultCache.get` / `get_or_compute`), and
  `serving.release_reads` is false in a temporary copy of the config (the serving release is a
  persisted answer too). Median / p95 of 5 calls per operation, none discarded as priming.
- **under load**: the same operation from 4 concurrent clients (5 calls each): the gap to
  *uncached* is GIL / pool contention.
- **Calls per page**: from `benchmarks/api_latency_pages.json` (`make api-latency-capture`):
  requests per operation per route (repeats counted), bytes, share of the page's time, the sum
  and the critical path of cold, uncached and under-load times.
- **Pages**: every route of the web router (`apps/web/src/app/routes`) against the capture, the
  static page -> operation map (`scripts/perf/web_page_ops.py`: an import walk from each route's
  page to the `graphql()` documents, on-load vs uncertain vs interaction-only), operations no
  page sends, pages with no data. The generated doc lists what still memoises under *uncached*.

## Run it against a clone

1. Ask the Backfill session to confirm that nothing ingests or compacts.
2. Clone the store as `docs/perf/release-writer-run.md` does (APFS `cp -c -R` into a directory
   outside the repo and `var/`, same volume); `scripts/perf/release_writer_run.py --dry-run`
   shows the clone rules.
3. `source worktree.env` (the API gets a spare port in `ALGOTRADE_PORT_BASE` + 8 .. + 19).
4. `make api-latency ARGS="--uncached --data-url file:///Users/<you>/perf-clone/data"`
   (`--config-dir DIR` picks another config root, default `./config`; `--only NAME ...` measures a
   subset and writes nothing).

`--data-url` equal to (or inside, or containing) the real local store (`$ALGOTRADE_DATA_URL`, this
checkout's and the main checkout's `var/data`) is refused unless
`--i-know-this-is-the-real-store` is passed; `--uncached` without `--data-url` is refused the same
way. The plain baseline run keeps today's behaviour (real store by default).

## Run it page by page (small memory footprint)

The whole-site run holds one process per operation and a 4 MB answer in several copies; on a
machine with no free memory, run one page at a time.

- `--page ROUTE` (repeatable) measures only the operations of that route (the capture's, else
  the static on-load map's); `--ops NAME ...` (same as `--only`) names operations. A subset run
  writes nothing: it prints the JSON. Example:
  `make api-latency ARGS="--uncached --page /ideas --data-url file://<clone>"`.
- **Memory guard**: before every operation (and between them) the tool reads `sysctl
  vm.swapusage` and stops when free swap is under `--min-free-swap-mb` (default 500): exit code
  3, the results so far printed (profile mode: already in the file). An unreadable value does not
  block.
- **COLD is checked**: each row records the first GraphQL error and an empty-`data` check next to
  the HTTP status; a failure is a FAILED row (`COLD FAILED: <message>`), printed in the progress
  line with the bytes and rows. COLD in the uncached run now uses the uncached mode, so no cache or
  warmer replay can answer it; the row is also flagged `COLD SUSPECT` when its answer is under
  half the bytes of the later uncached calls. Why a fresh process could answer fast (code
  read, not measured): the old COLD pass ran in the default cache mode, where the start-up warmer
  replays the seeded page operations into the response cache, so a call made once `/health`
  answers could be a cache hit or an error answered with status 200 (`errors` in the body), and
  only the status was recorded.
- **`--profile --page ROUTE`** (one page per run, a clone URL required: the real-store refusal
  applies) profiles each operation once, uncached, in process (same patches as the uncached mode,
  warmer off, TestClient on `http://127.0.0.1:8000`) under cProfile and rewrites that page's
  section of `docs/perf/page-profiles.md` after every operation. An unprofiled
  `session { date }` call first builds the schema and store handles. Per operation: profiled wall
  seconds (cProfile inflates pure-Python time: read shares, not absolutes), bytes, rows, stat
  calls, files opened, the bucket split and the top 12 functions of `algotrade` and `pyarrow` by
  cumulative time.
- **Bucket method**: each function's own time (`tottime`) goes to exactly one bucket. A function
  a rule names (filesystem calls, `storage/runs.py from_json` and `local.py _record` / `find`,
  anything in pyarrow, pandas / numpy, GraphQL / JSON encoders) keeps its own time; any other
  function splits its own time over its callers' buckets in proportion to the caller-edge time,
  recursively; unnamed code is "other". The buckets therefore sum to the profile's total and
  nothing is counted twice (summing the cumulative time of nested entry points would).
