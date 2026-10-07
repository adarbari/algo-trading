# The Guide: the app's learning area (spec)

Spec for ADR 0051; owner-approved mockup 2026-10-07 (https://claude.ai/artifact/1HSXjM1zsiKzTe6fak8ieZ).
Sections 1 and 2 are the research note of 2026-10-07; section 3 is the design as decided,
section 4 the migration of today's explanations, section 5 the rule and its checks, section 6
the phases. How to add or move content: `.claude/skills/add-guide-content`.

Research note, 2026-10-07. Read-only survey (WebSearch + WebFetch; Investopedia, Morningstar's
glossary index, IBKR's glossary and Robinhood article pages refused the fetcher, so those rows
mix a fetched index with page templates recalled from use, marked "recalled"). The question:
the field guide (about 450 catalogue fields, each with reads / criteria per intent / caveats /
sources, `config/site/field_guide/*.toml`) is today a tab inside Explore, a per-ticker page.
Where should education live, how should it be structured, and how should it hook back into
the product?

## 1. Comparison

| Product | Placement | Information architecture | Single-term page template (sections in order) | Search | Links back into the product | In-context help |
|---|---|---|---|---|---|---|
| **TradingView** | Three separate properties: Help Center `tradingview.com/support/` (knowledge base), Pine docs `tradingview.com/pine-script-docs/`, and Ideas > Education (`/ideas/?type=education`, community). | Help Center: Knowledge base > Indicators > Built-in Indicators > one article per indicator (breadcrumb on the RSI page `support/solutions/43000502338`). Pine docs sidebar: Welcome, Primer, Language, Visuals, Concepts, Writing scripts, Errors and warnings, FAQ, Release notes, Migration guides: concepts and language reference kept apart. | RSI article: Definition, History, Calculation, The basics, What to look for (Overbought/Oversold, Divergence, Failure swings), Cardwell's trend confirmations, Summary, **Inputs** (RSI Length, Source, Calculate Divergence, Smoothing). Reference material (inputs) sits at the bottom of a concept page. | Help-center search box; prev/next links inside the Indicators category ("Previous: Receiving addresses / Next: Relative Vigor Index"). | A "Launch Supercharts" call to action on every indicator article; "Also read" block (How to trade on TradingView, Technical analysis essentials...). In the chart, the Indicators dialog shows a description per built-in and the status line's menu opens the same article (recalled). | Indicator settings dialog with Inputs / Style / Visibility tabs; per-input tooltips; in-chart description rather than a separate docs trip. |
| **Investopedia** (recalled; fetch refused) | Separate site; the whole product is the dictionary: `investopedia.com/terms/<letter>/<slug>.asp`, A-Z index. | Breadcrumb by topic (Technical Analysis > Technical Analysis Basic Education); the same term page serves beginner and practitioner by section order. | "What Is X?", **Key Takeaways** box, formula / "How to calculate", "What does X tell you?", example, "X vs Y", **Limitations of X**, FAQ ("Is a high X good?"), "The Bottom Line". Related terms in a sidebar; every first mention of a term is an inline link. | Site search; the A-Z and topic hubs. | None (no product). | None; the inline links are the help. |
| **Robinhood Learn** | `robinhood.com/us/en/learn/`: a top-level marketing-site section, separate from the app. | "Investing 101" (guided, ordered), "Options Trading Essentials", a Library of 800+ articles and a dictionary of "investing lingo"; by level (beginner first) rather than by theme. | Article (recalled): one-line definition up top, "Understanding", "Example", "Takeaway", "What is / How does" FAQ-style subheads, "Ready to start investing?" CTA. | Site search. | CTA to open the app; in the app, term cards link out to Learn (recalled). | Short definitions surfaced in the app (recalled). |
| **Fidelity Learning Center** | `fidelity.com/learning-center/` on the main site; a Technical Indicator Guide at `learning-center/trading-investing/technical-analysis/technical-indicator-guide/<NAME>`. | Topics: Mutual Funds, ETFs, Fixed Income, Options, Options Strategy Guide, Stocks, Technical Analysis, Fundamental Analysis, Trading, **Technical Indicator Guide** (filters "By Indicator Type" and "By Class"), Tools & Demos, Webinars. | Indicator page (RSI): Description with the 70/30 reading and divergence diagrams, formula inline, then marketing blocks. No related indicators, no product link. | Site search; the guide's two filters. | Weak: no "open in Active Trader Pro". | Not applicable. |
| **Schwab / thinkorswim** | Two: `schwab.com/learn/topic/<topic>/` (articles by topic: Trading, Options, Trading tools) and the thinkorswim Learning Center `toslc.thinkorswim.com/center/` (platform docs). | Learning Center nav: thinkManual (how-to), thinkScript (language), **Technical Indicators** reference with a **Studies Library** (alphabetical A-B, R-S...) and a Strategies Library, Glossary, FAQ, Release notes. How-to, reference and glossary are separate trees. | Study page (RSI, `reference/Tech-Indicators/studies-library/R-S/RSI`): Description, **Input Parameters**, **Plots**, Example; then "Related Studies" (RSICrossover), "You may also like", and links to the maths it depends on (Wilder's Moving Average...). | Learning Center search; A-Z. | The platform's Edit Studies dialog shows each study's description beside the list, so the reference is read in place (recalled). | Study description panel in the dialog; per-input tooltips. |
| **Interactive Brokers** | IBKR Campus at `interactivebrokers.com/campus/` (eight "pillars": Traders' Academy courses, Traders' Insight, podcasts, webinars, quant, glossary `campus/glossary-terms/`). | Courses by audience and product (Introduction to Charts, Risk Navigator), each a short video + study notes + quiz; a glossary alphabetical, each term with cross-links to lessons. | Lesson: video, notes, quiz. Glossary term: definition + related lessons. | Campus search. | Platform tutorials per tool; TWS has "?" help per window (recalled). | Per-window help. |
| **tastytrade / tastylive** | tastylive `tastylive.com/learn` (courses: Beginner Options, Implied Volatility, Beginner Futures), `tastylive.com/concepts-strategies/<term>` (reference), FAQ / Glossary / Help Center in the footer; tastytrade `courses.tastytrade.com` for platform how-to. | Concepts & Strategies is a term/strategy reference by category (Options Greeks under Options Trading Fundamentals; strategies such as Iron Condor, Jade Lizard); courses are by level. | Delta page: What Is Delta?, What Are the Greeks?, How Does Delta Work, Long vs Short, **Example**, **FAQs** (six Q&As); a numbered table of contents at the top. | Site search. | "Open a tastytrade account" CTA; the platform's trade page shows Greek labels with hover definitions (recalled). | Hover definitions on the platform. |
| **Koyfin** | Help center at `koyfin.com/help/` (left nav: Getting Started, Functionality (50+ feature articles), How do I, Mobile App, Integrations, Release Notes) plus a **Data Dictionary** `koyfin.com/help/koyfin-data-dictionary/`. | How-to and reference are separate; the Data Dictionary is alphabetical (Alpha ... Z-Score), no categories. | Dictionary entry: Definition, **Formula** (e.g. Buyback Yield % = (Issuance + Repurchase) / Market Cap), calculation notes and exclusions, a screenshot example (Apple, Bank of America), **source attribution** (Morningstar, Capital IQ) and update cadence ("every 2 weeks"). | Help search; the dictionary itself is Ctrl+F only. | Each app section has "Learn more" links to its help article; the command bar ("/") is for tickers, not help. | "Learn more" links per section. |
| **Finviz** | One help page `finviz.com/help/screener.ashx` (Filters, Signals, Other Data). | Flat: every filter is a heading in the order of the screener. | Per filter: name, 1-2 sentence definition with the reading ("Low P/E ... relatively cheap"), formula as code, metadata line (Sorting / Export / Appearance). Signals: name, short description, scope ("Top 200 stocks"). | Browser find. | Same names and order as the screener form; filter labels in the screener link to the help entry (recalled). | None beyond that. |
| **Morningstar** | Investing Terms `morningstar.com/investing-terms` (alphabetical glossary) and Methodology documents (`/business/insights/research/methodology-documents`, PDFs per rating: Stock Rating, Fund star rating, Style Box, Equity Comparables). | Glossary for readers, methodology PDFs for the "how is it computed" question; the two are not linked at term level. | Glossary term (recalled): definition, why it matters, example, related terms. Methodology: scope, formulas, procedures. | Site search. | Data-point hover on fund pages shows the glossary definition (recalled). | Hover definitions. |
| **Stripe Docs** (benchmark) | `docs.stripe.com`, its own origin; also `stripe docs` in the CLI and `.md` versions of every page. | Start here (use-case quickstarts) / Browse by product / API reference: tasks first, reference apart, one sidebar. | Guide: goal, steps with code (language switcher), right-hand on-page TOC, "Was this page helpful". | Cmd+K search with AI answers; every page has a stable URL. | Deep links from the Dashboard into the matching doc; docs link into the Dashboard ("Test mode"). | Dashboard side panels. |
| **Linear Docs** (benchmark) | `linear.app/docs`, one sidebar: Getting started, Intake, Projects and initiatives, Issues and cycles, Coding and review, Agents and automation, Insights and outcomes, Working in Linear, Administration, Integrations, Imports and Exports. | By job-to-be-done, with "Popular" and "Linear basics" on the home. | Short page: what it is, how to use it, keyboard shortcut, tips. | Cmd+K search in app and docs. | "?" / Help menu in the app opens docs and the shortcut sheet. | Shortcut sheet; contextual help menu. |

## 2. Patterns among the best

1. **Three kinds of content, kept apart but linked**: *reference* (one page per indicator or
   metric: thinkorswim Studies Library, Koyfin Data Dictionary, Finviz filter list),
   *concepts and how-to* (TradingView Help Center, Linear docs, Stripe guides) and *courses /
   playbooks* (tastylive, IBKR Academy). Nobody mixes them in one list; everyone cross-links.
2. **The reference entry has a fixed template** and the same order everywhere: definition
   with the low-to-high reading, formula / inputs, how to read it (thresholds), example,
   limitations ("when it lies": Investopedia's Limitations section, our caveats), related
   entries, source. Koyfin adds source vendor and update cadence; Finviz adds where the field
   appears (Sorting / Export / Appearance).
3. **Reference is read in place**: thinkorswim's Edit Studies description panel, TradingView's
   Indicators dialog, Koyfin's "Learn more" per section, Morningstar's hover definitions.
   The full page exists for depth; the product shows the first paragraph where the user is.
4. **Every entry is a URL** (Investopedia `/terms/r/rsi.asp`, thinkorswim `.../R-S/RSI`) so
   tables, tooltips, drafts and PRs can point at it.
5. **Browse by category, find by search**: Fidelity's "By Indicator Type / By Class"
   filters, thinkorswim A-Z, Koyfin alphabetical; Stripe and Linear make Cmd+K the primary
   entry and the sidebar the secondary one.
6. **Links out of the reference back into the product** are where most financial sites are
   weak (Fidelity has none; TradingView has only "Launch Supercharts"). The ones that work
   are precise: thinkorswim "Related Studies", Stripe's Dashboard deep links, Finviz's
   one-to-one naming between the help page and the screener form.
7. **Playbooks are strategies, not fields**: tastylive's Concepts & Strategies (Iron Condor
   with its rules), IBKR courses with quizzes. A strategy page names its fields and the
   criteria, i.e. exactly what the eight preset screens already encode.


## 3. The design (owner decisions 2026-10-07)

### Placement

A **utility link on the right of the top bar**: book icon and "Guide", before the session date
and the account menu, in both workspaces (no role gating). `?` opens `/guide`, ⌘K searches it
from anywhere. Not a workspace section (sections are where work happens; Linear, Stripe,
Notion, IBKR and tastytrade keep help as a utility on the right or a "?" button) and not in the
account menu (GitHub and TradingView do that; it is the least discoverable place, wrong for an
app with 399 fields to learn). The drawer is how most users meet the content; the pages are
for depth. The original recommendation (a TRADER section after Explore) was superseded.

### Sections, in order: from the market down to one number

1. **Start here** (how-to, numbered): how the app thinks about a day (session, knowledge time,
   UNKNOWN), read a screen's result (pass, near miss, reject, WATCH, LIQUIDITY_RISK, score),
   build a screen (from a playbook, criteria from a field page, preview), draft a screen from a
   sentence; later: read Explore, read the Regime page.
2. **Market regime**: the eight indicators as their plain-language questions
   (`config/site/regime/cards.toml`), then the reference episodes (`episodes.toml`); a link to
   today's readings on the Regime page.
3. **Playbooks**, one per site preset screen, grouped by family and ordered within it: Trend
   (Trend continuation, Pullback), Breakouts in lifecycle order (Range breakout, Breakout,
   Failed breakout), Reversals (Support reversal, Oversold reversal, Exhaustion), Option
   income (VRP).
4. **Fields**, the themes grouped in the order a screen uses them: who is tradeable
   (instrument gates, liquidity), the chart (momentum and trend, price levels, volume,
   volatility), options (implied volatility, option chain and short strikes, put wing, walls
   and expiries), the company and its calendar (events, fundamentals, episode behaviour);
   plus by intent and A-Z.
5. **Situations**: the `[[situation]]` entries, each with the fields it fools.
6. **Glossary**: the app's own words (session, knowledge time, UNKNOWN vs NOT_RUN, run,
   selection, draft) and the rule grammar (`op`, `mode` hard / soft / score, `tolerance`,
   `on_miss`; from docs/screeners/rules.md). Last: it is a lookup.

Navigation stays compact (a 196 px rail with the search on top; the current section expands to
its themes or families); the content is the hero (the reading paragraph at 18 px, max 68ch).

### The field page (fixed order, every section anchored, "On this page" on the right)

1. Header: display name, `name@version`, theme chip, unit and range, kind (rollup, expression),
   cadence, source vendor, licence.
2. **How to read it** (the guide's `reads`; the hero).
3. **Across the universe** on the resolved session: the distribution, the names passing the
   selected criterion highlighted.
4. **Use it for**: one card per intent (op, value, mode, tolerance, on_miss, note) with **Add
   to Builder** and **Preview hits**.
5. **When it lies**: the caveats, fields they name linked; **Situations that fool it**.
6. **How it is computed**: the formula (expression features) or the inputs (rollup
   parameters), null meaning.
7. **Related fields** and **Playbooks that use it** (derived by the server, ADR 0038).
8. **See it on a ticker**: opens Explore with this field's history.
9. Sources.

### The playbook page

Header (preset id and version, the plain summary as the hero), **See today's hits** and **Open
in Builder** with the last run; "What a hit looks like" beside "What it does not check"; the
criteria table (what it asks in words, the field linked, the rule, what a miss does; the base
gates as one line); "Before you act on a hit" (the caveats of its fields, each attributed) and
the situations; related playbooks. The prose (summary, what a hit looks like, what it does not
check, family) is a Guide source of its own, `config/site/playbooks/<id>.toml`, because a preset
version is immutable; a fitness test requires one per site preset.

### The help drawer

A right-hand drawer (440 px, full height under the top bar, Esc closes) opened by an
`InfoButton` beside the thing it explains. It renders the first sections of the entry (a field:
header, how to read it, use it for with "Add to Builder"; a regime indicator: why it matters,
when it is on, lead time and track record; a glossary term: the definition) and **Open full
page**. A hover on the button shows the entry's first sentence. Search results, links in caveats
and drafter reasons all resolve to the same entries.

### Search

One search over all kinds (name, display name, theme, reads, intent, playbook and situation
names, glossary terms), results grouped by kind, ranked exact name, display name, intent, then
prose; every result is a URL under `/guide`. ⌘K anywhere; the rail's box on Guide pages.

## 4. Migrating today's explanations

Inventory of 2026-10-07. Each row moves in the phase named; the PR that moves it lowers
`architecture/web_prose.toml`.

| Today | Becomes | Phase |
|---|---|---|
| Explore "Field guide" tab and its panels (`widgets/field-guide`, `pages/trader-explore`) | `/guide/fields`, `/guide/fields/<name>`; the tab redirects for one release | 1 |
| Feature table column headers (`widgets/feature-table`, column factories in `entities/feature`), Ideas columns | `InfoButton` in every field header, opening the field's drawer | 1 |
| Builder "How to read it" Disclosure (`features/screener-builder/ui/FieldGuideHelp.tsx`) | `InfoButton` beside the criterion's field; the drawer's "Use this" fills the row | 2 |
| Preset descriptions in TOML comments; Screeners list rows, the Builder header of a preset | playbook pages; a "Playbook" link on every preset | 2 |
| Drafter "Left out ... (reason)" lines (`features/screener-describe`) | the field name opens its drawer, a kept criterion its intent card | 2 |
| Regime cards' "Why it matters, what it did before" Disclosure (`widgets/regime-indicators`), the reading list (`widgets/reading-list`) | indicator pages; `InfoButton` on each card opening its drawer (text stays in `cards.toml`, written once) | 2 |
| Regime "Market falls we compare with" (`widgets/regime-episodes`) | episode pages; a row opens its drawer; the table of live drawdowns stays | 2 |
| Regime "How to read the charts" legend (`widgets/regime-legend`), the history note (`features/indicator-history`) | a Start here page; an `InfoButton` on the chart headers | 3 |
| Explanatory sentences on Ideas paused picks (`widgets/paused-ideas`), regime sizing (`widgets/regime-sizing`), missing data and narrow misses (`widgets/screen-summary`), the funnel's gating (`widgets/screen-funnel`), WATCH / LIQUIDITY_RISK chips, the completeness legend (`widgets/completeness-panel`), the chain's delta band (`widgets/options-panel`) | glossary entries, each opened by an `InfoButton` | 3 |
| Page introductions (Ideas, Results, Calendar, Regime), empty states, dialogs | stay, cut to one sentence under 25 words | 3 |
| Data banners ("not known for this session", "not in the snapshot"), the text-model regime explanation | stay: they describe the session's data; the facts they name open drawers | — |

## 5. The rule and its checks

Explain once, in the Guide; show in place through the drawer (ADR 0051).

- **Structure**: `HelpDrawer` (design system) takes rendered sections; the one feature that
  opens it from a Guide reference (`{ kind, id }`) is the only importer (an ESLint
  `no-restricted-imports` entry with the skill in its message), so no page passes text to it.
- **Content**: `tests/architecture/test_layout_web.py::test_web_prose_matches_the_baseline`
  finds explanatory prose and explainer Disclosures in `apps/web/src` against the shrink-only
  baseline `architecture/web_prose.toml`.
- **Coverage**: fitness tests that every Guide reference in the web code and in config resolves,
  that every site preset has a playbook, every regime card and episode a page, and (existing)
  every phrased or site-screened field a field-guide entry.
- **Process**: `.claude/skills/add-guide-content` (where each kind lives, its owner, how to put
  the button on a page); CLAUDE.md names it in the workflow table.

## 6. Phases (one PR each, design-system first)

- **GD1 (this PR)**: the spec, ADR 0051, the skill, the prose check and its baseline.
- **GD2**: `InfoButton` and `HelpDrawer` in `@algotrade/ui` (`add-ui-component`, stories for
  every state, axe, light and dark screenshots).
- **GD3**: the Guide read model (one loader, `add-domain-object`) with related fields,
  playbooks that use a field and the situations that fool it computed server-side
  (`add-graphql-field`); the top-bar link and `/guide`, `/guide/fields`, `/guide/fields/<name>`
  (`add-web-page`); the Explore tab redirect; the drawer on feature-table headers.
- **GD4**: playbooks (`config/site/playbooks/`, pages, preset links), situations, the Builder
  and drafter hooks.
- **GD5**: market regime pages (indicators, episodes) and the Regime page's drawers.
- **GD6**: Start here, glossary, grouped search behind ⌘K, the remaining migrations, the
  baseline at its floor.

Not recommended: a separate docs site (duplicates the read model and loses session-aware
distributions), a guided tour (the drawer is cheaper and persistent), beginner / advanced
levels as navigation (one user tier; intents are the better second axis).

Sources (fetched for the research): TradingView RSI help article and Pine docs index;
thinkorswim RSI study page and Technical Indicators index; Fidelity RSI guide page and guide
index; Koyfin help index and Data Dictionary; Finviz screener help; tastylive Delta page and
Learn index; Stripe docs home; Linear docs home; Schwab learn topic pages; IBKR Campus press
pages. Placement comparisons in section 3 are recalled from use.
