# ADR 0064: Edge evidence detail: a per-session series and a trade ledger

**Status:** accepted (2026-10-10; owner decisions on the Edge page redesign, ED9: the
architecture plan's recommendations Q1-Q8 and D10-D12). Amends
[0063](0063-incremental-edge-evaluation.md) (leg v2), [0053](0053-edges-hypotheses-outcomes-and-one-harness.md)
(the `[published]` table of an edge document), [0037](0037-domain-read-model-served-by-graphql.md)
(one more REST file GET) and [0005](0005-ingestion-is-the-only-writer.md) (two more job-written
result tables). Extends [0028](0028-ibkr-enrichment-source.md) (licence of a trial) and
[0056](0056-role-scoped-causes.md) (public kinds, admin causes). Plan: [edges-plan.md](../edges-plan.md) ED9.

## Context
The edge page shows one verdict and its slice rows (`results/edge_eval`: all, year, regime,
frozen, random). The redesign adds an evidence curve, drawdown and volatility, rolling starts,
a monthly map, a trade ledger, cost sensitivity, capacity, decay against the published figure,
a haircut Sharpe, a projected date for the next verdict criterion and a live-vs-backtest state.
None of these can be derived in the browser (ADR 0038), and most need per-session or per-pick
facts that no table holds: a leg (`SessionStat`, ADR 0063) keeps the picks' net values and
counts, not their ids, ranks, scores, exclusion reasons, gross values, dips or liquidity.

## Decision
1. **`results/edge_series`** (per-session series). Run-scoped like `edge_eval`: partition
   `session_date` = the run's range end, `runs = "merge"`, read by `run_id`; key `(edge_id,
   user_id, edge_variant, variant, horizon_sessions, range_from, split_from, decision_session)`.
   One row per (main edge variant, implementation screener or baseline, horizon, decision
   session D or event block); no `[[variants]]`, no random draws. Columns: `role`, config hashes,
   `decision_session`, `entry_session`, `exit_session` (S + h sessions, from the calendar: the
   curve's x, so no point shows a return before it closed), `block_days`, `before_split` (the decision
   session is before the run's split; written by the harness, never re-derived from dates by a
   reader; not `edge_eval.in_sample`, which means a scorer was fitted on the slice),
   `exploratory`, `regime`, `status` (`measured` | `excluded_coverage` | `lost_input` |
   `no_picks`; `lost_table` only as an admin cause), pick and base counts and means (oriented, net
   of the document's cost), exclusions, deciles, `unit` (`excess_return` | `return` | `cushion` |
   `ratio`), `licence`, `benchmark`, and the ADR 0007 columns. Framed from the run's pooled legs:
   no leg change, no re-run (the next nightly incremental run writes it). Kept forever (small).
2. **`results/edge_trades`** (the ledger). Same scheme, key plus `instrument_id`. One row per
   pick of the main edge variant's implementation screeners at every horizon, excluded picks
   included with a public `excluded_reason` (`UNMEASURED`, `MISSING_VALUE`, `NO_ENTRY_BAR`,
   `NO_IMPLIED_VOL`, `MISSING_DRAWDOWN`); eligible non-picks are never listed. Columns: entry and
   exit sessions, `rank`, `score` ("score at D": the value stored for D now, screens read with
   `as_of = None`), `value` (oriented, net), `gross_value` (return outcomes only), `hit`,
   `status` (`won` | `lost` | `excluded`), `delisted`, `before_split`, `max_drawdown` (the
   within-window dip), `adv_usd_20d` at D (null = not stored, never 0), `reference`, `touch`,
   `licence`. **Retention 45 days** (`TableSpec.retention_days`), applied by the ingestion
   maintenance `purge` task with a keep-list function owned by the run reader's owner: it spares
   the partitions of the canonical run (the latest non-exploratory official run of each edge), the
   latest run per edge and user, and every run cited by an edge's `[evidence] run_id`. The run
   record states the ledger row count it wrote: rows absent under a nonzero count read
   `Unknown(PRUNED)` ("re-run the backtest"), a run with no count (older) `Unknown(NOT_STORED)`.
3. **One writer, one reader.** Both tables are framed only in
   `services/evaluation/cross_section/detail/` and written by the `edge-eval` job through
   `ResultWriter` (the job, not an ingestion task: ADR 0063 amendment 5), inside the run's one
   `writer.publishing` block with its `edge_eval` rows, legs and run record (ADR 0022): a crash
   leaves no series or ledger without its run. They are read only through
   `services/read/evaluation/runs.py` (`load_run_series`, `load_run_trades`); for a hidden copy
   (`oos_hidden`) they keep only `before_split` rows (fitness test, one test per surface).
   `load_run_rows` changes too: today it drops every slice kind but the in-sample ones for a
   hidden run; it keeps the `cost` rows whose `slice_value` starts `in_sample:` as well.
   Storage gains `TableReader.read_run(table, session_date, run_id)` on every backend
   (contract-tested): one committed run's rows of a partition without reading the others'.
4. **Leg v2 (amends 0063; `LEG_VERSION` 2).** A leg adds, aligned to `pick_ids`, `pick_ranks`,
   `pick_scores`, `pick_reasons` ("" when counted), `pick_gross`, `pick_mdd`, `pick_adv` (null
   elements, never 0), and `base_hits_at` / `pick_hits_at` per cost-grid level. `adv_usd_20d` at D
   is read through the recording reader (0063 decision 2), so a restated liquidity partition
   invalidates the leg. The cost grid joins the leg key, like `draws`. The key seeds the random
   draws (0063 decision 6), so the bump redraws every random-pick backtest once ("beats N% of
   random picks" moves slightly; the verdict reads only the latest run). One detached full re-run
   of every site edge follows; the re-run script takes the existing `claim_edge_eval` lock, so it
   and the nightly `edge-eval` step serialise per edge (no pause; concurrent runs of one edge
   would race on tombstones).
5. **Cost and capacity on `edge_eval`.** Cost rows `slice_kind = cost`, `slice_value =
   "<period>:<bp>"` (period all / in_sample / frozen) over the document's `cost_bps` plus the site
   grid `[edge_costs] levels_bps = [0, 15, 30, 50]` (`config/site/verdict.toml`); not written when
   the outcome is not a return (`Unknown(NOT_A_COST_OUTCOME)`); break-even = gross mean excess x
   1e4 (exact: cost is linear in the mean); the decile spread is cost-invariant and stated so.
   Capacity columns `pick_adv_median`, `pick_adv_known`, `pick_adv_low` (below the site floor
   `capacity_adv_floor_usd`, applied at the statistics stage, not in the leg key).
6. **`[published]` in an edge document (amends 0053).** Optional: `measure` (`mean_excess` |
   `decile_spread` | `lift_pts`), `value`, `horizon_sessions` (one of the edge's), `sample`
   (years), `source` (index into `[[sources]]`); validated, inherited by copies. Decay compares
   published, in-sample, out-of-sample and live; a statistic not measurable live is
   `Unknown(NOT_MEASURED_LIVE)`, a horizon mismatch `Unknown(NOT_COMPARABLE)`.
7. **Projected date.** Computed at run time by the harness, which owns schedule arithmetic: for a
   calendar schedule it writes, per (variant, horizon) on the run's `slice_kind = all` rows,
   `projected_exits` (the exit sessions of the schedule's next N decision sessions, count-based,
   not a calendar window: `vrp_short_premium`'s 40th out-of-sample exit is about 2029 at 21
   sessions and 2031 at 31) and the scheduled and measured decision-session counts over the run's
   out-of-sample side. N = ceil(max threshold / 0.25), the max threshold being the largest of
   `VerdictSettings` `min_oos_trades`, `works_oos_trades`, `works_trades` at run time. The read
   model's outlook, for count criteria only (`trades`, `works_trades`), scales by the observed fill
   ratio (measured / scheduled on the out-of-sample side, the whole run's when there is no
   out-of-sample history, floored at 0.25): the expected exit is the ceil(remaining / ratio)-th
   stored exit. Thresholds stay in `verdict.toml`, so a changed threshold never stales a stored
   value; one past the stored list reads the projection state `BEYOND_PROJECTION` until the next
   run. An event schedule (`on_event:`) cannot be projected: the honest state `UNPROJECTABLE`
   (owner-delegated decision); a hidden copy `Unknown(OOS_HIDDEN)`; a non-count criterion has
   none. Each state has its Guide term. Labelled an estimate; never an input to a verdict.
8. **Haircut Sharpe.** Robustness shows the Harvey-Liu haircut (Holm, M = the trial log's trials;
   the Bonferroni bound when the peers' t-statistics are not stored) beside the trial count, from
   stored `sharpe`, `sessions`, `trials`; the deflated Sharpe stays the verdict criterion.
9. **Live state.** `EdgeDesk.liveStates` reads `results/edge_paper` (latest row per key with
   `knowledge_ts` at or before the resolved session's cutoff, ADR 0062; settled trades only) for
   the list badge, the header, an Ideas banner and one line in the nightly `edge-signals` run
   record when the live record falls below the backtest's usual range. No push, no email. The
   evidence curve's live stroke reads the same stored paper rows through `data/paper` (read-only,
   never re-derived from today's document) under the same out-of-sample rules as the backtest.
10. **Licence of a trial.** The harness writes the most restrictive licence of the IV field, the
    screen's features and the universe's features on `edge_eval`, `edge_series` and
    `edge_trades`, and records each ledger column's licence. The licence holder is a user whose
    entry in `config/site/users.toml` lists it (`licences = ["personal"]` on `UsersSettings`; the
    owner only today). To anyone else, in the ledger and the CSV, every per-name column whose
    recorded licence is personal is `Unknown(LICENCE)`, decided by that recorded licence, never by
    column name: the oriented outcome value and IV / strike when the outcome's `iv_field` is
    personal, the score and inputs when the screen reads a personal feature. Counts, dates, names
    and won / lost stay; aggregate statistics are shown to all.
11. **CSV route (amends 0037).** `GET /files/edges/{edge_id}/trades.csv?variant&horizon&period`,
    a file, not a page read: same loader as `Query.edgeTrades` (same redaction, licence and
    `oos_hidden`), streamed. `architecture/rest_allowlist.toml` entry with `keep = true`;
    `max_get_routes` goes from 4 to 5. Precedent: ADR 0044's file GET.

### Amendment (2026-10-11): the session's cutoff
`Session.cutoff` (`services/read/session.py`, resolved once in `resolve_session`) is the finish
time of the session's FIRST completed nightly: the first `nightly` run record of the session that
`published()` accepts (the test `done_sessions` uses), by `finished_at`. A session with no completed
nightly has no cutoff. `data/paper` reads `edge_paper` as of the cutoff (latest row per key with
`knowledge_ts` at or before it), so a settlement a later night recorded never changes an earlier
session's state; it bounds every paper read, the desk's buys and sells too (an intended behaviour
change). With no cutoff the live state is not judged: `EdgeLiveState.state = not_settled`
("not yet settled for this session", Guide term `live_state`), and no later settlement is read for
it. The nightly `edge-signals` step runs before its session completes, so it reads as of now.

## Alternatives rejected
- **Series as `edge_eval` row kinds** (`slice_kind = session`): every verdict and list read
  would load the whole run's rows (about 150k for `vrp_short_premium` on every page).
- **A read loader over `results/edge_legs`**: the reader would re-implement leg keys, tombstones
  and reuse (harness knowledge leaking into `services/read`) and break 0063's fitness test that
  only `cross_section` reads legs.
- **A ledger partitioned by D with delta writes**: tombstones in a reader and about 4,000
  partitions read per page.
- **Projection from the read model alone** (the plan's draft): the read model cannot import the
  schedule code and would re-implement it; the stored list keeps one owner.

## Consequences
- Two more result tables (about 0.7M ledger rows a night for the site; series small), one storage
  Protocol method, two folders (`cross_section/detail/`, `services/read/edge_evidence/`), two
  responsibilities (`edge-evaluation-detail`, `edge-evidence-read`).
- Older runs have no series, ledger, cost or capacity rows: `Unknown(NOT_STORED)` until re-run.
- Leg v2 costs one full re-run (about 3-4 h for the site edges) and one redraw of random picks.
- The ledger of a run older than 45 days is gone unless it is canonical, the latest for its edge
  and user, or cited.
- REST gains one GET (shrink-only list raised by this amendment only).
