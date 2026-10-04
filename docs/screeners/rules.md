# Rule screens (`impl = "rules"`)

> **Status:** spec ([ADR 0029](../adr/0029-rule-screener.md), proposed); not implemented yet.
> Defaults marked *(pending)* await owner confirmation (ADR 0029, "Pending owner confirmation").

A rule screen is a screener written as TOML instead of Python. The web Builder edits the same
file. It obeys the [screener contract](README.md#contract-all-screeners): one row per
instrument of the selection, a shared `Decision`, fail closed, a coverage audit.

## Where it lives

| File | What |
|---|---|
| `config/site/presets/screeners/<id>.toml` | site preset, changed by PR, carries `version = N` |
| `config/users/<u>/screeners/<id>/draft.toml` | the Builder's working copy (autosaved, never run nightly) |
| `config/users/<u>/screeners/<id>/v<N>.toml` | a finalised version: immutable; the latest is the highest N |

Finalise validates the spec (fields exist in the catalogue, types match, user features
resolve) and refuses to save an invalid one. Finalising does not schedule: set
`schedule = "nightly"` separately *(pending)*.

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
mode = "hard"

[criteria.spread]
field = "feature.iv_hv_spread"
op = "gte"
value = 0.10
mode = "hard"
weight = 30
score = { from = 0.10, to = 0.25 }   # 0 points at 0.10, all 30 at >= 0.25

[criteria.adv]
field = "rollup.price_stats@v2.adv_usd_20d"
op = "gte"
value = 50_000_000
mode = "soft"
on_miss = "WATCH"
label = "ADV > $50M"

[criteria.iv_rank]
field = "rollup.ibkr_iv@v1.iv_rank_252d_ibkr"
op = "gte"
value = 0
mode = "score"
weight = 10
score = { from = 0.0, to = 1.0 }

[tiers.STRONG]
all = [{ field = "feature.iv_hv_spread", op = "gte", value = 0.15 }]

[flags.leveraged]
all = [{ field = "instrument.is_leveraged", op = "eq", value = true }]

[columns]
next_earnings = "rollup.earnings@v1.next_earnings_date"

[decision]
max_soft_misses = 1
```

Field names are catalogue names (`instrument.*`, `rollup.<group>@vN.*`, `feature.<name>`;
see `GET /features` and [docs/data/features.md](../data/features.md)). A formula is never
written inline: make it a user feature (`config/users/<u>/features/`) and use
`feature.<name>`; the Builder's "Add formula feature" does this and asks for a name *(pending)*.

## Criteria

A criterion is `field`, `op`, `value` (ops: `eq ne in not_in gt gte lt lte between is_null
not_null`) plus:

| Key | Meaning | Default |
|---|---|---|
| `mode` | `hard`, `soft` or `score` | `hard` |
| `weight` | points toward the score (0 = not scored) | 0 |
| `score` | `{ from, to }` linear ramp: `from` earns 0, `to` earns the full weight, clipped; reversed when `from > to` | full weight on a pass |
| `on_miss` | decision when it fails: `REJECT`, `WATCH`, `EVENT_RISK`, `LIQUIDITY_RISK` | `REJECT` (hard), `WATCH` (soft) |
| `label`, `enabled` | display text; `enabled = false` switches it off (also removes an inherited one) | |

| Mode | TRUE | FALSE | UNKNOWN (missing data) |
|---|---|---|---|
| `hard` | passes | `on_miss` (REJECT) | row is **UNKNOWN** *(pending)* |
| `soft` | passes | miss: `on_miss` (WATCH) | miss, reason `unknown:<id>` *(pending)* |
| `score` | earns points | earns ramp points (0 below `from`) | 0 points, recorded, not a miss |

## Decision and score

1. Any hard criterion UNKNOWN → `UNKNOWN` (not processed; counts against coverage).
2. Any hard FALSE with `on_miss = REJECT`, or more than `max_soft_misses` (default 1
   *(pending)*) soft misses → `REJECT`.
3. Otherwise the most severe miss wins: `EVENT_RISK` > `LIQUIDITY_RISK` > `WATCH`; every
   reason is listed *(pending)*.
4. Otherwise `QUALIFIED`.

`score = 100 * points / sum(weights)`, 0-100, for sorting only (not a probability). Every
non-UNKNOWN row is scored, REJECT included *(pending)*. Then: `tiers` (first TRUE group wins),
`flags` (TRUE adds the flag, never changes the decision), `classify = "<label field>"`
(buckets the output), `columns` (values stored with the row for display).

## Extending a preset

```toml
id = "my_vrp"
extends = "vrp_scanner@3"                 # pinned; the Builder offers "rebase on v4"
[criteria.iv30]
value = 0.40                              # override one threshold, keep the rest
[criteria.earn]
enabled = false                           # drop an inherited criterion
```

Criteria merge by id; a user screen pins the preset version it extends *(pending)*.

## Preview and results

The Builder's preview runs the same `evaluate_screen` as the nightly `screen` job on the
latest closed session *(pending)* and saves nothing. Nightly rows go to
`results/rule_screen` (one per instrument: decision, score, tier, class, flags, reasons,
config id / version / hash) and `results/rule_screen_values` (one per criterion: value,
PASS / FAIL / UNKNOWN / INFO, points). Ideas ranks tickers across saved screens: one row per
ticker, by the highest-priority screener that picked it, then score *(pending)*.
