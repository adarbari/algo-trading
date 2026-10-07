# ADR 0051: The Guide: every explanation written once, shown in place through the help drawer

**Status:** accepted (2026-10-07; owner decisions on the mockup, roadmap "Guide (GD)"). Extends
[0025](0025-frontend-architecture.md) (one more component rule for the web app),
[0038](0038-catalogue-named-values.md) (derived Guide facts are computed
by the server) and [0041](0041-natural-language-screener-drafts.md) (the field guide becomes the
Guide's Fields section). Spec: [docs/ui/guide.md](../ui/guide.md).

## Context
Explanations are spread over the app: the field guide is an Explore tab and an expandable
section under each Builder criterion, the regime cards carry why-it-matters text behind an
expandable section, the Regime page has a hand-written chart legend and an episode table, the
preset screens explain themselves only in TOML comments, and pages hold explanatory paragraphs
written in TypeScript. The same idea is written in several places, a page cannot link to an
explanation, and nothing stops the next page from adding its own. The survey in
docs/ui/guide.md (TradingView, thinkorswim, Koyfin, Finviz, tastylive, Stripe, Linear and
others) found the better products keep one reference entry per term, give it a URL, and show
its first paragraph where the user is.

## Decision
1. **One Guide, at `/guide`, reached from a utility link** on the right of the top bar
   (book icon and "Guide", before the session and the account menu, in both workspaces; `?`
   opens it, ⌘K searches it). It is not a workspace section and not in the account menu.
   Sections, in this order: Start here (how-to), Market regime, Playbooks, Fields,
   Situations, Glossary.
2. **Every explanation is written once, as a Guide entry in site configuration** (reviewed by
   PR), of one kind: a field (`config/site/field_guide/<theme>.toml`), a situation
   (`field_guide/situations.toml`), a regime indicator or episode (`config/site/regime/`), a
   playbook (one per site preset screen), a glossary term or a how-to page. Each kind has one
   owner in `architecture/ownership.toml`, and every entry has a URL under `/guide`.
3. **A page shows an explanation only through the help drawer**: an `InfoButton` beside the
   thing explained opens a `HelpDrawer` with the entry's header, its first paragraph and its
   criteria (or the kind's equivalent) and "Open full page". Three depths, one source: a hover
   shows the first sentence, the drawer the first sections, the page the whole entry. The
   drawer is given a reference to an entry (kind and id), never text, so no explanation is
   written in the web code. A page keeps at most a one-sentence introduction; microcopy (an
   empty state, a confirmation, an action hint) is one sentence under 25 words.
4. **The web code holds no explanatory prose** beyond that: a fitness test finds multi-sentence
   or long text and explainer expandable sections ("how to read", "why it matters", "learn
   more", "what is") in `apps/web/src`, and today's are a shrink-only baseline
   (`architecture/web_prose.toml`). Each PR that moves a surface into the Guide lowers it.
5. **What the Guide derives is computed by the server** (ADR 0038): related fields, the
   playbooks that use a field, the situations that fool it, the names passing a criterion.
6. **Live readings stay on their pages.** The Regime page keeps its values and charts and
   links its explanations to the Guide; the regime explanation written by the text model stays
   where it is (it is about the session's data), with the facts it cites opening their drawers.

## Consequences
- The Explore "Field guide" tab becomes a redirect to `/guide/fields` for one release.
- New work that needs to explain something adds or extends a Guide entry first
  (`.claude/skills/add-guide-content`), the way a missing component goes to the design system
  first (ADR 0011).
- Preset screens need prose that their immutable TOML cannot change in place: playbook text is
  its own Guide source (phase 2 of docs/ui/guide.md).
- The prose test is a heuristic: it can miss a one-sentence explanation and flag a long label.
  A false finding is shortened or moved, never added to the baseline.
