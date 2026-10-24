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

## Export
The bar's `actions` slot may hold `ExportButton` (`features/filter-export`, Guide terms `export` and
`export_notice`): it saves the rows the filters in force leave as `GET /files/<surface>.csv?f=<f>`
(ADR 0082 decision 6). The rule: **a file carries what the viewer can see and nothing more.** The
server builds it through the surface's own gated loader and the same filtering pass as the page
(`services/read/export/`), so the rows and order are the page's for the same `f`; a value under a
licence the viewer does not hold is `LICENCE` (never the value), an unknown one its public kind,
a hidden filter's field is not offered or refused as on the page. The first line is the notice
(session, viewer, licences held, own-use wording); more than 50,000 rows are cut and the second
line says so; each export logs one audit line. A new surface adds one entry to
`services/read/export/surfaces.py` (its loader and text cells) and puts the button in its bar. Wired on Ideas;
screener results and the universe are served by the route and take the button with their page
migrations.

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

## Enforcement
`tests/architecture/test_layout_web.py::test_data_surfaces_use_the_filter_bar` ([ADR 0025 rule 12]) fails when a
file under `apps/web/src` renders `DataTable`, `ExpandableTable`, `FeatureTable` or `MasterDetail`
without `SurfaceFilterBar` / `FilterBar`, unless `architecture/web_filter_bar.toml` lists it:
`[migrating]` (surfaces that will get the bar; shrink-only, the migrating PR deletes its line) or
`[exempt]` (a reason: a fixed handful of rows, a detail panel). A fitness test with a TOML baseline
is used, as for prose and derivations, because the baseline carries a reason per file, which
an ESLint rule cannot. A listed file that gained the bar fails with its name, so a PR that
migrates a surface must delete its line.

## Views (saved views of a surface)
Every filter-bar surface offers "Views" in the toolbar (`SurfaceFilterBar views`: `true` keeps the
user's views under the scope `surface:<name>`; a page that also saves columns and sort passes its
`useTableView` state). A view is the `f` string (and the page's columns and sort where it has them);
the list shows each view with the filters it holds, in the chips' words from the definitions, and
the save form shows the filters about to be saved. Applying a view puts its `f` in the URL; filters
the surface no longer defines are dropped and named ("Not applied"); a `feature:` filter is kept (the
server gates it). The server accepts `surface:<name>` for a surface with a filters file
(`services/read/screens/views.py`).
