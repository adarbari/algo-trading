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
