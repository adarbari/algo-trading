---
name: add-guide-content
description: Explain something to the user (what a field, signal, setup, rule word or screen element means, how to read it, when it lies) or move an existing explanation into the Guide. Use before writing any explanatory text in the web app, a Disclosure or tooltip that defines something, or a help paragraph; the text becomes a Guide entry and the page shows it through InfoButton + HelpDrawer (ADR 0051).
---

# Add or move Guide content

Read first: `docs/ui/guide.md` (sections 3 to 5: the sections, the page templates, the drawer,
the migration table, the checks) and ADR 0051. The rule: **every explanation is written once,
as a Guide entry in site config, and a page shows it only through the help drawer.** The web
code never holds the explanation; a page keeps at most a one-sentence introduction, and
microcopy (an empty state, a confirmation, an action hint) is one sentence under 25 words.

1. **Is it an explanation?** It says what something means, how to read it, why it matters,
   what it did before, or when it misleads. Then it is Guide content. If it describes this
   session's data (a gap, a missing snapshot, a run's coverage), it stays on the page as a
   banner, and the terms it uses open their drawers. If it tells the user what to do next, it
   is microcopy: one sentence.
2. **Find the entry's kind and its source** (`grep -n "<term>" config/site/field_guide/*.toml
   config/site/regime/*.toml`, and the Guide sources below); extend an existing entry rather
   than adding a near-duplicate:

   | Kind | Source (one owner each, `architecture/ownership.toml`) | Written by |
   |---|---|---|
   | field (a catalogue feature) | `config/site/field_guide/<theme>.toml` `[[field]]` | `add-feature` ships it with the feature |
   | situation (fools many fields at once) | `config/site/field_guide/situations.toml` `[[situation]]` | |
   | regime indicator, episode | `config/site/regime/cards.toml`, `episodes.toml` | |
   | playbook (one per site preset screen) | `config/site/guide/playbooks/<id>.toml` (`[asks]`: one line per criterion of the latest version) | `add-screener` for a site preset |
   | glossary term, how-to page | `config/site/guide/glossary.toml` `[[term]]`, `start.toml` `[[page]]`; the button takes `{ kind: 'term' | 'start', id }` | |

   A kind the table does not have yet: stop and add it through `add-responsibility` (an owner,
   a loader in the Guide read model, a page template in docs/ui/guide.md), not as page text.
   Until a kind's phase ships, write the entry in the spec's migration table and leave the
   page's old text where it is (it is in the baseline); never add new text to a page.
   **Why a value is not available** (a gap on a page) is a glossary term per public kind
   (`unavailable_system`, `unavailable_not_stored`, ..., `not_run`; ADR 0056). A new
   `UnavailableKind` needs its term in `config/site/guide/glossary.toml` and a line in
   `GUIDE_TERMS` (`services/read/availability/cause.py`); the fitness test fails without one.
   The chain behind a gap (a table, a step, a source) is an admin's cause, never Guide text.
3. **Write the entry for someone who does not follow markets**: what it is, how to read it from
   low to high (thresholds with units), what to use it for, when it lies, sources. Name other
   fields by their catalogue name so the server can link them; never derive in the browser
   what a field page lists (related fields, playbooks that use it: the server computes them,
   ADR 0038). Fields: `make features-doc` and the field-guide fitness tests.
4. **Show it in place**: put the `InfoButton` from the guide-help feature beside the thing
   explained, passing the entry reference `{ kind, id }` (for a field, its catalogue name),
   never text (from GD2 / GD3; `HelpDrawer` is imported only by that feature). In a feature
   table the column factories in `entities/feature` already add it to every field header.
5. **Moving an old surface**: delete its text and its Disclosure from the page, put the
   button in its place, and lower or delete the file's line in `architecture/web_prose.toml`
   in the same PR (the test fails until you do); tick the row in docs/ui/guide.md section 4.
6. **Checks**: `.venv/bin/python -m pytest tests/architecture/test_layout_web.py -q -k prose`
   (explanatory prose in `apps/web/src` against the shrink-only baseline), the field-guide
   tests in `tests/architecture/test_features.py`, then `make changed` and push (CI is the full gate). A false finding of the
   prose test (a long label, say) is shortened, never added to the baseline.
