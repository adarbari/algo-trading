# ADR 0083: The workflow-first trader site: Ideas, Setups, Test, Calendar; what Ideas is; the historical exit rule; the product rules

**Status:** accepted (2026-10-24; owner decisions, taken after the use-case research and the
workflow design; an architect reviewed the build slices). Amends
[0025](0025-frontend-architecture.md) (the TRADER sections) and
[0041](0041-natural-language-screener-drafts.md) (the model only translates: its `suggestions`
go). Supersedes [0029](0029-rule-screener.md) decision 9 (Ideas is the viewer's screener pool)
for the Ideas list, and the 2026-10-22 amendment of [0005](0005-ingestion-is-the-only-writer.md)
(a per-viewer Ideas index), with the matching amendments of [0006](0006-storage-grains-and-adapters.md)
and [0077](0077-serving-release.md) (d). Uses [0036](0036-session-strictness-for-reads.md) /
[0062](0062-reads-serve-the-last-complete-session.md) (one session per read),
[0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (verdicts),
[0064](0064-edge-evidence-series-and-trade-ledger.md) (the trade ledger),
[0065](0065-verdict-basis-fixed-before-the-frozen-period.md) (the basis),
[0069](0069-data-licence-gate.md) (the licence gate) and
[0081](0081-stored-edge-picks.md) (stored picks).

## Context
The owner is turning the trader app into a paid product ($20-100 a month) for part-time US swing
traders. Research (a use-case brief over about 60 tools and about 260 Reddit threads) found two
open jobs: an evidence-backed shortlist after the close, and an honest test of the trader's own
idea. Today's TRADER bar (Ideas, Screeners, Edges, Explore, Regime, Calendar) is organised by our
objects, not by that workflow; Ideas is the viewer's pool of screener matches, which carries no
evidence; Screeners and the edge builder are two flows for one job; Backtests is in ADR 0025 but
no page exists. Verdicts now exist (2026-10-24: 63 of 66 edges read `not_enough_data`), so a list
can be built on them. The business is run from the US; the rules in decision 4 come from a
legal-research pass, not from counsel's opinion, and a securities-law review of the format is
still owed before anyone is charged.

## Decision
1. **The TRADER top bar is Ideas, Setups, Test, Calendar.**
   - *Ideas* stays the home page (`/`, `/ideas`) and becomes tonight's shortlist (decision 2).
   - *Setups* is the Edges page under a new label (`/edges`, the chosen setup `/edges?edge=<id>`); the label is UI
     only, code, config, tables and the Guide's keys keep "edge" (ADR 0053). The site screeners
     that implement a setup are shown inside it.
   - *Test* is one flow for the Screener Builder (`/screeners/new`, `/screeners/$id/edit`) and the edge builder
     (`/edges/new`, `/edges/$id/edit`): describe it (Describe it), rules, settings (outcome, schedule,
     universe), result (an on-request evaluation, ADR 0059), save (a user screener config, ADR
     0029, and a user edge document, ADR 0053: the existing writes, no new one). It is one route
     group `/test`; the old builder URLs redirect to it. A trader's own screeners and setups are
     listed under Test.
   - *Calendar* is unchanged. *Explore* is not a tab: it is reached by a global ticker search
     (⌘K, which searches tickers, setups and the Guide: the Guide's ⌘K search, ADR 0051, extended)
     and keeps its `/explore` route. *Regime* is not a tab either: its page stays at `/regime`,
     reached from the top-bar regime chip and ⌘K. The Screeners list `/screeners` leaves the bar
     (a site screener lives in its setup, a user's own under Test; the route redirects to Test).
     Backtests is dropped (no page exists).
   - The account menu gains *Settings*: the nightly brief and display preferences only (the
     per-user `preferences.toml`, ADR 0032). **No account size, risk profile or position size is
     stored anywhere.**
   - Role gating stays in `apps/web/src/app/workspaces/guard.ts`; ADMIN is unchanged.
2. **Ideas is built from the picks of setups with a good stored verdict.**
   - *Source.* A site setup is listed when its stored verdict level is `works` or `promising`
     (`services/read/evaluation/verdict/stored.py`, the headline in `results/edge_verdict`),
     and its picks are the `picked` rows of `results/edge_picks` for the served session
     (`services/read/evaluation/pick_edges.py`, place 1 first; ADR 0081). The screener's own
     picks are not used. Ideas never judges live: a setup with no matching stored verdict (the
     fingerprint differs, ADR 0053 amendment) is not listed and the page says how many were
     left out for that reason (UNKNOWN with a reason, ADR 0036). `pick_edges.py` gains the
     inverse read (setup to picks); no other module names the table.
   - *One ranking rule for every viewer.* Evidence strength, then rank within the setup:
     verdict level (`works` before `promising`), then the verdict's out-of-sample lift in points
     (`lift_pts`), then its out-of-sample trades, then `edge_id`; then the pick's place, then
     `instrument_id`. A ticker picked by several setups is one idea at its best position and
     lists the others ("also in"). The rule is a pure function in `services/read/`, with a
     version recorded on the list.
   - *Per viewer, only a filter.* The licence gate (ADR 0069) drops a pick whose screener ranks
     on a field the viewer does not hold, before the cap, and its rank is never shown (ADR 0081
     `withheld`); the visible list is renumbered. Then the list is **capped at 15**.
   - *Unproven.* Until any setup has a `works` or `promising` verdict, today's screener matches
     (the pool of ADR 0029, with the 2026-10-22 pool rule it keeps) are shown in a section
     labelled **Unproven**, and the page says why. Once one setup qualifies the section is not
     shown; a night on which the qualifying setups pick nothing is an empty list with its reason
     (not a decision day, nothing qualified), never a fall-back to Unproven.
   - *No stored list, no per-viewer index.* The list is a read over stored rows (the same for
     everyone, filtered per viewer); the planned `ideas` step, the per-viewer SQLite index
     (`indexes/ideas.sqlite`, `storage/indexes/ideas.py`) and the API's rebuild of Ideas rows are
     not built, so ADR 0005 gains no writer for them. The Ideas request stays a run operation,
     never release-shared (ADR 0077 decision 16).
   - *The trader's own setups.* Once a trader builds their own, their picks appear in their own
     section, so Ideas becomes personal for them. It needs, first, per-owner pick rows (the
     `user_id` already in the key; ADR 0081 decision 3, an amendment of that ADR with its
     writer) and a verdict for an own setup (`stored.py` never stores one, own edges judge
     live). Until then the section is absent.
   - *Past lists.* A stored scorecard of past lists is a later, separate ADR; here only: it
     will exist, and a pick that rests on a personal-licence field is visible on it only to
     accounts that hold that licence (today the owner's account alone).
3. **A setup's historical exit rule** (the words "plan", "your stop" and "your size" are not
   used). For a pick of a setup:
   - *Stop* is the drawdown that 80% of the setup's winning trades never exceeded: the 80th
     percentile of `max_drawdown` over the `hit` trades of `results/edge_trades` for the verdict's
     basis (its screener and horizon, ADR 0065) in the canonical run, read only through
     `services/read/evaluation/runs.py` (ADR 0064; `oos_hidden` and the 45-day retention rule
     apply; PRUNED and NOT_STORED stay distinct). The page says it is a historical distance, that
     20% of the winners went past it, and on how many trades it rests.
   - *Fallback.* With fewer winning trades than a configured minimum (a `[exit_rule]` setting,
     value chosen in the implementing PR), the stop is 2 x `momentum.atr_14@v1` at the session,
     labelled "fallback: 2 x ATR(14), not from this setup's history".
   - *Hold* is the edge document's `[outcome] horizon_sessions`, the horizon of the verdict's
     basis.
   - *Unknown, never filled.* A missing input (no ledger, no `atr_14` row for the session, no
     basis) is UNKNOWN with its reason (ADRs 0036, 0062). Long picks only (ADR 0081 decision 4).
     No position size, no stored account profile. If the percentile is too slow for a page it is
     stored as a column by the `edge-eval` writer (ADR 0064), never computed in the browser.
4. **Product rules** (every page, the Guide, the nightly brief and the model prompt):
   - *One fixed nightly batch, the same list for everyone;* no event-triggered alerts. The
     brief carries the shared list.
   - *No broker links, trade buttons or broker commissions.* (ADR 0026 stays.)
   - *Wording:* "publishes setups", "the setup's historical exit rule"; never "recommend",
     "your plan", "your stop". The slice that ships the list adds a fitness test over the
     Guide entries, site config and web labels for these words.
   - *The language model only translates a trader's sentence into rules; it never suggests or
     improves a rule.* Describe it's paths, checked in `services/drafting/`: the `suggestions`
     (protective checks the sentence did not ask for, ADR 0041 amendment 2026-10-11,
     `contract/suggestions.py`, `MAX_SUGGESTIONS`, `suggestions_dropped`, the Builder's
     "Suggested" group) **break the rule and are removed** in the Test slice (prompt, answer
     schema, `ScreenDraft`, REST response, web); the other paths stay because they only read the
     sentence: the readings of an unresolved vague word (the trader picks one; no threshold is
     invented), `tie_break` only from "rank by", a re-draft of words the trader retyped. The
     model's `notes` are limited to how the sentence was read (prompt rule and a golden case).
     The Test result states a verdict and never a changed rule.
   - *Every statistic* is labelled "backtested (hypothetical)" or "forward paper record since
     <date>", never blended in one figure, and shows its trades, base rate, worst year, cost
     assumptions (ADR 0064) and survivorship handling (delisted names and their coverage).
   - *A methodology and conflicts page and a risk statement beside every list.* Both are Guide
     entries (ADR 0051); the risk statement is shown inline beside the list through a design-system
     component given the entry reference, not as prose in `src/`. Ownership of the entries:
     `add-guide-content`.
   - *Launch is US-only; UK and EU sign-ups are blocked.* The mechanism (at registration, behind
     the `Authenticator` seam, ADR 0040; roles never carry it) belongs to the sign-up and billing
     ADR; this ADR fixes the rule.

## Consequences
- The bar matches the workflow (Find, Check, Learn, Test); Backtests leaves the docs; old
  `/screeners*` and `/edges/new` and `/edges/$id/edit` URLs redirect, so bookmarks and Guide links keep working.
  Guide entries and labels say "setup" where a trader reads them.
- Until a setup earns `works` or `promising` the home page is the Unproven section, honestly
  labelled; 63 of 66 setups read `not_enough_data` today, so that is the first state.
- Ideas needs no new writer, store or per-viewer table; it needs one pure ranking function, the
  inverse read in `pick_edges.py` and a loader test on a fixture with a licence-held and a
  licence-withheld setup. The 2026-10-22 per-viewer index and its three amendments (0005, 0006,
  0077 (d)) are marked superseded; the weight / position rule survives only for Unproven.
- A strong setup can fill the whole list of 15 (a setup's `top_k` can reach it); the card says
  which setup an idea comes from. No diversification rule is decided here.
- Removing `suggestions` from Describe it is a code change (ADR 0041 amended): slices follow
  this ADR.
- Not decided here (each its own ADR): past lists and the scorecard, the nightly brief's
  delivery, sign-up and billing and the US-only gate, per-owner pick rows and own-setup verdicts,
  and the size of the Unproven section (it keeps today's rule).
