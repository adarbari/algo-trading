# ADR 0081: Stored edge picks: what each site edge took, written nightly, read by the screener page

**Amended by [0088](0088-setups-as-positions-and-rules.md)** (proposed, 2026-11-01): `@named` picks, status `gate_closed`, `pick_sides` / `pick_weights`, short and book picks shown (decision 4).

**Status:** accepted (2026-10-23; the owner chose "store each edge's picks nightly and read them"
over re-running the selection on every page request). Extends
[0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (the edge harness's pick rule) and
[0036](0036-session-strictness-for-reads.md) (one session per read); adds one writer to
[0005](0005-ingestion-is-the-only-writer.md).

## Context
The screener results page says which edges a pick "counts toward" (`ScreenResult.countsToward`,
PR #886). It decided that from the screener run's own ranking: QUALIFIED and within the edge's
`top_k` among the run's qualified rows. That is not the harness's rule. The harness
(`cross_section/picks.py` `screen_variant`, then `measuring.py`) takes the screener's qualified
names **that are in the edge's universe** (and, for an event schedule, in the event's names) and
keeps the first `top_k`. When the edge's universe is narrower than the screener's scan (an ETF
ranks second in the screener, the edge is common stocks only) every place after it shifts and the
page says the wrong thing. Schedule and side were not applied either (served as `unjudged`).
Re-running the selection per request would put a screen, a universe selection and an event read in
a page read.

## Decision
1. **A table, written nightly.** `results/edge_picks`: one row per (user, edge, screener, session),
   partition `session_date` = the decision session D, `runs = "merge"`, key `(user_id, edge_id,
   screener)`. Columns: `status` (`picked`: the edge decides at D, `pick_ids` lists its picks;
   `not_decision_day`: its schedule does not fire at D; `unjudged`: its outcome side is not
   long; `skipped`: the data to decide was missing, `reason` says what), `reason`, `pick_ids`
   (`string[]`, place 1 first), `top_k`, `config_hash` (the screener's resolved config) and the
   point-in-time columns of ADR 0007 (`knowledge_ts` = the write instant, never back-dated;
   `source` = `edge-picks`; `run_id`). Owner of the table: the ingestion task
   `apps/ingestion/algotrade_ingestion/tasks/edges/picks.py`; framed by
   `services/evaluation/edge_picks/`. The reader is `services/read/evaluation/pick_edges.py`, no
   other module names the table (a fitness test).
2. **The harness's own rule, not a copy.** `picks.long_picks(edge, qualified, pickable)` is the
   rule (the qualified names in order, kept when pickable, the first `top_k`); the harness's
   `measuring.py`, the paper record's `forward/signals.py` and this step all call it. The run and
   the universe are the harness's too: `screen_variant` and `eligible(edge_universe)` at D, the
   event names through `names_for`.
3. **Which edges.** Every **site** edge with a screener, whatever its status (the page lists
   retired and rejected edges too). A user's own edge is not stored (a viewer's own edges read
   `not_stored`); this can be added per owner later without a schema change (`user_id` is in the
   key). One run per distinct (screener config, session) is shared by every edge listing it.
4. **Long leg only.** A `short` or `long_short` edge ranks shortable names by its own score and
   liquidity floor (`measuring._side_picks`), which is not "the screener's pick". Those rows are
   `unjudged` with a reason; the page keeps saying so.
5. **Decision days.** A row says `picked` only when the schedule fires at D: `every_session` every
   session (the harness spaces the decisions a horizon apart to keep its statistic independent;
   the stored picks are what the edge would take that session, so the page says "would take",
   never "has earned"), `month_end` and `calendar:<window>` through
   `sessions.decision_sessions` over the sessions around D, `on_event:<class>` through
   `forward.signals.legs_between` (the harness's own legs, event names read at D). Any other
   session is `not_decision_day`: a row, so the page can tell it from a session never stored.
6. **Resumable, idempotent, accepted.** The task `edge-picks` (`--date`, `--from/--to`,
   `--edge`) skips the (edge, screener, session) keys already decided (a `skipped` gap is decided again and its row replaces it; an edge document edited after a session was stored does not rewrite that session: re-run with `--edge` after deleting nothing is not supported, the stored row is what the edge took then), writes every new row of a
   session in one publish, counts one edge's failure (a `skipped` row with the reason, the run
   PARTIAL) and never stops the others. It is a nightly step after `screens`, optional
   (ADR 0039/0055: a gap warns, never holds the session), run for every session of a catch-up.
   Its acceptance check fails when a site edge with a screener has no row for the session.
7. **The read.** `load_pick_edges` reads the stored rows of `ctx.session` only (ADR 0036): a
   session with no stored partition, or an edge with no row in it, is `not_stored` (an UNKNOWN
   with its reason, never an older partition). Codes: `counts` (the row is in `pick_ids`; `place`
   its index + 1), `not_counted` (decision day, not among the picks), `not_a_decision_day`,
   `unjudged`, `not_stored`; a row the regime gate PAUSED is still `paused` (not counted), and one
   whose rank is withheld by a licence is `withheld`. The screener's own rank is no longer used.

## Consequences
- The page and the harness agree by construction (one rule, one test on a fixture whose edge
  universe is narrower than the screener's scan).
- One more optional nightly step: its cost is one screen per distinct screener (cached by config
  hash) plus one universe selection per distinct edge universe; the run's stats record the
  seconds so the budget is visible.
- The stored picks are derived data (the screens and the universe selection can recompute them):
  losing the table is a re-run of the task, never a loss.
