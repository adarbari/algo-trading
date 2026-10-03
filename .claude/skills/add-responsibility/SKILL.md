---
name: add-responsibility
description: Add a new responsibility (a kind of work some module must own) or move one to a new owner, keeping architecture/ownership.toml, the ratchets and ADRs in sync. Use before writing code that does something no owner covers yet, when moving work between modules, or when make ownership / make dupes fails.
---

# Add or move a responsibility

Read first: ADR 0019 (`docs/adr/0019-ownership-and-boundaries.md`),
`architecture/ownership.toml` and `architecture/layout.toml` (ADR 0020, directory layout).

**The ownership ratchet is at zero** (since restructure PR 6): `make ownership` fails on any
hit outside an owner, `architecture/known_violations.toml` must stay empty, and no
`[[pending_contract]]` may exist (`tests/architecture/test_ownership.py` asserts both). There
is no "park it in the ratchet" option: extend the owner, narrow a wrong detect rule, or, for
a genuine exception, write an ADR and list the module in `allowed` with the reason.

1. **Is it already owned?** Search `architecture/ownership.toml` (ids, descriptions, detect
   rules) and the table in `docs/architecture.md` section 13. If an owner exists, extend
   that module and stop here: never write a second implementation, even a small one.
2. **New responsibility:** add a `[[responsibility]]` with `id` (kebab-case), one-line
   `description`, `owner` (the one module, or a package glob), optional `target_owner` while
   a PR is moving it, `section` (an ADR heading anchor) and
   `detect` rules that would catch a re-implementation elsewhere: prefer specific call
   names (`call`), attribute chains (`attr`), imports (`import`) and literals
   (`string_prefix`). Run `make ownership`; it must report no new hits. If a rule hits
   legitimate code, narrow the rule or add the module to `allowed` with a comment saying
   why. Never add the hit to `known_violations.toml`.
3. **Where does the code go?** `architecture/layout.toml` declares every directory under
   `src/` and `apps/` with its purpose (one kind of thing per folder, at most 10 modules).
   Put the module in the folder whose purpose fits; a new folder needs a `[[dir]]` entry
   with a one-line purpose and an `__init__.py` docstring in the same PR
   (`tests/architecture/test_layout.py`, ADR 0020). Never add an `[[exception]]` for a new
   oversized folder: split it by kind.
4. **New stored table:** add a `[[table]]` with exactly one producing `owner`.
5. **Moving a responsibility:** move the code and make the new module the `owner` in the
   same PR (a `target_owner` may bridge a multi-PR move; remove it when done). Run
   `make dupes-update` if duplicates went away (it fails when counts go down without the
   update, on purpose). A boundary the move makes true goes straight into `pyproject.toml`
   as an import-linter contract (`make arch`), never as a pending entry.
6. **Boundary change?** If the new owner crosses a layer or app boundary, or a rule R1-R5
   changes, write an ADR (`.claude/skills/write-adr`) and update `docs/architecture.md`
   section 13 and the Ownership table in `CLAUDE.md`.
7. **Site settings:** a new key in `config/site/*.toml` gets a typed field in
   `src/algotrade/config/settings.py` (the one loader, with validation and an error path) and
   must drive code (`tests/architecture/test_ownership.py`). Environment variables are read
   only in `src/algotrade/config/env.py`. A new table column is declared with its type in
   `src/algotrade/storage/schemas.py`.
8. Run `make check`.
