# Filtering and search on tables, lists and feeds

Spec for ADR 0082. A screen that shows many rows (Ideas, screener results, the screener list,
Edges, Explore, edge detail tables) filters through one component family and one read contract;
a page declares nothing but its surface name.

## User cases every surface answers
Find a name; narrow many to few; what changed since the last session; why is this here or not
here; compare; come back later (saved view, shareable URL). The capability checklist: text
search, facet filters, range filters, sort, column sets, saved views, applied chips with counts,
URL state, zero-result recovery, keyboard, phone. A surface that omits one says why in its PR.

## Layout (approved mockups, 2026-10-23)
One toolbar row: search, one button per group (Setup, What changed, Tradeable, Coming up), "More
filters" (type to find any catalogue feature), Views. A group button shows a count badge and an
accent border while it holds filters; it opens a small popover. Below, the applied chips; below
that "N of M", Clear all, Save view. Phone: search plus one Filters button opening a sheet with
"Show N results"; chips scroll sideways (container query, ADR 0052).

## Chips
Each applied filter is a chip: `Label value` and "removes N" (rows it removes given the other
filters). Clicking switches it off (struck through, kept, in no mask); the x removes it. Every
count comes from the server (ADR 0038).

## Zero results
"No <thing> matches all K filters" and the best loosening chips: "Switch off X gives N" (the K
largest). The same `removes` pass supplies them.

## Control kinds
`pick` multi-select with counts; `select` one value; `toggle` yes / no / either; `range` min and
max numbers with a histogram of the candidates (fixed bin edges; with `unit = "percent"` the stored 0..1 value is shown and entered as
0..100 and the limits are sent as 0..1); `window` within N days or
sessions; `percentile` (later) top or bottom N% of a named cohort. An unknown value never passes
a filter; the control says how many rows are unknown, with a Guide term.

## Definitions and contract
See ADR 0082 decisions 1-4: `config/site/filters/<surface>.toml` -> `filterSet(surface)`;
`filters: [FilterInput!]` in, `facets` out; URL parameter `f` =
`decision:QUALIFIED,WATCH;dte:..14;rsi_14@v1:30..70;!liq:risk`.

## Components (`@algotrade/ui`)
`FilterBar` (search, groups, chips, actions, count, narrow sheet), `FilterGroupButton`,
`RangeFilter` (with an `unknownHelp` slot for the Guide term), `WindowFilter`, `ZeroResults`, `FilterChips` (structured items; `onClear` only when the bar does not own Clear all). Pick uses `OptionList`, toggle
`SegmentedControl`. Each has stories for every state, a `Narrow` story, an axe unit test and
light and dark screenshots.

## More filters (find a filter by typing)
On a surface whose rows are instruments (it declares at least one catalogue-field filter:
`FilterSet.searchable`), the "More filters" button opens a search over the catalogue
(`filterFeatures(surface)`: a field the viewer's data licences do not cover is not listed; the
phrasebook's words for a field are in its option text, so "liquid" finds dollar volume). Picking
a field starts a filter with the id `feature:<field>` (a catalogue field: `rollup.<group>@v<N>.<column>`
or `feature.<name>`), served like any other: `filterSet(surface, withFeatures: [<field>])` returns
its definition (group `more`, kind from the dtype: number -> range with bins chosen from the
values, flag -> toggle, label -> pick; unit `percent` for a fraction; Guide entry `field:<field>`),
and `filters: [{ id: "feature:<field>", ... }]` narrows the list with the same counts. A hidden
field is refused if sent; a surface of its own columns (Screeners, Edges) takes none. In the
URL the id is percent-encoded (`f=feature%3Arollup...:1000..`).
