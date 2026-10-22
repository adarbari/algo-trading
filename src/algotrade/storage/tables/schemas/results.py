"""Result, usage and feedback table schemas: LLM usage, Describe-it feedback and the rule-screen
result tables, with the display-column / group row predicates.
"""

from algotrade.storage.tables.spec import (
    fixed,
    floats,
    strings,
)

# The text-model usage log (ADR 0058, the API's fifth write): one row per provider
# attempt of a call (the failed and the budget-skipped ones too), one partition per exchange
# calendar date of the call. Runs merge (each is a batch of attempts; all kept). Tokens, cost
# and ``fell_back_from`` are null when unknown or not applicable, never 0: ``cost_basis`` says
# where ``cost_usd`` came from (``price`` tokens x the model's [[price]], ``reported`` a
# subscription's notional total, ``bound`` the upper bound reserved when the cost is unknown or
# the attempt failed, ``free`` 0 for a free provider, ``unknown`` null: a skipped attempt or a
# ``rejected`` one). A failure also carries ``error``, ``stage`` (``provider`` / ``answer``), the
# prompt (``sentence``, clipped), the raw ``answer`` (clipped) and ``prompt_chars``: null on
# every other row and on partitions written before they existed. Metering (ADR 0058 amended
# 2026-10-11): ``input_tokens`` is the regular (uncached) input as reported, ``cache_read_tokens``
# / ``cache_write_tokens`` the cached prompt (null: not reported), ``call_id`` ties the attempts
# of one call and its ``rejected`` row, ``prompt_version`` and ``call_stage`` (``first`` /
# ``repair`` / ``escalate``) are the caller's tags; null on older partitions. Written
# only through ``UsageWriter`` (``usage/*``); read across a date range by ``data.usage``.
USAGE_LLM_CALLS = fixed(
    "usage/llm_calls",
    "usage",
    ("ts", "provider", "use_case", "outcome"),
    "ts timestamp_utc!",
    "provider string!",
    "model string!",
    "use_case string!",
    "user string",
    "input_tokens int64",
    "output_tokens int64",
    "latency_s float64!",
    "cost_usd float64",
    "cost_basis string!",
    "outcome string!",
    "fell_back_from string",
    "error string",
    "stage string",
    "sentence string",
    "answer string",
    "prompt_chars int64",
    "cache_read_tokens int64",
    "cache_write_tokens int64",
    "call_id string",
    "prompt_version string",
    "call_stage string",
    runs="merge",
    key=("ts", "provider", "use_case", "user", "outcome"),
)

# The Describe-it feedback events (ADR 0066, the API's sixth write): one row per event of a
# drafting session (``draft_requested``, ``draft_returned``, ``choice_made``,
# ``formula_accepted``, ``formula_skipped``, ``draft_saved``, ``screen_finalised``,
# ``edge_revised``), one partition per exchange calendar date of the event. Runs merge (each is
# a batch of events; all kept). ``draft_session_id`` ties the events of one draft to the screen
# saved from it; ``call_ids`` is a comma-delimited list of ``usage/llm_calls.call_id``;
# ``draft_hash`` / ``saved_hash`` are content hashes (the draft the model returned, the document
# saved); ``sentence`` is the trader's text (<= 1,000 characters, personal data: ADR 0066 has the
# retention) and ``payload`` a JSON object (the server-side diff of a save, the criteria in
# force: ``current_criteria`` / ``draft_criteria`` / ``saved_criteria``, each <= 8,000 characters;
# the choices); ``seq`` is the 1-based ordinal of the draft request in its session.
# Only the columns that are not the event's identity are nullable. Written only through
# ``FeedbackWriter`` (``feedback/*``); read across a date range by ``data.feedback``.
FEEDBACK_DRAFTING_EVENTS = fixed(
    "feedback/drafting_events",
    "feedback",
    ("event_id", "ts", "event"),
    "event_id string!",
    "draft_session_id string!",
    "ts timestamp_utc!",
    "user string!",
    "doc_kind string!",
    "doc_id string!",
    "event string!",
    "call_ids string",
    "catalogue_version string",
    "prompt_version string",
    "draft_hash string",
    "saved_hash string",
    "sentence string",
    "payload string",
    "seq int64",
    runs="merge",
    key=("draft_session_id", "event_id", "event"),
)

# The missing-feature requests of Describe it (ADR 0066 amendment 2026-10-11): one row per
# (user, backlog key or new slug, exchange day), the span of the sentence the request covers
# (never the sentence). ``ref`` is the key or the slug (the identity); ``key`` is set for a backlog
# item, ``new_slug`` for a request the backlog does not know. Written through ``FeedbackWriter``,
# read across a date range by ``data.feedback``; the viewer-scoped loader decides who sees what.
FEEDBACK_FEATURE_REQUESTS = fixed(
    "feedback/feature_requests",
    "feedback",
    ("ts", "user", "ref"),
    "ts timestamp_utc!",
    "user string!",
    "ref string!",
    "key string",
    "new_slug string",
    "feasibility string",
    "span string",
    "closest string",
    "call_id string",
    "draft_session_id string",
    runs="merge",
    key=("user", "ref", "session_date"),
)

# Rule screens (ADR 0029): one fixed schema for every rule-screen config, so pages and Ideas
# query across screens. Many configs and users share a session's partition, so runs merge
# on (user, config, instrument): readers take a config's rows of its latest run (``run_id``
# from the run record), since a later run never removes rows an earlier one wrote.
RULE_SCREEN = fixed(
    "results/rule_screen",
    "results",
    ("instrument_id", "user_id", "config_id", "config_hash", "decision", "rank"),
    "instrument_id string!",
    "user_id string!",
    "config_id string!",
    "config_version int64",
    "config_hash string!",
    "decision string!",
    "score float64",
    "rank int64!",
    "tie_break float64",
    *strings("flags", "reasons", "failed", "near_missed", "missing"),
    "regime string",  # the session's regime label (ADR 0049); null: gate off or unknown
    "size_multiplier float64",  # the regime's size for the screener; null in runs before it
    runs="merge",
    key=("user_id", "config_id", "instrument_id"),
    whole_per_group=True,  # a run's file is its config's whole result (ADR 0029 amendment)
)

# One row per (instrument, criterion), per display column (``mode = "column"``, ``outcome =
# "INFO"``) and per criterion group (``mode = "group"``, ADR 0071: ``field`` the kind, the
# verdict's outcome and penalty, ``value_str`` the deciding member's id): the value, PASS / NEAR /
# FAIL / MISSING, distance and penalty. ``group_id`` is the row's parent group (null: a gate, or
# a partition from before groups).
DISPLAY_COLUMN_MODE = "column"

GROUP_MODE = "group"


def is_display_column(mode: object) -> bool:
    """Whether a ``results/rule_screen_values`` row of ``mode`` is one of the screen's display
    columns (``[columns]``) rather than a criterion's outcome: the one predicate its writer
    and its readers share."""
    return mode == DISPLAY_COLUMN_MODE


def is_group_row(mode: object) -> bool:
    """Whether a ``results/rule_screen_values`` row of ``mode`` is a criterion group's verdict
    (ADR 0071), not a criterion's outcome: a reader of criteria skips it as it skips display
    columns (``is_display_column``)."""
    return mode == GROUP_MODE


def is_criterion_row(mode: object) -> bool:
    """Whether a row of ``mode`` is a criterion's outcome (neither a display column nor a
    group): what every criterion reader keeps."""
    return not (is_display_column(mode) or is_group_row(mode))


RULE_SCREEN_VALUES = fixed(
    "results/rule_screen_values",
    "results",
    ("instrument_id", "user_id", "config_id", "criterion_id", "field", "mode", "outcome"),
    "instrument_id string!",
    "user_id string!",
    "config_id string!",
    "criterion_id string!",
    "field string!",
    "mode string!",
    "value_num float64",
    "value_str string",
    "outcome string!",
    *floats("distance", "normalised", "penalty"),
    "group_id string",  # the parent group (ADR 0071); null: a gate, or a partition before groups
    runs="merge",
    key=("user_id", "config_id", "instrument_id", "mode", "criterion_id"),
    whole_per_group=True,
)

# A screener run as a business object (ADR 0077 amendment (c); owner decision 2026-10-22): one row
# per run of one config for a session, written in the run's own publish beside
# ``results/rule_screen`` (ADR 0022), so the two cannot drift. The decision counts are the run's
# summary (parallel arrays sorted by decision); ``new_picks`` / ``dropped`` are FROZEN at write,
# counted against ``previous_run_id`` (the config's latest run in the previous stored session of
# ``results/rule_screen``, whatever its version: both versions are kept). Null previous / counts:
# no earlier run to compare with, never 0. Runs merge and the key holds ``run_id``, so every run
# is kept; a reader takes the newest ``knowledge_ts`` per (user, config).
SCREEN_RUNS = fixed(
    "results/screen_runs",
    "results",
    ("user_id", "config_id", "config_hash", "rows", "passed", "picked", "paused"),
    "user_id string!",
    "config_id string!",
    "config_hash string!",
    "config_version int64",
    "rows int64!",
    "passed int64!",
    "picked int64!",
    "paused int64!",
    "decision_names string[]",
    "decision_counts int64[]",
    "regime string",
    "size_multiplier float64",
    "previous_run_id string",
    "previous_session date",
    "previous_version int64",
    "new_picks int64",
    "dropped int64",
    "started_at timestamp_utc",
    "finished_at timestamp_utc",
    runs="merge",
    key=("user_id", "config_id", "run_id"),
)

# A screener run's picks as a business object (ScreenPick, same decision): the rows of
# ``results/rule_screen`` whose decision is a pick or a regime-gate ``PAUSED`` (the same columns,
# equal), one file per run, sorted by ``instrument_id``. No field value: those stay in
# ``results/rule_screen_values`` under their licence, so this table adds no licence surface.
# Not ``whole_per_group``: a run with no picks writes no file, so the newest file of a group can
# be an older run's. Read it by the ``run_id`` taken from ``results/screen_runs`` (``read_run``).
SCREEN_PICKS = fixed(
    "results/screen_picks",
    "results",
    ("instrument_id", "user_id", "config_id", "decision", "rank"),
    "instrument_id string!",
    "user_id string!",
    "config_id string!",
    "config_version int64",
    "decision string!",
    "score float64",
    "rank int64!",
    "regime string",
    "size_multiplier float64",
    runs="merge",
    key=("user_id", "config_id", "instrument_id"),
)
