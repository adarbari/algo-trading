# Evening Desk: build plan for the trader site's new screens

Status: plan (2026-11-01). Basis: [ADR 0083](../adr/0083-workflow-first-trader-site.md) and its
amendment of 2026-11-01 (Ideas tabs, idea page, watchlist, sign-up answer, derived option
figures), [ADR 0085](../adr/0085-evening-desk-theme.md) (tokens, live), [0051](../adr/0051-guide-explain-once-show-in-place.md)
(the Guide), [0052](../adr/0052-one-ui-for-phones-and-desktops.md) (one tree),
[0088](../adr/0088-setups-as-positions-and-rules.md) (option setups; backend slices in
[options/backend-build.md](../options/backend-build.md)). Decisions: `docs/decisions/log.md`,
2026-11-01 entries.

Mockups: the canvas artifact `https://claude.ai/artifact/4uNu2h5uGGWYv7V6MVKLkw`; read a screen
with the Artifact tool, `action: "read"`, `path: "project/<Name>.dc.html"`. `*Phone` files are the
same screens at phone width (ADR 0052: one tree, never a page). A_/B_/C_/BL_/Dir*/Brief*/Sweep are
alternatives; Pricing is out of scope (payments need their own ADR). The mockup is a layout, not a
spec: where it shows something this plan or an ADR rules out (section 2), the rule wins.

## 1. Approach
- **Restyle and regroup what exists; never build a near-duplicate** (owner rule 2026-10-25). Most
  mockup elements are existing `@algotrade/ui` components with a new variant (table in section 3).
  A slice that replaces a page deletes the old page's widgets in the same PR.
- **Every slice ships its Guide entries** (`add-guide-content`: every new word, section, column
  header and enum value) and its `Narrow` story / phone e2e check (`responsive-ui`).
- **Server work follows the skills:** a new read object `add-domain-object`, a field
  `add-graphql-field`, a write or preview POST `add-api-endpoint`, a new responsibility
  `add-responsibility`; review per CLAUDE.md (architect for a new read object, responsibility,
  table, feature group or `quant/` maths; own review otherwise).
- **Vertical slices, each working end to end** (owner instruction 2026-11-01): a slice ships one
  new screen, or one section of it, with its read or write, the components it needs, the page and
  route, the Guide entries and the phone e2e check, and deletes the old screen's equivalent in the
  same PR or the next. U0-U6 are groupings, not gates. Screens whose data exists today come first;
  option-setup screens follow the options backend as it lands
  ([options/backend-build.md](../options/backend-build.md)); a backend piece no one is building yet
  is part of the slice that needs it.
- **File-disjoint slices.** Each slice owns the folders in its row; where two slices touch one
  module the order is in section 6. Shared files every slice may append to:
  `apps/web/design-system/components/index.ts` and `COMPONENTS.md` (append-only; on conflict
  `scripts/merge_main.sh`), and the generated schema / client files (never hand-merged:
  regenerate).

## 2. Rules every screen keeps (decided; see the log)
- **Wording:** "publishes setups", "the setup's historical exit rule"; never "recommend", "buy",
  "sell" as an instruction, "your plan", "your stop", "your size". The mockup's "The plan" section
  is titled *Historical exit rule*; "Copy plan as text" is *Copy exit rule as text*; the
  mockup's "Size: not ours to say" row is dropped. V3 adds ADR 0083's wording fitness test.
- **Labels:** every statistic says "backtested (hypothetical)" or "forward paper record since
  <date>"; the `StatStrip` evidence variant takes the basis as a required prop, so an unlabelled
  figure does not compile.
- **Option figures (decision B, extended by Fable):** our computed mid premium, spread as % of mid,
  open interest and volume, a straddle from mids, IV, IV rank, delta, yield %, return on
  collateral, breakeven, probability of ending below the strike. Never a vendor bid, ask, last or
  size on a trader screen. The raw-column Options tab and `GET /chains/{underlying_id}/live` stay,
  admin-only.
- **Nothing personal stored:** the watchlist holds instrument ids only (max 50); the calculators'
  typed figures (contract count, sold-at price, cost basis) live in component state only: never in
  the URL, `localStorage`, a user config, a request log or a cache key; the preview POSTs take them
  in the body and return figures, Reg-T only (no broker rule tables).
- **One nightly batch:** the Premium tab reads the same nightly list (no Sunday edition); a
  weekly setup simply picks once a week.
- **Out of this track:** Past lists (the scorecard has its own ADR, ADR 0083 decision 2); a "Yours"
  Ideas tab (Ideas is Stocks | Premium; followed and own setups live on Setups, the watchlist in
  Settings and the Watch toggle); the nightly brief toggle, plan / trial, data download and account
  deletion in Settings (brief delivery, billing, the Authenticator ADRs); premium strategy tests
  (OptTestBuild, OptTestResult: history-derived evidence is owner-only, ADR 0088 decision 12; a later
  owner-only slice once the E-track's history runs exist).

## 3. Mockup element -> component (the U0 session builds them in section 5's order)
| Id | Mockup element | `@algotrade/ui` | Change |
|---|---|---|---|
| C1 | Top bar (4 sections, Guide, ⌘K box, regime pill, avatar) | `TopBar`, `AppShell`, `AccountMenu` | restyle; a footer slot |
| C2 | Footer data-status + risk line | `NoticeLine` + `InfoButton` | `footer` variant, given the risk-statement Guide entry |
| C3 | Command palette | `SearchDialog` | result groups Tickers and Setups |
| C4 | Verdict pill (Works, Promising, Too few cases, Baseline, No better than chance) | `StatusBadge` | a `verdict` tone map; no new badge |
| C5 | 3- and 4-cell stat strip | `StatStrip` | `evidence` variant: required `basis` (backtested / forward) |
| C6 | Setup evidence line | `OddsLine`, `EvidenceMeter` | restyle; composed in `entities/edge`, no new component |
| C7 | Label / value grid (rules; Matched / Entry / Stop / Exit) | `KeyValue` | `grid` layout |
| C8 | Checklist (what could go wrong, before you act, avoid-list) | `ProseList` | `check` variant: ok / warn / unknown marks |
| C9 | Idea rows with a detail pane; grouped tables | `MasterDetail`, `ExpandableTable`, `DataTable` | group header rows, restyle |
| C10 | Basics / More column toggle | `ViewChips` | none |
| C11 | Equity curve, by-year bars, report-move bars, rule distribution | `Chart`, `Distribution`, `Sparkline` | a `bars-with-reference` kind (the priced move) |
| C12 | Yield grid (expiry x delta) | `HeatGrid` | cell slots (value, sub-line), a selectable cell |
| C13 | Back link and crumbs (setup page, Guide entry) | `TextLink` | none (no `Breadcrumb` component) |
| C14 | Steps of the Test flow | `NavTabs` | a `steps` variant (no `Stepper` component) |
| C15 | Choice cards (onboarding, way in) | `OptionList` | a `card` variant |
| C16 | Ticker tag input (onboarding, Settings) | `Combobox` | `multiple` mode |
| C17 | One-sentence preview | `TaggedSentence` | none |
| C18 | Draft part with status | `PartCard` | statuses `not_available`, `not_said` |
| C19 | Number and select inputs (calculators, expert rules) | `NumberInput`, `Select`, `SegmentedControl` | restyle |
| C20 | Help drawer, sub-nav, doc layout | `HelpDrawer`, `Drawer`, `NavTabs`, `SectionNav`, `DocLayout` | restyle |

No new component: every element is an existing one or a variant of it. Reveal-once is a feature
composing `Disclosure` + `Dialog`.

## 4. Data gaps (each inside the slice that needs it)
- **Option grid (V6).** The yield grid needs, per underlying and session, puts and calls at our
  delta bands and expiry buckets: strike, mid premium, yield % a year on collateral, return on
  collateral, breakeven, probability below the strike, spread % of mid, open interest, a report
  inside the expiry. As catalogue features that is about 540 columns, so the grain is the
  architect's first call in V6: (a, recommended) a read object over the stored chain for the served
  session (`services/read/options/`, a new folder: `services/read/instruments/` is at its 10-module
  cap), the pricing in `quant/`, the summary figures the lists filter on (a 0.20-delta, about 30-day
  put and call: yield, strike, breakeven) as a small catalogue group so `features(names)` and the
  filter bar serve them (ADR 0038); or (b) a compact catalogue group only. `put_wing@v1` and
  `call_wing@v1` stay as they are and share `wing_search.py`; any later retirement is a version bump,
  never an alias. `features/rollups/options/` is at its cap: `make layout` first.
  **Decided (V6, 2026-11-01): (a).** The filter bar needs only the summary (a 0.20-delta, 30-day put
  and call: `short_premium@v1`, in the new `features/rollups/premium/`), and 540 columns are not
  features; the grid is `services/read/options/grid.py` (`Instrument.optionGrid`), the pricing is
  `quant/options/premium.py`, and one pick (`premium/band_pick.py`, on `wing_search.select_legs`) serves
  both, so the summary is the grid's (0.20, 30-day) cell. Known inconsistency: the chance below the
  strike uses r = q = 0 (ADR 0053), the IV behind it is inverted with the session's rate and yield;
  they differ by about 0.01 at 30 days.
- **Earnings pricing (V8):** the options-priced move at the expiry after the report, the past 12
  reports' moves and "options overpaid N of M" over `earnings_reaction@v2` and the chain; a TOML
  expression where it is a formula, else a feature group (architect).
- **IV rank** reads `iv_history@v2` (provisional after 60 sessions; chains stored from 2026-10-02, so
  UNKNOWN with its reason until about late December); the IBKR rank stays `personal`. No new source
  is bought (data tenet).
- **Setups that picked a name** (V3, V5): the inverse reads (setup to picks, instrument to setups)
  live in a new module under `services/read/ideas/`, not in `pick_edges.py` (E9 edits it), reading
  `results/edge_picks` through `pick_edges.py`'s public functions.

## 5. Vertical slices
Each row is one PR (or two where marked), working end to end. Components by section 3 id; the U0
session builds them in the order of the first slice that needs each.

### Share screens on data that exists today
| Slice | Screens | Components | Route / page | Read or write | Guide | Replaces / deletes | Needs | Review |
|---|---|---|---|---|---|---|---|---|
| V1 Shell, search, Guide | top bar, Search, footer, GuideHome, GuideEntry, HelpDrawer, Methodology | C1, C2, C3, C13, C20 | `src/app`: bar Ideas, Setups, Test, Calendar; Explore and Regime off the bar; `/screeners` list redirects to `/test` once V9 lands; `features/guide-search` becomes the global ⌘K; `pages/guide` restyled; Methodology as Guide start pages in `DocLayout` | `guideSearch` gains ticker and setup groups (its existing loader) | risk statement, methodology and conflicts entries (ADR 0083 decision 4), Setups, Test | the bar's Screeners and Explore tabs; `features/ticker-search` folded into ⌘K; `widgets/guide-home`, `guide-start` regrouped | U0: C1-C3, C13, C20 | own |
| V2 Setups list and share setup page | Setups, Setup | C4-C11, C13 | `pages/trader-edges`: library (Start here, grouped by verdict, Follow) and the setup page (rules, how it has done, when it fails, ideas tonight, before you act, dig deeper) | existing `edgeList`, `edgeDesk`, edge evidence reads; "ideas tonight" from V3's inverse read (a later PR of V2 if V3 is not merged) | verdict groups, before you act, every column header | `widgets/edge-list`, `edge-detail`, `edge-performance`, `edge-sureness` merged into the sections; leftovers deleted | U0: C4-C11 | own |
| V3 Ideas from stored picks | Main (Stocks and Premium tabs), OptPremiumList layout | C4-C6, C9, C10 | `pages/trader-ideas` rebuilt: tabs (`?tab`), setup groups, idea rows in `MasterDetail`, Unproven per tab, regime pill; the Premium tab is Unproven until an option setup qualifies | `services/read/ideas/` (new folder, `add-responsibility`: id `ideas-setup-picks`; `ideas-list` in `services/read/screens/ideas.py` narrowed to Unproven; folder in `architecture/layout.toml`): ADR 0083 decision 2 per tab (basis screener's picks of `works` / `promising` setups, one ranking rule, licence filter on the run's `field_licences` and on the verdict's evidence licence through E1's gate (#991, merged) in `pick_edges.py` / `cross_section/detail/licences.py`, consumed, never re-implemented in `services/read/ideas/` (a verdict judged on the bought history is personal, ADR 0088 decision 12), cap 15 per tab, Unproven per tab, left-out counts by reason); tab from `position_of`; a screener behind setups of both kinds appears in both tabs' Unproven; the watchlist filter after the cap (from V7; until then none), and left-out counts never count names the watchlist hides; `Query.ideas` gains `tab` | Unproven, tabs, left-out reasons; ADR 0083's wording fitness test | today's pool list as the main list (kept only as Unproven); `widgets/top-ideas`, `ideas-heading`, `paused-ideas` generalised or deleted | T-basis (#1011, merged); U0: C4-C6, C9, C10 | **architect** (PIT, licence, new read object and responsibility) |
| V4 Share idea page | IdeaStock | C4, C5, C7, C8, C13 | `pages/trader-idea` `/ideas/$symbol?setup=` (default: the pick's best setup) | `IdeaDetail` read object in `services/read/ideas/detail.py`, `Query.idea`: why it is here, the historical exit rule, evidence, what could go wrong, learn this setup | each section | `widgets/pick-detail` generalised into the sections | V3 (folder), E12a (exit section; until it merges the section is UNKNOWN with its reason), U0: C7, C8 | **architect** (read object) |
| V5 Ticker page | Ticker | C4, C8, C10, C11 | `pages/trader-explore` detail restyled (`/explore?symbol=`, route unchanged): where it stands (setups that picked it), avoid-list checks, next report, tabs | `Instrument.pickedBy` (V3's inverse read), existing feature reads | where it stands, avoid-list checks | `DetailTabs`, `OtherTabs` regrouped, never copied | V3; U0: C11 | own |
| V6 Yield grid | OptYieldGrid | C12, C20 | ticker sub-nav (Where it stands, Options, Roll a put, Calls on shares, Buying power) in `pages/trader-explore`; `widgets/option-grid` | the option grid (section 4: architect picks the grain first), derived figures only | every figure on the grid | `widgets/options-panel` leaves the trader view (admin-only with the live route) | V5 (ticker page); U0: C12 | **architect** (grain, `quant/`) |
| V7 Watchlist and preferences | Onboarding, Settings, Watch toggle | C15, C16 | `pages/settings` (account menu: theme, default tab, watchlist, country read-only, sign out), `pages/onboarding` (first signed-in visit with no `[ideas] default_tab`), `features/watchlist` (Watch toggle on the idea and ticker pages) | `services/authoring/preferences.py`: `[watchlist] instruments` (max 50, through `SymbolResolver`) and `[ideas] default_tab`; one loader in `services/read/users/` and one field `Query.traderPreferences`; `PUT /preferences/watchlist`, `PUT /preferences/ideas` in `read_your_writes.toml` with tests that Ideas reflects the write; the ADR 0077 response-cache key of `Query.ideas` includes the preferences hash | watchlist, default tab, the sign-up question | `widgets/theme-choice` moves into Settings | U0: C15, C16 | **architect** (new responsibility `watchlist`, user data, cache key) |
| V8 Calendar and Regime | EarningsWeek, Regime | C9-C11 | `pages/trader-calendar` (Earnings week, Next 90 days, Macro), `pages/trader-regime` restyled | existing event and regime reads; the earnings pricing features (section 4) in this slice, UNKNOWN until their first nightly | new columns | `widgets/event-calendar-panel`, `regime-*` regrouped | U0: C9-C11 | own (architect if a feature group) |
| V9 Test flow | CreateStart, CreateGuided, CreateExpert, TestResult | C14, C15, C17, C19 | `/test` route group (start, guided, expert, result); old builder URLs redirect; `pages/screener-builder` and `pages/edge-builder` merged into `pages/test` | existing writes (user screener config, user edge document) and the on-request evaluation | the four ways in, steps | `pages/trader-screeners` (redirect), the two builder pages | V1; U0: C14, C15, C17, C19 | own |
| V10 Describe it | CreateDescribe | C17, C18 | `features/screener-describe` restyled into the Test flow | `suggestions` removed (ADR 0083 decision 4: prompt, schema, `ScreenDraft`, REST, web) | part statuses | the Builder's "Suggested" group | V9 (route); U0: C18 | own |
| V11 Calculators (two PRs: roll and calls, then buying power) | OptRoll, OptCalls, OptMargin | C19 | three ticker sub-pages in `widgets/option-calculators`; typed figures in component state only | `services/preview/options/` (new folder, declared, tests mirrored): `roll.py`, `calls.py`, `margin.py` (Reg-T is a broker rule: it stays here, only payoff maths in `quant/`); `POST /preview/options/{roll,calls,margin}`, body only, excluded from request logs and caches (a test) | every input and figure | - | V6 (sub-nav, the chain read) | **architect** (new folder, `quant/`) |
| V12 Admin (two PRs) | AdminNightly, AdminEvaluations, AdminUsers, AdminAI | C4, C5, C9-C11 | the four admin pages on the new skeleton | existing admin reads; a tile with no read gets one (`add-graphql-field`) | new tiles | old admin layouts | U0: C4, C5, C9-C11 | own |

### Option-setup screens, following the options backend
| Slice | Screens | Adds to | Waits on (backend-build.md) | Review |
|---|---|---|---|---|
| O1 Option setup page | OptSetup | V2's setup page: rules for option legs, evidence on collateral, kept premium, costs at mid / worse side, stress episodes, by year | E4 (`structure_pnl@v2`), E6a / E6b (trade contract and measures), E11 (ledger and evidence) | own |
| O2 Setup state chip | Setups, Setup, Ideas | the state chip (ADR 0088 decision 16) on V2 and V3 | E10 | own |
| O3 Premium picks | Main (Premium tab), OptPremiumList | V3's Premium tab: option rows (example put, collateral, chance of assignment); the licence filter on the evidence licence applies | E9 (picks, example position), E10, E1 (licence gate, merged) | **architect** (PIT, licence) |
| O4 Option idea page | IdeaOption | V4's sections for an option pick: example position, declared exits, most you can lose per contract, "the setup's rule holds Monday at a premium of $X or more" | E9, E12b | **architect** (PIT) |

Until an option setup has a stored `works` / `promising` verdict (not before 2027-01-26), the
Premium tab is its Unproven section; history-derived evidence is owner-only (ADR 0088 decision 12).

## 6. Order and parallel start
```
U0 (running; builds C-ids in this order: C1-C3, C13, C20 | C4-C11 | C12 | C15, C16 | C14, C17-C19)
V1 ─ V9 ─ V10                      V7 (C15, C16) ─ filter in V3 (a follow-up PR of V7)
V2 ─────────────── O1 (E4, E6b, E11), O2 (E10)
V3 ─┬─ V4 (E12a) ─ O4 (E9, E12b)
    ├─ V5 ─ V6 ─ V11
    └─ O3 (E9, E10; E1 merged)
V8, V12 any time after their components
```
**Start now** (beside the running U0 session, file-disjoint): **V3** (Ideas read and page, the long
pole), **V2** (Setups), **V1** (shell and search), **V7** (preferences: server first, web when C15 / C16
land), **V6's grain decision** (architect, a short doc in the slice, then the build after V5). Each
web part starts as soon as its components merge; a slice may stub a component behind its existing
version and swap it in a follow-up PR.

Folder order: `services/read/ideas/` V3 -> V4 -> O3 / O4; Ideas page V3 -> O3; setup page V2 -> O1,
O2; ticker page V5 -> V6 -> V11; `pick_edges.py` is E9's (V3 only calls it). E12a waits on T-basis
(merged) and E2; V4 waits on E12a for one section only.

## 7. Done means
Every trader screen of the canvas (bar Pricing, Past lists, the "Yours" tab and the premium strategy
tests) is live on the new skeleton, the old page each replaced deleted in its slice, `make web-check`
and the phone e2e project green, each new word in the Guide with coverage baselines shrunk, and no
raw vendor quote on a trader screen (a fitness test in V6 over the trader GraphQL operations).
