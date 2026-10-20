# Outcomes compaction: measurement (2026-10-19, read-only)

20 partitions of `outcomes/instrument/forward_returns@v2` evenly spread over 2010-01-04..2026-10-15
(scripts: `outcomes_measure.py`, `outcomes_e2.py` in the side-session notes; the store was only read, at
`nice 19`). Every file is already zstd with one row group.

| | files | bytes | rows |
|---|---|---|---|
| Now | 505 (17-32 per old partition) | 114.9 MB | 2,303,934 |
| Runs whose every row a later run rewrites | 279 | 60.7 MB (53 %) | |
| Latest row per key (live) | | | 1,092,675 (47 %) |
| (a) merge files only, zstd | 20 | 53.1 MB (46 %) | |
| (b) drop superseded rows, zstd (C1) | 20 | 40.5 MB (35 %) | |
| (c) C1 sorted by instrument, zstd 3 / 9 | 20 | 38.2 / 37.7 MB (33 % / 33 %) | |
| **E2 (ADR 0078, value-exact, delta runs)** | **355** | **54.9 MB (48 %)** | 1,093,745 |

Why the rewrites exist: the nightly recomputes `RECHECK + 1` = 11 window ends and each backfill
re-runs a T; the rewrites are value-identical, so E2 keeps each value once, from its first run.
Extrapolated to 24 GB: C1 about 8 GB, E2 about 11.5 GB.
