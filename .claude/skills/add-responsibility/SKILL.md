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

0. **Where it goes:** this skill is also the place for "nothing fits, I need a new folder":
   step 3 covers the new kind end to end.
1. **Is it already owned?** Search `architecture/ownership.toml` (ids, descriptions, detect
   rules) and the table in `docs/architecture.md` section 14. If an owner exists, extend
   that module and stop here: never write a second implementation, even a small one.
2. **New responsibility:** add a `[[responsibility]]` with `id` (kebab-case), one-line
   `description`, `owner` (the one module, or a package glob), optional `target_owner` while
   a PR is moving it, `section` (an ADR heading anchor) and
   `detect` rules that would catch a re-implementation elsewhere: prefer specific call
   names (`call`), attribute chains (`attr`), imports (`import`) and literals
   (`string_prefix`). Run `make ownership`; it must report no new hits. If a rule hits
   legitimate code, narrow the rule or add the module to `allowed` with a comment saying
   why. Never add the hit to `known_violations.toml`.
3. **Where does the code go?** Look the kind up in the "Where does this go?" table
   (CLAUDE.md, Directory layout) and `architecture/layout.toml` (every directory under
   `src/`, `apps/`, `tests/`, `config/`, `docs/`, with its purpose; one kind of thing per
   folder). Put the module in the folder whose purpose fits, named for what it does (never
   `utils` / `helpers` / `common` / `misc` / `shared`: `[banned_module_names]`). Run
   `make layout`: a folder at 8+ of 10 modules is due a split by kind; plan it in this PR
   rather than adding the 11th (there are no `[[exception]]` entries). **A new kind gets a
   new folder, end to end, in the same PR:**
   - a `[[dir]]` entry in `architecture/layout.toml` with a one-line `purpose` (and `kind`
     if it is a vendor or task domain);
   - an `__init__.py` whose docstring says what the folder holds;
   - if a boundary guards it (purity, independence, who may import it), an import-linter
     contract in `pyproject.toml`, named in the entry's `contracts`;
   - the mirrored test folder (`tests/unit/<path>/` or `tests/apps/<app>/<path>/`, with an
     `__init__.py`); a new non-mirrored test bucket (helpers, a contract suite) is a
     `[[test_dir]]`; a new config or docs folder a `[[config_dir]]` / `[[docs_dir]]`;
   - the "Where does this go?" row in `CLAUDE.md` if it is a new kind of code, and an
     addendum to ADR 0020 (`docs/adr/0020-directory-layout.md`) when the top-level structure
     changes (a new top-level library package, app folder or test suite).
   Splitting a folder: move modules into kind subfolders, update imports and
   `architecture/ownership.toml` paths, and move the tests to mirror (no re-export shims).
   `tests/architecture/test_layout.py` and `test_layout_buckets.py` check all of it.
4. **New stored table:** add a `[[table]]` with exactly one producing `owner`.
5. **Moving a responsibility:** move the code and make the new module the `owner` in the
   same PR (a `target_owner` may bridge a multi-PR move; remove it when done). Run
   `make dupes-update` if duplicates went away (it fails when counts go down without the
   update, on purpose). A boundary the move makes true goes straight into `pyproject.toml`
   as an import-linter contract (`make arch`), never as a pending entry.
6. **Boundary change?** If the new owner crosses a layer or app boundary, or a rule R1-R5
   changes, write an ADR (`.claude/skills/write-adr`) and update `docs/architecture.md`
   section 14 and the Ownership table in `CLAUDE.md`.
7. **Site settings:** a new key in `config/site/*.toml` gets a typed field in
   `src/algotrade/config/site/settings.py` (the one loader, with validation and an error path) and
   must drive code (`tests/architecture/test_ownership.py`). Environment variables are read
   only in `src/algotrade/config/env.py`. A new table column is declared with its type in
   `src/algotrade/storage/tables/schemas.py`.
8. Run `make check`.
