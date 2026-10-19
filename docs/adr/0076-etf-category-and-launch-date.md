# ADR 0076: ETF category and launch date: the specialised-ETF flag behind `thematic_etf_launch_fade`

**Status:** accepted (2026-10-19; the three product calls below were taken by the owner, see
`docs/decisions/log.md`). Extends [0013](0013-universe.md) (the reference snapshot's ETF flags),
[0018](0018-figi-instrument-ids.md) (the listing history) and
[0075](0075-market-triggers-lockup-reverse-split-and-two-windows.md) (`etf_launch`, deferred
there).

## Context
Ben-David, Franzoni, Kim and Moussawi (RFS 2023) find that newly launched *specialised* equity ETFs
(sector and thematic funds) lose about 6 % a year in their first five years. The edge document
`thematic_etf_launch_fade` was blocked on two missing facts: which ETFs are specialised, and when
each launched. Both are judgement and data calls, not implementation details, so they are decided
here and the judgement is curated by a reviewer, not hidden in code.

## Decision
1. **Both sector and thematic funds are flagged, as two categories.** The paper counts broad GICS
   sector funds (XLK, XLF) as specialised, so the faithful test needs both; keeping them apart
   lets an edge or screener choose and keeps the paper's headline result checkable.
   `instruments/reference` gains `etf_category` (`thematic`, `sector`, `broad`, `excluded`; null =
   UNKNOWN), `etf_theme` (the theme group, the sector, or the exclusion kind) and
   `etf_category_source` (`override`, `name_rule`, `needs_review`, `unclassified`, `not_etf`).
2. **Resolution order** (`tasks/reference/classify.py`, rules in `config/site/universe.toml
   [etf_category]`, typed in `config/site/universe/etf_category.py`): a curated row in
   `config/site/overrides/thematic_etfs.csv` wins; a leveraged or inverse fund is `excluded`;
   exclusion phrases (bond, spot commodity or currency, option income, allocation) exclude; a theme
   phrase without a broad phrase is `thematic`, a sector phrase without one is `sector`, a broad
   phrase alone is `broad`; a theme or sector phrase next to a broad one is `needs_review`; no phrase
   is `unclassified`. UNKNOWN fails closed (never counted as specialised or as broad). The
   curated file was built by an Opus review of the rules' output (2026-10-19); names it could not
   settle stay UNKNOWN and are listed for the owner in the PR description.
3. **Launch date** is the Tiingo `instruments/listing_history.start_date`, the earliest listing of
   the ticker, disclosed as `launch_date_source = "tiingo_listing"`. It is the ticker's first
   listing, not the fund's inception (a ticker change or relisting moves it; a fund older than
   Tiingo's coverage is capped at it), so a sample was checked against issuer inception dates
   (recorded in the PR). It is known on that date: a listing is public the day it starts.
4. **Event class `etf_launch`**: the rollup `etf_launches@v1` carries `sessions_since_etf_launch`,
   `last_etf_launch_date`, `etf_category`, `etf_theme` and `launch_date_source` for ETFs whose
   category is `thematic` or `sector` and launched in the last 1300 sessions (five years); subtypes
   `thematic` and `sector`; anchor the launch day, known on it (`announced_ahead` false). The input
   `instruments/etf_launches` (`data/listings/etf_launches.py`) reads the latest listing and
   reference snapshots as identity reads and keeps point in time by the launch date. The edge's
   universe is `security_type = ETF`; its screener `etf_launch_recent` gates on the 20-session
   dollar volume, which needs twenty sessions of bars, so the entry is the 21st session
   (`start_offset_sessions = 21`) and the first month is not measured. Horizons 250, 750 and 1250
   sessions (one, three and five years), the short side as for the other avoid-list edges. The
   avoid window is the horizon and the screener's `sessions_since_etf_launch` bound (750, a new
   preset version changes it).

## Consequences
- The classification reads the name as of the build, so a renamed fund carries today's category on
  its launch date (a disclosed tilt); the edge's report says so.
- Delisted funds are classified too (carried rows from before this ADR are classified from their
  stored name), so closed funds, which drive the paper's fade, stay in the sample; a fund that
  never reached a reference snapshot has no category and is not in the edge's sample (a
  survivorship tilt the edge report discloses).
- A fund whose leverage is itself UNKNOWN has an UNKNOWN category: a geared fund the leverage rules
  missed is never read as thematic by its name.
- Overrides are keyed by symbol (as `leveraged_etfs.csv` is): a ticker reused by a new fund
  inherits the curated row until the file is edited.
- A new curated file to maintain: the build writes the UNKNOWN names with `--etf-review-out`.
- The keyword phrases are judgement calls the owner can change in the TOML; the override file wins.
