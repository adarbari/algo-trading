# Rule screens (`impl = "rules"`)

> **Status:** engine, preview, Ideas and the web Builder implemented
> (`strategies/screeners/rules/`, nightly `screen` jobs, Trader > Screeners;
> [ADR 0029](../adr/0029-rule-screener.md)).

A rule screen is a screener written as TOML instead of Python. The web Builder edits the same
file. It obeys the [screener contract](README.md#contract-all-screeners): one row per
instrument of the day's universe snapshot, a shared `Decision`, fail closed, a coverage audit.
There is no selection ([ADR 0030](../adr/0030-rule-screener-simplification.md)): who is screened
is a list of `hard` criteria like any other (security type, `ACTIVE`, optionable).

## Where it lives

| File | What |
|---|---|
| `config/site/presets/screeners/<id>/v<N>.toml` | site preset versions, added by PR, immutable (hash-locked in `architecture/preset_versions.toml`); the latest is the highest N; visible and editable in the Builder |
| `config/users/<u>/screeners/<id>/draft.toml` | the Builder's working copy (autosaved, never run: only finalised screens run) |
| `config/users/<u>/screeners/<id>/v<N>.toml` | a finalised version: immutable; the latest is the highest N |

Finalise validates the spec (fields exist in the catalogue, types match, user features
resolve) and refuses to save an invalid one. An error names the criterion and the key at
fault (`<id>.criteria.<criterion_id>.field`, `.value` or `.tolerance`), so the Builder can mark
the row; preview and finalise report the same paths. There is no schedule switch (ADR 0033): finalising a screen puts it on the nightly, and every
site screener preset runs nightly too. An old `schedule` key in a document is ignored.

## Drafting from a sentence (ADR 0041)

The Builder's "Describe it" box sends a sentence ("optionable stocks over $5 with IV rank
above 50%") to `POST /screeners/{id}/draft-from-text`. The text model `config/site/llm.toml`
names (off by default; any OpenAI-compatible endpoint, the key only in the environment) maps it
onto the user's field catalogue; the answer is parsed strictly, every criterion on a field
the catalogue does not have is dropped with a reason, the rest is validated exactly as
finalise does, and the Builder loads the result as unsaved rows. The model's notes say what it
could not map. Nothing is saved or run until the user saves and finalises as usual.

## Example

```toml
id = "high_iv_near_extreme"
kind = "screener"
impl = "rules"
version = 2

[criteria.optionable]                 # who is screened is a criterion too
field = "instrument.optionable"
op = "eq"
value = true

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

[criteria.iv_rank]
field = "rollup.ibkr_iv@v1.iv_rank_252d_ibkr"
op = "gte"
value = 0.5
mode = "score"                        # never gates; a miss only lowers the score
tolerance = 0.5

[flags.leveraged]
all = [{ field = "instrument.is_leveraged", op = "eq", value = true }]

[columns]
next_earnings = "rollup.earnings@v1.next_earnings_date"

[rank]
tie_break = "feature.iv_hv_spread"    # sorts rows with equal scores; descending by default
```

A copy of a preset clears an inherited tie-break with `tie_break = ""` (a user layer cannot
delete a key); changing it is setting another field.

Field names are catalogue names (`instrument.*`, `rollup.<group>@vN.*`, `feature.<name>`;
see the GraphQL `catalogue` and [docs/data/features.md](../data/features.md)). A formula is never
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
| `enabled` | `enabled = false` switches it off (also removes an inherited one) | |

| Mode | TRUE | FALSE | Missing data |
|---|---|---|---|
| `hard` | passes | **REJECT** | **REJECT** (`no <field>`), penalty 100 |
| `soft` | passes | within tolerance: near miss (`on_miss`, WATCH at best); beyond: **REJECT** | the row stays in; full near-miss penalty (10) and `no <field>` listed in the reasons |
| `score` | passes | lowers the score only | lowers the score only (full penalty) |

Missing data never passes and never skips a row: a value that is absent, NaN or of the wrong
type for the op is missing. A `hard` criterion with no value is a fail; the other two only
cost points.

## Decision

1. Any `hard` FALSE or missing, or `soft` FALSE beyond its tolerance → `REJECT` (reasons
   include `no <field>`).
2. Any near miss → the most severe near-miss `on_miss`: `EVENT_RISK` > `LIQUIDITY_RISK` >
   `WATCH`; every reason is listed.
3. Otherwise `QUALIFIED` (a `soft` criterion with no value is listed in the reasons).

`SKIPPED` is no longer produced; stored rows from before ADR 0030 still carry it.

## Score

For sorting only (not a probability). A row that meets every threshold scores **100**; each
miss subtracts a penalty:

| Miss | Penalty |
|---|---|
| near miss (`soft` within tolerance, `score` within tolerance) | `10 × distance / tolerance` (0 to 10) |
| `score` beyond its tolerance, without a tolerance, or missing; `soft` missing | 10 |
| `hard` FALSE or missing, `soft` beyond tolerance | 100 |

`distance` is how far the value is from the threshold (from the nearer bound for `between`).
The score is clipped to 0 to 100 (clipped at 0; only positive scores), so many hard fails tie at 0.
REJECT rows are scored too.
Rows sort by score (descending), then by `[rank] tie_break`
(descending unless `tie_break_order = "asc"`; missing last), then by instrument id. Then:
`flags` (TRUE adds the flag, never changes the decision) and `columns` (values stored with the
row). A criterion has no stored name: the Builder reads it from its field, operator and
threshold ("IV30 ≥ 50%"). `tiers`, `classify` and `label` were removed in
[ADR 0030](../adr/0030-rule-screener-simplification.md); v1 / v2 presets still carry them and
they are ignored.

## Run summary

Every run, preview and nightly, reports: how many rows passed (QUALIFIED), the count of each
decision, and the **narrow misses**: rows
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

The Builder's preview (`POST /screeners/preview`, `services/preview/screens.py`) runs
the same `evaluate_screen` as the nightly `screen` job on the request's session (the latest with
daily bars, ADR 0036) and saves
nothing. It returns the run summary, the decision counts, the funnel (each gating criterion in
order: rows entering, passing, narrowly missing, failing, missing), the coverage and the top
rows. The session's field frame is cached in-process, so editing a threshold, mode or
tolerance re-evaluates in memory (only the edited criterion); a new publish invalidates it.
Nightly rows go to `results/rule_screen` (one per instrument: decision, score, rank,
flags, reasons, config id / version / hash),
`results/rule_screen_values` (one per criterion: value, PASS / NEAR / FAIL / MISSING / INFO,
distance, penalty); the run summary is in the run record (`stats["summary"]`). Ideas ranks tickers
across saved screens: one row per ticker, by the highest-priority screener that picked it,
then score.
