# Guide quality: what customers praise, what Stripe does, and the standard for this app

Research note, 2026-10-10 (read-only; WebSearch + WebFetch, URLs below). Complements
`docs/ui/guide.md` sections 1-2 (where help lives, its IA); this note is about the QUALITY of
the writing and how to enforce it. Caveat up front: Reddit is poorly indexed by the search
tools, so customer voice comes through an aggregator of 196 Reddit reviews (GummySearch),
review sites (StockBrokers.com, NerdWallet, Bankrate, Finder), Trustpilot and a trading forum
(NexusFi); the Twilio writers' guide PDF was font-encoded and only its headings were readable.

## 1. Comparison: what customers single out

| Product | Praised for | Complained about | Source |
|---|---|---|---|
| **tastytrade / tastylive** | The best-rated options platform in the Reddit sample (4.5/5); "excellent educational resources"; "intuitive user interface" for newcomers; a free, deep, options-first curriculum (courses by level, daily shows). | Thin research; marketing ties (tastylive is a paid marketing agent of the broker); **stale guidance**: a NexusFi user found 2016 videos still recommending a trade the 2017 shows said not to do, and asked them to fix the old material. | GummySearch; Finder; Bankrate; NexusFi p=347081 |
| **Schwab / thinkorswim** | "contextual education": tutorials built into the platform, not a separate library; paper money to practise; the Studies Library reference. | "Extremely confusing and non intuitive for a beginner" (Trustpilot 1-star cluster); support told a user the platform was "too complex" for a manual and pointed at videos; thinkScript reference "sparse" on examples. | StockBrokers.com guides index; ch.trustpilot.com/review/thinkorswim.com; NexusFi p=610410, p=838053 |
| **Fidelity** | #1 Research and Education 2026 (StockBrokers.com); Learning Center called the most comprehensive free resource at a US broker. | Education not linked back into the tools (see guide.md section 1). | stockbrokers.com/annual-broker-review; investormint |
| **E*TRADE** | NerdWallet's pick for investor education: webinars, videos, articles. NerdWallet scores education inside "customer service" (30%): "ease of finding information, and educational support". | | nerdwallet.com/best/investing/online-brokers-for-beginners; awards methodology |
| **Robinhood** | "easiest to use"; "packed with educational resources" (StockBrokers.com 2025). | "like the Wild West": options with no risk education; Greeks display "thin"; regulators and a lawsuit forced it to add options education and experience gates. | GummySearch; purepowerpicks; investmentexecutive.com |
| **Webull** | "simplest trading". | "order type confusion, particularly around options": wrong limit/market, wrong expiry: the screen did not explain the choice at the point of choice. | GummySearch; unstar.app 2026 analysis |
| **IBKR** | "the best" once learned; Campus courses with quizzes. | "old school interface"; the learning is outside the product. | GummySearch |
| **Public.com / Stake** | A one-sentence "Why is it moving" per stock (Public via Benzinga's WIIM API; Stake's own, 2026): the "why did this happen" explanation in place. | Vendor editorial, not the product's own reasoning. | benzinga.com/apis/cloud-product/bz-why-is-it-moving; cfotech.com.au Stake story |

### What the praise and the complaints have in common

- **Praise** is for: plain language for newcomers; explanation at the point of use ("contextual
  education", hover Greeks, "why it's moving"); worked examples and practice (paper money); a
  curriculum with an order; honesty about risk.
- **Complaints** are for: jargon and "non intuitive" screens; help that lives outside the
  screen (videos instead of a manual; a Learning Center with no way back into the tool); a
  choice the screen did not explain (Webull's order types); **out-of-date advice that
  contradicts newer advice**; education that is marketing in disguise (affiliate copy,
  "an options trader's dream"); risk left unexplained (Robinhood).

## 2. How Stripe (and Twilio, Plaid) get the quality

| Practice | What Stripe does | Source |
|---|---|---|
| **Audience first** | Larry Ullman (Stripe technical writer, Write the Docs 2018): the mark of a strong writer is asking "Who is the audience?"; users "have problems and need solutions", so each page maps a solution to a problem. | knowledgeowl.com/blog/posts/code-examples-shine-like-stripe |
| **Culture, not a docs team** | Dave Nunez (ex Head of Docs): culture change is "the highest leverage investment"; one docs line on every level of the engineering ladder; docs assessed in performance reviews; templates and onboarding classes so engineers never face a blank page; "doc star of the week". | mintlify.com/blog/stripe-docs; review.firstround.com/articles/david-nunez |
| **Measured by time-to-task, not pageviews** | "The best measure is the time it takes to accomplish" the task (test charge: cut ~4x); support contact rate second; pageviews, bounce, CSAT "much less meaningful on their own". | calyx.substack.com/p/mediocre-docs-are-sabotaging-your |
| **What makes docs mediocre** | Written "for machines or for people that don't exist"; walls of text; heavy inline linking (Stripe replaced it with **hover definitions and a glossary**); exhaustiveness ("Don't be afraid to delete or trim pages!"); neglected getting-started flows, fixed with a friction log. | same |
| **Every field, every enum value described** | The API reference gives each attribute a type line + a description that says *when it is set* ("Populated when `status` is `canceled`...", "`null` until confirmation is attempted"); every enum value gets its own line, even the obvious ones ("`succeeded`: The PaymentIntent has succeeded."); a field that sends you elsewhere links the guide. | docs.stripe.com/api/payment_intents/object |
| **States get "what happens next"** | The lifecycle page is a table, one row per state: how you get there, what you do, where it goes next, what happens on failure ("returns to `requires_payment_method` so that the payment can be retried"), what cannot be undone. The reference says *what*; the guide says *so what*. | docs.stripe.com/payments/paymentintents/lifecycle |
| **Terms defined on first mention, inline** | A term's definition is rendered inline in parentheses at its first use on a page (3D Secure, asynchronous payment method, default API version), the hover-definition pattern Nunez describes. | same pages |
| **Error docs = cause + fix** | One table row per error code: what happened, then the action ("Use a lower amount and try again"; "Obtain your current API keys from the Dashboard"), linking the guide where the fix is longer; the error carries `doc_url` to its own row. Plaid: errors carry `documentation_url` and `suggested_action`; its 2020 rebuild moved the error-code breakdown out of support emails into the docs. | docs.stripe.com/error-codes; rubydoc Plaid::PlaidError; plaid.com/blog/new-plaid-docs |
| **Versioned, dated changelog** | Every API version is a date + codename; each change is a row with affected products, **Breaking / Non-breaking**, category; integrations pin a version; the lifecycle page notes renamed enum values per version. | docs.stripe.com/upgrades; docs.stripe.com/changelog |
| **Content validated in CI** | Markdoc: every tag has a schema (attributes, allowed children); validators check internal links resolve and heading-level rules; run in CI and in an editor extension while typing. Reviewed as code. | stripe.dev/blog/markdoc |
| **Examples are generated and tested** | Code samples follow a code style guide (naming, quotes, indentation), are generated from templates and tested in all languages; "copy-and-paste ready". | knowledgeowl interview |
| **Twilio** | Writers' guide headings: Be code wise, Be global, Be clear, Be audience aware, Be active, Be informal, Be organized, Be consistent; present tense, active verbs; readers "arrive with a specific question"; Developer Education team edits engineers' drafts; AI prompts that review a page against the style guide and "simplify jargon" are open-sourced. | smittytone.net/portfolio/Twilio.Documentation.Writers.Guide.pdf; twilio.com/en-us/blog/developers/open-source-docs-ai-buddy-prompts |
| **General** | Describe all enum values "even if they seem self-explanatory"; an error message says what went wrong, what will happen next, a realistic fix. | mintlify GitBook guide on enums; learn.microsoft.com UWP writing style |

### Patterns

1. **Reference says what, guide says so what.** The same status appears twice: a one-line
   value description in the reference and a lifecycle row (how you got here, what to do, where
   it goes next). Our analogue: a glossary term per status plus the Start page that walks it.
2. **Nothing public is undescribed.** Every field and every enum value has its own sentence,
   including the obvious ones; the description says *when the value is set or null*.
3. **Define the word where it is used**: hover definition and glossary beat links to other pages.
4. **Every gap carries its fix**: an error row is cause + action + link; our caveats already end
   with "what to check instead" and `Unavailable` kinds already map to a Guide term.
5. **Quality is a schema plus CI**, reviewed with the code; the writing rule that cannot be
   checked is a template plus a review question.
6. **Dated and versioned**: content names the version it describes; stale advice is the
   complaint customers remember (tastylive 2016 vs 2017).
7. **Measure time-to-task and support questions, not views**: for us, the questions the owner
   asks a session about a screen are the friction log.

## 3. The standard for this app

### (a) Writing checklist (glossary term, Start here page, field entry)

1. **Reader named**: written for someone who does not follow markets; the term they would type is the title (`term`), the app's exact label is used nowhere else.
2. **Short is one sentence, at most 25 words**, the hover and the drawer's first line, no comma-chained clauses.
3. **Says what the value or state means AND when it is shown**: a `reads` starts with unit and range, low to high; a state term says what put the page in that state and what it is not (NOT_RUN is not UNKNOWN).
4. **What happens next**: a state or status term has a sentence on what the app does next or what the reader should do (retry tonight, pick a date, ask the owner).
5. **A worked example**: a field entry has at least one `[[field.use]]` (intent, op, value); a term for a rule word has a one-line rule in the grammar; a Start page section names a page element the reader can go and look at.
6. **When it lies**: every field has at least one caveat ending with what to check instead (a catalogue name or a situation); a term for a statistic (win rate, lift) says the sample size below which it is noise.
7. **Every catalogue name, term and link resolves**; a term used in a body that has its own entry is in `see_also` (no orphan jargon).
8. **No marketing, no hedging filler**: no "simply", "just", "easy", "powerful", "robust", "leverage (verb)"; no exclamation marks; no advice ("buy", "sell", "should trade").
9. **Active voice, present tense, second person** for what the reader does, "the app" for what the app does; sentences at most 30 words.
10. **Source and version**: a field entry cites its `sources`; a threshold names where it comes from; the entry names the feature `name@version` it describes, and the page shows the entry's last-reviewed date.
11. **One idea per section**: a Start page section is one paragraph under a question-shaped or verb-shaped title; a page has at most 7 sections and ends with `links` to read next.
12. **Honest about risk**: a playbook or Start page that leads to a trade says what the screen does not check and the loss case, before the hit case.

### (b) Fitness tests over the TOML (proposed; per-value terms ship as `tests/architecture/guide/`, the style checks are a follow-up)

| Check | Rule | Status |
|---|---|---|
| `short` is one sentence | one terminal `.`/`?`, no `;` | exists (glossary) |
| `short` <= 25 words; every sentence in `body` / `reads` / `caveats` <= 30 words | word count split on `. ` | new (bullets 2, 9) |
| Every public status value has its own term | every `UnknownCode` served as a public kind, every `NewerState`, every screener `status` and ingestion step state maps to a `[[term]]` id (today: 5 `unavailable_*` terms, `not_run`, `paused`; assert the full enum) | new (bullet 3) |
| State terms carry "next" | a term whose id is in the state set has a `next` key (one sentence) or its `body` contains a sentence starting "Then" / "Next" / "The app"; schema key preferred | new (bullet 4) |
| Field has example + caveat + source | each `[[field]]` has >= 1 `use`, >= 1 `caveats`, >= 1 `sources` | partly (use validated); new for counts |
| Caveat ends with a check | each caveat's last sentence names a catalogue field, a `situation` or "see" | new (bullet 6) |
| Banned words | the list in bullet 8 fails on `short`, `body`, `reads`, `summary`, section `body` (case-insensitive, whole word) | new |
| No orphan jargon | every glossary `term` string that appears in another entry's body is in that entry's `see_also` (or a Start page's `links`) | new (bullet 7) |
| Version named is current | a `name@vN` in prose is the catalogue's latest version (playbooks already check `asks` vs latest) | extend |
| Reviewed date | each `[[term]]` / `[[page]]` / `[[field]]` has `reviewed = YYYY-MM-DD`; a fitness test lists entries older than 180 days as a warning, and fails when a feature version bumped after the date | new (bullet 10) |
| Section caps | a Start page has <= 7 sections, each body one paragraph (no blank line) | new (bullet 11) |
| Readability | a Flesch-Kincaid grade estimate (syllable heuristic in the test, no dependency) <= 10 on `short` and `summary` | new, advisory first |

Keep these in the existing test modules (layout cap: `tests/unit/config/site/guide/` holds 4 modules; a `test_style.py` shared by the three kinds fits).

### (c) Process rules

- **Content ships in the PR that ships the feature.** A PR that adds a public status value, a
  catalogue feature, a page element with a help button or a rule word adds its Guide entry in
  the same PR; the fitness tests in (b) are what makes this fail CI, not a reviewer's memory
  (Stripe: validators in CI; Nunez: expectation on the ladder, not a docs team).
- **Docs reviewed like code**: the PR template gets a "Guide" block: entries added/changed,
  which checklist bullets the reviewer read for (3, 4, 6, 8, 12 are the judgment calls the
  tests cannot make), and the screen the entry is opened from.
- **Reviewer questions** (the five the tests cannot answer): Could the owner's non-market friend
  read it? Does it say when the number is shown and when it is not? Is there a "then"? Does the
  caveat tell me what to look at instead? Is there any sentence that sells?
- **Trim, do not accumulate**: an entry nobody opens from a screen is deleted when its button
  goes (Nunez: "Don't be afraid to delete or trim pages!"); the coverage test already fails on
  a reference that does not resolve; add the reverse (an entry no screen or page links) as a
  warning list in `make features-doc`.
- **Friction log as the metric**: a session that had to explain a screen to the owner in chat
  records it via `capture-learning` as a Guide gap; `/review-sessions` counts them. Time-to-task
  (owner reads a screen without asking) is the goal; views are not tracked.
- **Dated advice**: `reviewed` is bumped only after a reread; a changed threshold changes the
  entry and the date together (the tastylive 2016/2017 contradiction is the failure to avoid).

## Sources

- https://gummysearch.com/tools/best-products/options-trading-platform/ (196 Reddit reviews, 18 subreddits)
- https://www.stockbrokers.com/annual-broker-review ; https://www.stockbrokers.com/guides?page=1 (Schwab "contextual education")
- https://www.nerdwallet.com/best/investing/online-brokers-for-beginners ; https://www.nerdwallet.com/l/awards-investing-methodology-best-broker-for-beginning-investors-2026
- https://www.bankrate.com/investing/brokerage-reviews/tastytrade ; https://www.finder.com/stock-trading/tastytrade-review
- https://nexusfi.com/showthread.php?p=347081 ; https://nexusfi.com/showthread.php?p=610410 ; https://nexusfi.com/showthread.php?p=838053
- https://ch.trustpilot.com/review/thinkorswim.com ; https://unstar.app/blog/stock-trading-app-reviews-robinhood-webull-fidelity-etrade-2026
- https://purepowerpicks.com/robinhood-review/ ; https://www.investmentexecutive.com/?p=16585
- https://www.benzinga.com/apis/cloud-product/bz-why-is-it-moving/ ; https://cfotech.com.au/story/stake-adds-portfolio-chart-stock-move-explainers
- https://mintlify.com/blog/stripe-docs ; https://review.firstround.com/articles/david-nunez/ ; https://calyx.substack.com/p/mediocre-docs-are-sabotaging-your
- https://www.knowledgeowl.com/blog/posts/code-examples-shine-like-stripe (Larry Ullman, WTD 2018)
- https://stripe.dev/blog/markdoc ; https://docs.stripe.com/api/payment_intents/object ; https://docs.stripe.com/payments/paymentintents/lifecycle ; https://docs.stripe.com/error-codes ; https://docs.stripe.com/upgrades ; https://docs.stripe.com/changelog
- https://smittytone.net/portfolio/Twilio.Documentation.Writers.Guide.pdf ; https://www.twilio.com/en-us/blog/developers/open-source-docs-ai-buddy-prompts
- https://plaid.com/blog/new-plaid-docs/ ; https://preview.rubydoc.info/gems/plaid/Plaid/PlaidError
- https://www.mintlify.com/GitbookIO/public-docs/api-reference/guides/describing-enums ; https://learn.microsoft.com/windows/uwp/design/style/writing-style
