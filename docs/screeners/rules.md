# Rule screens (`impl = "rules"`)

> **Status:** engine implemented (`strategies/screeners/rules/`, nightly `screen` jobs);
> Builder, preview and Ideas to come ([ADR 0029](../adr/0029-rule-screener.md)).

A rule screen is a screener written as TOML instead of Python. The web Builder edits the same
file. It obeys the [screener contract](README.md#contract-all-screeners): one row per
instrument of the selection, a shared `Decision`, fail closed, a coverage audit.

## Where it lives

| File | What |
|---|---|
| `config/site/presets/screeners/<id>/v<N>.toml` | site preset versions, added by PR, immutable (hash-locked in `architecture/preset_versions.toml`); the latest is the highest N; visible and editable in the Builder |
| `config/users/<u>/screeners/<id>/draft.toml` | the Builder's working copy (autosaved, never run nightly) |
| `config/users/<u>/screeners/<id>/v<N>.toml` | a finalised version: immutable; the latest is the highest N |
| `config/users/<u>/screeners/<id>/schedule.toml` | the schedule switch (not part of a version, not in the config hash) |

Finalise validates the spec (fields exist in the catalogue, types match, user features
resolve) and refuses to save an invalid one. Finalising does not schedule: the nightly
schedule (`schedule = "nightly"`) is a separate switch, kept outside the versioned document
and the config hash (the hash says what a screen computes, not when it runs).

## Example

```toml
id = "high_iv_near_extreme"
kind = "screener"
impl = "rules"
version = 2
selection = "liquid_optionable"      # who is screened
schedule = "nightly"                  # omit to run only on request

[criteria.price]
field = "rollup.price_stats@v2.close"
op = "gt"
value = 5
mode = "hard"                         # strict: 4.99 is a REJECT

[criteria.spread]
field = "feature.iv_hv_spread"
op = "gte"
value = 0.10
mode = "soft"
tolerance = 0.02                      # 0.08-0.10 is a near miss (WATCH); below 0.08 REJECT

[criteria.adv]
field = "rollup.price_stats@v2.adv_usd_20d"
op = "gte"
value = 50_000_000
mode = "soft"
tolerance = { relative = 0.2 }        # 20% of the threshold: $40M-$50M is a near miss
on_miss = "LIQUIDITY_RISK"
label = "ADV > $50M"

[criteria.iv_rank]
field = "rollup.ibkr_iv@v1.iv_rank_252d_ibkr"
op = "gte"
value = 0.5
mode = "score"                        # never gates; a miss only lowers the score
tolerance = 0.5

[tiers.STRONG]
all = [{ field = "feature.iv_hv_spread", op = "gte", value = 0.15 }]

[flags.leveraged]
all = [{ field = "instrument.is_leveraged", op = "eq", value = true }]

[columns]
next_earnings = "rollup.earnings@v1.next_earnings_date"

[rank]
tie_break = "feature.iv_hv_spread"    # sorts rows with equal scores; descending by default
```

Field names are catalogue names (`instrument.*`, `rollup.<group>@vN.*`, `feature.<name>`;
see `GET /features` and [docs/data/features.md](../data/features.md)). A formula is never
written inline: make it a user feature (`config/users/<u>/features/`) and use
`feature.<name>`; the Builder's "Add formula feature" does this and asks the user to name it.

## Criteria

A criterion is `field`, `op`, `value` (ops: `eq ne in not_in gt gte lt lte between is_null
not_null`) plus:

| Key | Meaning | Default |
|---|---|---|
| `mode` | `hard`, `soft` or `score` | `hard` |
| `tolerance` | how far a value may miss the threshold and still be a near miss: a number (absolute, in the field's unit) or `{ relative = r }` (r × \|threshold\|). Required for `soft`, optional for `score`, not allowed for `hard`; numeric comparisons only (`gt gte lt lte between`) | |
| `on_miss` | `soft` only: the decision of a near miss, `WATCH`, `LIQUIDITY_RISK` or `EVENT_RISK` | `WATCH` |
| `label`, `enabled` | display text; `enabled = false` switches it off (also removes an inherited one) | |

| Mode | TRUE | FALSE | Missing data |
|---|---|---|---|
| `hard` | passes | **REJECT** | row **SKIPPED** (`no <field>`) |
| `soft` | passes | within tolerance: near miss (`on_miss`, WATCH at best); beyond: **REJECT** | row **SKIPPED** (`no <field>`) |
| `score` | passes | lowers the score only | lowers the score only (full penalty) |

Missing data never passes: a value that is absent, NaN or of the wrong type for the op is
missing.

## Decision

1. Any `hard` or `soft` criterion missing → `SKIPPED` (not processed; counts against
   coverage; reasons `no <field>`).
2. Any `hard` FALSE, or `soft` FALSE beyond its tolerance → `REJECT`.
3. Any near miss → the most severe near-miss `on_miss`: `EVENT_RISK` > `LIQUIDITY_RISK` >
   `WATCH`; every reason is listed.
4. Otherwise `QUALIFIED`.

## Score

For sorting only (not a probability). A row that meets every threshold scores **100**; each
miss subtracts a penalty:

| Miss | Penalty |
|---|---|
| near miss (`soft` within tolerance, `score` within tolerance) | `10 × distance / tolerance` (0 to 10) |
| `score` beyond its tolerance, without a tolerance, or missing | 10 |
| `hard` FALSE, `soft` beyond tolerance | 100 |

`distance` is how far the value is from the threshold (from the nearer bound for `between`).
The score is clipped to 0 to 100 (clipped at 0; only positive scores), so many hard fails tie at 0.
REJECT rows are scored too.
SKIPPED rows have no score. Rows sort by score (descending), then by `[rank] tie_break`
(descending unless `tie_break_order = "asc"`; missing last), then by instrument id. Then:
`tiers` (first TRUE group wins), `flags` (TRUE adds the flag, never changes the decision),
`classify = "<label field>"` (buckets the output), `columns` (values stored with the row).

## Run summary

Every run, preview and nightly, reports: how many rows passed (QUALIFIED), the count of each
decision, the skipped rows counted by reason (`no <field>`), and the **narrow misses**: rows
that missed only within tolerance, with each criterion, the value, the threshold and the
distance.

## Extending a preset

```toml
id = "my_vrp"
extends = "vrp_scanner@3"                 # pinned; the Builder offers "rebase on v4"
[criteria.iv30]
value = 0.40                              # override one threshold, keep the rest
[criteria.adv]
enabled = false                           # drop an inherited criterion
```

Criteria merge by id; a user screen pins the preset version it extends. A pinned version
always resolves (preset versions are immutable); rebasing onto a newer version is optional.

## Preview and results

The Builder's preview runs the same `evaluate_screen` as the nightly `screen` job on the
latest closed session and saves nothing. Nightly rows go to `results/rule_screen` (one per
instrument: decision, score, rank, tier, class, flags, reasons, config id / version / hash),
`results/rule_screen_values` (one per criterion: value, PASS / NEAR / FAIL / MISSING / INFO,
distance, penalty); the run summary is in the run record (`stats["summary"]`). Ideas ranks tickers
across saved screens: one row per ticker, by the highest-priority screener that picked it,
then score.
