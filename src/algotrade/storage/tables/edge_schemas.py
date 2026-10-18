"""The schemas of the edge harness's result tables (ADR 0053, 0063, 0064): ``results/edge_eval``,
``results/edge_series``, ``results/winners_study``, ``results/edge_paper``,
``results/edge_legs`` and ``results/edge_trades``, and the ``outcomes/instrument/`` family the
harness scores against. Declared here, registered in ``schemas.KNOWN``."""

from algotrade.storage.tables.spec import TableSpec, fixed, floats, strings

# The edge harness's results (ADR 0053): one row per (edge, variant, horizon, slice), written
# by ``services/evaluation/cross_section/results.py``. Partition ``session_date`` is the range's
# end; ``key`` includes the range start, so re-running a range replaces its rows and another range
# adds its own. ``sessions`` is the number of independent sessions beside every number.
# ``edge_variant`` (a key column; null is read as "main", the edge itself) names the edge's own
# ``[[variants]]`` row; ``iv_source`` / ``licence`` record the implied-vol field an outcome read
# and its catalogue licence; ``reference_rate`` / ``touch_rate`` are filled by the expires_otm
# outcome (ED4a), null until then. ``split_from`` (a key column; null: no split) is the first
# session of the test slice the run used and ``exploratory`` is true when it is not the edge's
# ``frozen_from``: a user's split writes rows under its own key, never over the site's (ED5a).
# Rows written before the column stay under the null key (never rewritten) beside a new run's
# dated one; a reader picks a run by ``run_id`` (ED5c), never by key. ``in_sample`` is true on
# a model screener's slice whose sessions its score was fitted on (ED7b): never evidence.
# ``decile_mean_01`` .. ``decile_mean_10`` (ED8): the mean outcome of each tenth of the ranked
# eligible names, best-ranked first, averaged over the slice's sessions that had deciles; null
# when it had none and in rows written before the columns (never zero). Rows with ``role`` =
# ``random`` (``variant`` = ``random``, ``slice_kind`` = ``draw``, ``slice_value`` the draw's
# number) are the random-pick backtest's draws over the out-of-sample slice: no screener, never a
# candidate for a verdict, read only through ``services/read/evaluation/runs.py``.
# ADR 0064 decision 5: rows with ``slice_kind`` = ``cost`` (``slice_value`` = ``<period>:<bp>``,
# period all / in_sample / frozen / split) carry a return edge's figures at one round-trip cost;
# none for an outcome that is not a return. ``pick_adv_median`` / ``pick_adv_known`` /
# ``pick_adv_low``: the median 20-day dollar volume of the slice's counted picks, how many have
# one and how many are below the site's ``capacity_adv_floor_usd``; null in rows written before
# the columns and on cost and random rows.
EDGE_EVAL = fixed(
    "results/edge_eval",
    "results",
    (
        "edge_id", "user_id", "variant", "horizon_sessions", "slice_kind", "slice_value",
        "range_from",
    ),
    *strings("edge_id", "user_id", "variant", "slice_kind", "slice_value"),
    *strings("role", "config_hash", "run_config_hash", "benchmark"),
    *strings("edge_variant", "iv_source", "licence"),
    "horizon_sessions int64!",
    "range_from date!",
    "range_to date",
    "split_from date",
    "exploratory bool",
    "in_sample bool",
    "projected_exits date[]",  # the next decision sessions' exits, on ``all`` rows (ADR 0064)
    *(f"{n} int64" for n in (
        "decisions_scheduled", "decisions_measured", "decisions_scheduled_oos",
        "decisions_measured_oos", "sessions", "picks", "hits", "eligible", "base_hits",
        "decile_sessions", "trials",
        "unscored", "excluded_score_coverage", "excluded_unclosed", "excluded_missing",
        "excluded_coverage", "delisted", "excluded_unmeasured", "unmeasured_base",
        "pre_snapshot_sessions", "pick_adv_known", "pick_adv_low",
    )),
    *floats(
        "hit_rate", "base_rate", "lift", "mean_excess_picks", "bh_mean", "top_decile_mean",
        "decile_spread", "decile_t", "effect_size", "sharpe", "picks_t", "deflated_sharpe", "pbo",
        "reference_rate", "touch_rate", "pick_adv_median",
        *(f"decile_mean_{i:02d}" for i in range(1, 11)),
    ),
    runs="merge",
    key=(
        "edge_id", "user_id", "edge_variant", "variant", "horizon_sessions", "slice_kind",
        "slice_value", "range_from", "split_from",
    ),
)  # fmt: skip
# The edge harness's per-session series (ADR 0064), framed by ``cross_section/detail/series.py``
# from the run's pooled legs and published with the run's ``edge_eval`` rows (same partition, the
# range's end; read by ``run_id``): one row per (main edge variant, screener or baseline, horizon,
# measured block). ``exit_session`` = S + the horizon (calendar); ``before_split``: the decision
# session is before the run's split (false without one), never re-derived by a reader; ``status``:
# measured | excluded_coverage | lost_input (``lost_table``: an admin cause) | no_picks. Nulls, not
# zeros, where nothing was measured; values are oriented, net of cost, in ``unit`` (excess_return
# | return | cushion | ratio).
EDGE_SERIES = fixed(
    "results/edge_series",
    "results",
    ("edge_id", "user_id", "variant", "horizon_sessions", "range_from", "decision_session"),
    *strings("edge_id", "user_id", "variant", "role", "config_hash", "run_config_hash"),
    *strings("edge_variant", "benchmark", "regime", "status", "lost_table", "unit", "licence"),
    "horizon_sessions int64!",
    "range_from date!",
    "decision_session date!",
    *(f"{n} date" for n in ("range_to", "split_from", "entry_session", "exit_session")),
    "exploratory bool",
    "before_split bool",
    *(f"{n} int64" for n in (
        "block_days", "picks", "pick_hits", "eligible", "base_hits", "excluded_missing",
        "excluded_unmeasured", "excluded_score_coverage", "no_entry_bar", "no_implied_vol",
        "outside_universe", "delisted", "unscored",
    )),
    *floats("pick_mean", "base_mean", *(f"decile_mean_{i:02d}" for i in range(1, 11))),
    runs="merge",
    key=(
        "edge_id", "user_id", "edge_variant", "variant", "horizon_sessions", "range_from",
        "split_from", "decision_session",
    ),
)  # fmt: skip
# The ED6 winners study's results (ADR 0053 amendment 2026-10-09): one run's rows, written by
# ``services/evaluation/discovery/persist.py``. ``row_kind`` is ``block`` (a feature's mean effect
# over the counted grid sessions of one block), ``tell`` (a feature pooled over the blocks: sign,
# agreeing blocks, stable, qualifies, cluster), ``proposal`` (the probit proposer's rank, never a
# verdict) or ``exclusion`` (a feature left out, with ``reason`` and the ``sessions`` it was left
# out of). ``block`` is -1 on every row that is not a block's; ``cluster`` -1 when none. ``blocks``
# is the count of blocks of the run: not independent sessions, neighbouring blocks' outcome windows
# overlap. ``run_id`` is in the key, so every run keeps its own rows; a reader picks a run by
# ``run_id``. Partition ``session_date`` is the run's last grid session. Version 2 (W4,
# 2026-10-09): ``g_WL`` (winners over losers) and ``g_L`` (losers over the winners' controls) on
# block and tell rows, ``variance_like`` on tell rows; ``mean_g`` stays winners over controls.
# The columns are nullable and a run of version 1 reads them as unknown, so older runs stay valid
# but are never compared with version 2 (different controls, a new gate).
WINNERS_STUDY = fixed(
    "results/winners_study",
    "results",
    ("row_kind", "feature", "block"),
    *strings("row_kind", "feature", "reason", "proposed_by"),
    "block int64!",
    *(f"{n} int64" for n in ("sessions", "sign", "agreeing_blocks", "cluster", "rank", "rows",
                             "blocks")),
    *(f"{n} bool" for n in ("halves_agree", "stable", "qualifies", "converged", "passed",
                            "variance_like")),
    *floats("mean_g", "g_WL", "g_L", "coefficient", "gain"),
    runs="merge",
    key=("row_kind", "feature", "block", "run_id"),
)  # fmt: skip
# The forward paper record (ADR 0053 amendment 2026-10-10): one row per (user, edge, signal
# session, name) the nightly ``edge-signals`` job made when it was tonight's pick of an evidenced
# or live edge; ``user_id`` is the RECORD owner (``site`` for a site edge, else the user whose
# edge it is), never a follower. Written by ``services/evaluation/forward/results.py``. Partition
# ``session_date`` = ``signal_session`` (the decision session D), so a later run settles a trade
# by rewriting its row in its own partition: runs merge, the latest known row wins per key and
# ``as_of`` reads the book as it was. ``status`` is ``open`` (window not closed), ``won`` /
# ``lost`` (the edge's own hit; ``excess_return`` the outcome's measure) or ``skipped`` with
# ``reason`` (never a loss, never a zero); ``delisted`` marks a name measured to its last bar;
# ``outcome_hash`` fingerprints the edge's [outcome] at the signal, so a trade is never judged by
# a definition the user edited afterwards. ``buy_session`` is the entry session S,
# ``sell_session`` the window's close, both from the trading calendar.
EDGE_PAPER = fixed(
    "results/edge_paper",
    "results",
    ("user_id", "edge_id", "signal_session", "instrument_id"),
    "instrument_id string!",
    *strings("user_id", "edge_id", "config_hash", "outcome_hash", "screener", "status"),
    *strings("reason"),
    "signal_session date!",
    "buy_session date",
    "sell_session date",
    "horizon_sessions int64",
    "rank int64",
    "delisted bool",
    *floats("excess_return"),
    runs="merge",
    key=("user_id", "edge_id", "signal_session", "instrument_id"),
)  # fmt: skip
# The edge harness's stored legs (ADR 0063): what one evaluation computed per decision session,
# so a later run can reuse it. Written only by ``services/evaluation/cross_section/legs/``;
# partition ``session_date`` is the decision session D (not written every session). ``row_kind``:
# ``leg`` (one per leg key, edge variant, screener, horizon: every ``SessionStat`` field, the
# entry session S, the trial hash, the screen's universe snapshot, the event names, the table a
# lost session lacked, the ``as_of`` its outcome read used and, for a screener from the split on,
# its random draws' sums as float32 lists), ``reads`` (one per (user, edge, D): every partition
# the session read, ``read_*`` lists in step, the store's commit sequence ``inputs_seq`` at its
# first read, the historical-identity counts) and ``outcome`` (one per (D, edge variant,
# horizon): the entry session read, ``outcomes_as_of`` and the outcome partition's commit
# sequence). A key column that does not apply is "" (or 0 for the horizon), never null. Runs
# merge: a leg recomputed by a later run replaces the earlier one under the same key. Leg v2
# (ADR 0064): every pick as ``pick_*`` lists aligned to ``pick_ids`` (``legs/rows.py``) and the
# hits at each level of the site's cost grid (``base_hits_at``, ``pick_hits_at``); null in v1 rows.
EDGE_LEGS = fixed(
    "results/edge_legs",
    "results",
    (
        "user_id", "edge_id", "row_kind", "leg_key", "edge_variant", "variant",
        "horizon_sessions",
    ),
    *strings("user_id", "edge_id", "row_kind", "leg_key", "edge_variant", "variant"),
    *strings("trial_hash", "regime", "lost_table"),
    "horizon_sessions int64!",
    "entry_session date",
    "screen_snapshot date",
    "outcomes_as_of timestamp_utc",
    "pick_values float64[]",
    "deciles float64[]",
    "pick_reference float64[]",
    "event_ids string[]",
    *(f"{n} float64[]" for n in ("pick_scores", "pick_gross", "pick_mdd", "pick_adv", "pick_refs")),
    *(f"{n} int64[]" for n in ("pick_ranks", "pick_flags", "base_hits_at", "pick_hits_at")),
    *(f"{n} string[]" for n in ("pick_ids", "pick_reasons")),
    *(f"{n} int64" for n in (
        "pick_hits", "rest_n", "base_hits", "ranked", "unscored", "excluded_score_coverage",
        "excluded_unclosed", "excluded_missing", "excluded_coverage", "excluded_unmeasured",
        "unmeasured_base", "delisted", "outside_universe", "no_entry_bar", "pick_touches",
        "no_implied_vol", "rand_picks", "rand_eligible", "rand_base_hits", "inputs_seq",
        "outcome_seq", "id_eligible_flag", "id_eligible_proxy", "id_screened_flag",
        "id_screened_proxy",
    )),
    *floats("rest_mean", "rest_m2", "top_decile", "spread"),
    "pre_snapshot bool",
    "implied_stored bool",
    "tombstone bool",  # a leg row that says its key has no leg any more (ADR 0063 amendment 7)
    "value_sums float32[]",
    "hit_sums float32[]",
    "read_table string[]",
    "read_kind string[]",
    "read_digest string[]",
    "read_from date[]",
    "read_to date[]",
    runs="merge",
    key=(
        "user_id", "edge_id", "row_kind", "leg_key", "edge_variant", "variant",
        "horizon_sessions",
    ),
)  # fmt: skip
# The edge trade ledger (ADR 0064 decision 2): one row per pick of the main edge variant's
# implementation screeners at every horizon, excluded picks included (``status`` ``excluded``
# with a public ``excluded_reason``); framed only by ``services/evaluation/cross_section/detail/``
# from the run's v2 legs, written in the run's one publish with its ``edge_eval`` rows and read
# only through ``services/read/evaluation/runs.py``, by ``run_id``. Partition ``session_date`` =
# the run's range end, as ``edge_eval``. ``before_split``: the decision block started before the
# run's split (the harness's own rule, never re-derived from dates). ``score`` is the score at D:
# the value stored for D now (screens read with ``as_of = None``, ADR 0063; a later restatement
# of D's inputs is accepted, ADR 0064), not necessarily as first published. ``value`` is
# oriented and net of the document's cost, ``gross_value`` the stored excess return before cost
# (return outcomes), ``max_drawdown`` the window's dip, ``adv_usd_20d`` the ADV at D (null: not
# stored).
# ``licence`` is the trial's (the strictest of its implied-vol field, screen and universe
# features); ``value_licence``, ``score_licence`` and ``adv_licence`` are the licences of those
# columns (``value`` with ``gross_value``, ``reference`` and ``touch``): a reader redacts a
# per-name value by them, never by column name (ADR 0064 decision 10). Kept 45 days, but for the
# runs the purge spares (``runs.ledger_keep``).
EDGE_TRADES = fixed(
    "results/edge_trades",
    "results",
    (
        "edge_id", "user_id", "variant", "horizon_sessions", "range_from", "decision_session",
        "instrument_id",
    ),
    "instrument_id string!",
    *strings("edge_id", "user_id", "edge_variant", "variant", "role", "config_hash"),
    *strings("run_config_hash", "benchmark", "status", "excluded_reason"),
    *strings("licence", "value_licence", "score_licence", "adv_licence"),
    "horizon_sessions int64!",
    "range_from date!",
    "range_to date",
    "split_from date",
    "decision_session date!",
    "entry_session date",
    "exit_session date",
    "rank int64",
    *(f"{n} bool" for n in ("hit", "delisted", "touch", "before_split", "exploratory")),
    *floats("score", "value", "gross_value", "max_drawdown", "adv_usd_20d", "reference"),
    runs="merge",
    key=(
        "edge_id", "user_id", "edge_variant", "variant", "horizon_sessions", "range_from",
        "split_from", "decision_session", "instrument_id",
    ),
    retention_days=45,  # owner decision D10 (2026-10-10); the purge spares the kept runs
)  # fmt: skip

# Outcomes (ADR 0053): what happened after a start session S, read only by the harness
# (``algotrade.data.outcomes``). One family of fixed tables ``outcomes/instrument/<name>@v<N>``;
# the partition is S. Each night T writes the windows it closes (S = T - h sessions), so one
# partition receives one run per horizon on different nights: runs merge, the latest run's row
# winning per (instrument, horizon, benchmark). ``knowledge_ts`` is the write time, never before
# the close of ``window_end`` (the writer refuses a window that has not closed).
# v2 (ADR 0061): a window that needs a bar the ``bar-quality`` task flagged is UNMEASURED, a row
# with a reason and no returns, instead of a return computed over a bad price.
OUTCOMES_PREFIX = "outcomes/instrument/"
FORWARD_RETURNS = f"{OUTCOMES_PREFIX}forward_returns@v2"  # the outcomes task's table
OUTCOME_STATUSES = frozenset({"COMPLETE", "DELISTED", "UNMEASURED"})
UNMEASURED = "UNMEASURED"
_OUTCOME_TYPES = (
    "instrument_id string!",
    "ts timestamp_utc!",  # the close of S
    "horizon_sessions int64!",
    "window_end date!",  # T: the h-th exchange session after S
    "benchmark string!",  # the benchmark ticker of fwd_excess_return
    "fwd_return float64",  # close(T) / close(S) - 1, split-adjusted, price return; null: UNMEASURED
    "fwd_excess_return float64",  # fwd_return - the benchmark's (null: no benchmark bar)
    "fwd_max_return float64",  # max high over (S, T] / close(S) - 1 (favourable); null: UNMEASURED
    "fwd_max_drawdown float64",  # 1 - min low over (S, T] / close(S), >= 0; null: UNMEASURED
    "fwd_realised_vol float64",  # annualised stdev of daily log close returns over (S, T]
    "outcome_status string!",  # OUTCOME_STATUSES; DELISTED: measured to the last bar
    "outcome_reason string",  # UNMEASURED only: why (BAD_BAR: a flagged bar in S..T, ADR 0061)
)


def outcomes_spec(table: str) -> TableSpec:
    """The spec of one ``outcomes/instrument/`` table (they share one schema)."""
    return fixed(
        table, "outcome", ("instrument_id", "ts", "horizon_sessions", "window_end", "benchmark"),
        *_OUTCOME_TYPES, runs="merge", key=("instrument_id", "horizon_sessions", "benchmark"),
    )  # fmt: skip
