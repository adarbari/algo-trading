---
name: promote-feature
description: Promote a Describe it backlog item (config/site/feature_backlog.toml) or a trader's accepted formula (a user's draft_ feature) to a site feature, with everything that ships alongside it (catalogue, field guide, phrasebook, Guide entry, golden case, backlog status). Use when an admin or the owner decides a requested or accepted feature becomes part of the site catalogue.
---

# Promote a feature to the site catalogue

Plan: `docs/drafting/describe-it-plan.md` ("Features and duplicates", "Missing features").
This skill decides the class, then hands the building to `add-feature` (and `add-data-source` /
`add-dataset` for new data); what it adds is the promotion bookkeeping. One PR per feature.

## 0. Input and decision

- **Backlog item**: a `[[item]]` in `config/site/feature_backlog.toml` (`key`, `description`,
  `feasibility`, `closest`, `aliases`, `status`). Take the name from `key` unless a catalogue
  convention says otherwise (`grep -n "<keyword>" docs/data/features.md` first: does a close
  feature exist? `closest` lists the nearest; extend or relabel it rather than add a twin).
- **Accepted formula**: a trader's `draft_<slug>` in `config/users/<id>/features/<theme>.toml`
  (`algotrade-backtest --user <id> config validate-features` checks it). Take its `expr`,
  `params`, `dtype`, `unit`, `description` as the starting point; rename off `draft_`. Its
  fingerprint is `fingerprint(definition).hash` from `algotrade.features.expressions.fingerprint`
  (`find_duplicate` compares against site and user features); several users' copies with the
  same hash are one promotion. Structurally different equivalents are not merged by code:
  decide by hand which one wins.

| Class | Meaning | Build through |
|---|---|---|
| B1 | same-session formula over existing features | TOML expression feature: `config/site/features/<kind>/<theme>.toml` (`add-feature`, first half) |
| B2 | a time-window rollup over stored data (`ROLLUP_FROM_STORED`) | a `Feature` in a group in `src/algotrade/features/rollups/<kind>/` (`add-feature`, second half) |
| C | needs data we do not ingest (`NEEDS_SOURCE`) | `add-data-source` / `add-dataset` first (its own PR), then B1 or B2 |

`UNCLEAR` is not buildable: stop and ask the owner what it should mean.

## 1. Build the feature (per class)

- **B1**: `[name]` with `expr`, `dtype`, `unit`, `description`, `null_meaning` (when it is
  null; null is UNKNOWN, never zero), `valid_range`, thresholds as `params`. Licence: a formula
  over a personal-use source (IBKR) inherits `licence = "personal"`; do not copy a user's
  formula without checking its inputs. Virtual unless a group reads it (`materialise`).
- **B2**: a `Feature` in the right group (new stored column = new group version, per
  `add-feature` step 6). Check the nightly impact: the `rollups` task produces it, so its
  runtime and the `architecture/tables.toml` entry change; point-in-time comes from the
  framework (`features/framework/`), so inputs must be asked by table name through
  `data/feature_inputs.py` and no group reads storage. Never write a task for it.
- **C**: the source / dataset PR lands first (owner, ADR when it adds a grain); promote only
  when the data is stored, then B1 or B2.

## 2. Always (same PR)

1. **Backlog**: set `status = "PROMOTED"` and `promoted_to = "<catalogue name>"` exactly as the
   catalogue names it (`feature.<name>` or `rollup.<group>@v<N>.<column>`);
   `tests/unit/config/site/drafting/test_backlog.py` fails if the name is not in the
   catalogue or `promoted_to` is missing / present with another status. An accepted formula
   with no backlog item needs none.
2. `make features-doc` (regenerates `docs/data/features.md` and `docs/data/field-guide.md`).
3. **Field guide**: a `[[field]]` in `config/site/field_guide/<theme>.toml` naming the feature:
   how to read it, `[[field.use]]` per intent, caveats, sources (`add-feature` step 4).
4. **Phrasebook**, when traders have a word for it: `[[phrase]]` in `config/site/phrasebook.toml`
   (`say`, `fields`, `hint`). The format has no structured threshold: the threshold goes into
   the `hint` text. Every field named must exist (a test checks); a held-out golden sentence
   must not be pasted in as a `say`.
5. **Guide entry**: through `add-guide-content` (a field entry comes with the field guide
   entry; a new enum value or status needs its own). `tests/architecture/guide/` fails CI
   without it.
6. **Golden case** for the new feature in `tests/fixtures/drafting/golden/cases/<id>.json`
   (format of the neighbouring files: `id`, `sentence`, `split`, `expect.parts` with
   `span`, `bucket`, `fields`, `op`, `value`, `tolerance`). The sentence is a paraphrase,
   never a real trader sentence (public repo). Train vs held-out: new cases go `train` unless
   the owner says otherwise. Use `algotrade-api golden curate` when it exists (see gaps); else
   write the file by hand to that format.
7. **Tests**: a case in `tests/unit/features/test_site.py` for a B1 (values, nulls, categories),
   the group's mirrored test for a B2.
8. **Owner rules**: `grep <keyword> architecture/*ownership.toml`; the placement table in
   `CLAUDE.md`; `make ownership`, `make dupes`, `make layout`.

## 3. Migration of users' copies (what works today, what is manual)

- A site feature's name cannot be taken by a user feature: `build_expressions`
  (`features/expressions/definitions.py`) raises "shadows the site feature ...; choose another
  name" when a user definition has a site feature's name. Promoting under the user's own
  name therefore breaks that user's `features/<theme>.toml` at load until their copy is
  removed (the `add-feature` rule: give it the same name only after the user's copy is gone).
- A promoted feature under a **new** name does not break anyone: the user's `draft_` copy
  keeps working and resolves to nothing else. Today `find_duplicate` only compares a
  new proposal with site and user features; nothing rewrites existing user configs.
- Manual until a migration helper exists: (1) list the users with the same fingerprint
  (compute `fingerprint` over each `config/users/*/features/*.toml`); (2) pick the site name
  different from every user's name, or have the owner remove those copies in the same
  step; (3) users' saved configs that name `feature.draft_x` keep the old name: edit them or
  leave the old feature in place. Do not invent a helper here; propose one to the owner.

## 4. PR checklist

`make features-doc`, `make changed`, the golden file loads (`tests/unit/services/drafting/`),
backlog test passes. PR description: class, fingerprint hash(es) and the users' count (no user
ids), the paraphrased golden case, what stays manual. No label (docs / config only); a B2 or
C that adds a table or group version is a code change: normal flow.

**Architect review** when the promotion adds a new responsibility, folder, table or grain (a
new group is a folder question: `add-responsibility`), touches point-in-time reads or `quant/`
maths, or adds a personal-licence source.

## Known gaps against the plan (2026-10-11)

- `algotrade-api golden curate` and `golden candidates` are not in `apps/api/algotrade_api/cli.py`
  yet (only `golden run`): write the golden case file by hand.
- The admin accepted-formula list (grouped by fingerprint) and the `fingerprint` call in the
  accept path are not wired: `fingerprint.py` is used by nothing else yet, so list users'
  formulas by script.
- No migration helper for users' copies (section 3).
