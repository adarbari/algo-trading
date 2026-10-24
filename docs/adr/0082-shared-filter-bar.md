# ADR 0082: One filter bar for every table, list and feed

**Status:** accepted (2026-10-23; owner approved the mockups: one toolbar row, group popovers,
applied chips that show what they remove, zero-result recovery). Extends
[0037](0037-domain-read-model-served-by-graphql.md) (reads through GraphQL),
[0038](0038-catalogue-named-values.md) (the browser derives nothing),
[0051](0051-guide-explain-once-show-in-place.md) (every label has a Guide entry), [0052](0052-one-ui-for-phones-and-desktops.md)
(one tree for phones and desktops) and [0069](0069-data-licence-gate.md) (the licence gate).
Spec: `docs/ui/filtering.md`.

## Context
Ideas filters only the 50 rows already loaded (a defect); the screener list searches the id;
the Edges list has four fixed views and no search; no surface has a numeric range, a count per
filter, a way back from zero results or filter state in the URL. Each page has its own filter
code. The design system has `FilterBar` and `FilterChips`, but for single-valued string filters
the caller computes itself, and the browser may not compute counts or percentiles (ADR 0038).

## Decision
1. **Definitions are server-declared.** `config/site/filters/<surface>.toml` (a `FiltersSettings`
   model) lists each filter: `id`, `label`, `group` (`setup`, `changed`, `tradeable`,
   `coming_up`, `more`), `kind` (`pick`, `select`, `toggle`, `range`, `window`, later
   `percentile`), `unit` (`percent` on a range: shown 0..100, sent 0..1), `field` (a catalogue `name@version` or a column of the surface), `options`
   (`static`, `values` stored for the session, or an `enum`), `bins` (fixed histogram edges,
   required for a range), `guide` (an entry reference, required). A fitness test checks the
   field exists, the kind fits its dtype, and the Guide entry and coverage row exist. Licence is
   never declared: it is derived per viewer (ADR 0069). GraphQL serves them as `filterSet(surface)`;
   the web declares no filter.
2. **One typed input, one pass.** Every list field takes `filters: [FilterInput!]`
   (`id`, `values`, `min`, `max`, `within: {amount, unit}` with `unit` `DAYS` or `SESSIONS`, `active`); the operator comes from the definition's
   kind. The result carries `facets` (`total`, `matched`, per filter `removes`, `unknown`, option
   counts, histogram bins), all from one masked pass: `removes(f)` is the rows passing every
   other active filter minus `matched`; zero-result recovery is the same number. An inactive
   (switched-off) filter is echoed and in no mask. UNKNOWN never passes a filter and is counted
   with a Guide term (ADR 0036). A filter on a field the viewer's licences do not cover is not
   offered and is refused if sent; on the site run, filters and counts apply after the per-viewer
   withholding, so a count never leaks a withheld value.
3. **One loader, one owner.** `src/algotrade/services/read/filtering/` (definitions, masks,
   facets; pure and deterministic: fixed bin edges, option order by count then value). Loaders
   adopt it in turn: Ideas, screener results, the universe table, then the screener and edge
   lists. Paging filters first, then pages; an Ideas cursor carries a hash of the filters. The
   old per-surface arguments (`decisions`, `change`, `UniverseFilter` fields) become definitions
   and are deprecated, then removed. "Within N sessions" counts from the read session over events
   with `known_from <= S`; "what changed" compares with the run before S.
4. **URL state.** One search parameter `f`, `decision:QUALIFIED,WATCH;dte:..14;rsi_14@v1:30..70;!liq:risk`
   (`!` = switched off, `lo..hi` = range, a window is `earn:..5s` or `..14d`: amount then unit `d` days / `s` sessions; a value containing `,`, `;`, `:` or `%` is percent-encoded). Codec and `useFilterState(surface)` live in
   `apps/web/src/features/filter-bar/`; the definitions query in `entities/filter/`. Saved views
   store the `f` string.
5. **One component family.** `FilterBar` gains `groups`, `actions`, `count` and, narrow,
   `applyLabel` ("Show N results"); new `FilterGroupButton`, `RangeFilter`, `WindowFilter` and `ZeroResults`;
   `FilterChips` takes structured items (`label`, `valueText`, `removes`, `unknown`, `active`)
   with `onToggle`, `onRemove`, `onClear`. Pick uses `OptionList` with counts, toggle
   `SegmentedControl`. A table, list or feed screen uses these and nothing else.
6. **Cut from the first version:** percentile-of-cohort filters (each is a `cross_section`
   feature, added with `add-feature`, no ADR), Export (open: may personal-licence values leave
   as a file? until the owner decides, none), a slider, a count for switched-off chips.

## Consequences
One filter code path serves every surface, so the screener list, Edges and Explore get search,
ranges, counts and shareable URLs by adding a TOML file. The browser's client-side Ideas filter
(`widgets/top-ideas/model/filters.ts`) is deleted. Cost: a masked pass per request over the
surface's rows (benchmarked before Ideas adopts it, ADR 0077's response cache keys on the licence
set plus the filter hash); a new config kind, a new read folder and a schema change to the saved
views. Delivery is twelve small PRs; the design-system components and this ADR come first.
