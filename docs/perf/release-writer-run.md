# Release reads under a writer: the decision 24 measurement

Tool: `scripts/perf/release_writer_run.py` (ADR 0077 amendment, decision 24). It measures the
serving release on a copy-on-write CLONE of the store, never the real one, never in CI.

## Before you run

- Ask the Backfill session to confirm that no ingest or compaction runs; only then pass
  `--confirm-paused`.
- `source worktree.env` (it sets `ALGOTRADE_PORT_BASE`; the API gets base + 7).
- `--dest` must be a new directory on the same APFS volume as the store, outside the repo and
  `var/` (the script refuses otherwise), with at least `--min-free-gb` (20) free.

## Run

```
python scripts/perf/release_writer_run.py --dest /Users/<you>/perf-clone --dry-run   # the plan, read-only guards
python scripts/perf/release_writer_run.py --dest /Users/<you>/perf-clone --confirm-paused
```

Steps: clone the data dir (`cp -c -R`), `algotrade-ingest serve-release --rebuild` on the clone,
`algotrade-api` on the clone (auth off), `load.py realistic --writer-store <clone>
--publish-every 120` with `serving.release_reads` true then false (config copies in `--dest`),
then `load.py cold` (one user level, at most 300 s) straight after an API restart. Every child runs with its cwd and `--out` in `--dest/results`, so nothing is written to `var/`; the main checkout is refused as a `--dest` too. The API is always stopped at the end;
nothing is deleted, remove `--dest` yourself.

## Reading the result

`--dest/results/summary.md` and `summary.json` (raw reports in `reports.json`, API log in
`api.log`). Decision 24 triggers, any of which fails the run: page p95 > 2.5 s, /health p99
>= 250 ms, cold p95 in the first 5 minutes after a restart > 1 s. Exit code 0 pass, 1 fail,
2 refused.
