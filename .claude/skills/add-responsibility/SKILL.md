---
name: add-responsibility
description: Add a new responsibility (a kind of work some module must own) or move one to a new owner, keeping architecture/ownership.toml, the ratchets and ADRs in sync. Use before writing code that does something no owner covers yet, when restructuring (roadmap track R), or when make ownership / make dupes fails.
---

# Add or move a responsibility

Read first: ADR 0019 (`docs/adr/0019-ownership-and-boundaries.md`) and
`architecture/ownership.toml`.

1. **Is it already owned?** Search `architecture/ownership.toml` (ids, descriptions, detect
   rules) and the table in `docs/architecture.md` section 13. If an owner exists, extend
   that module and stop here: never write a second implementation, even a small one.
2. **New responsibility:** add a `[[responsibility]]` with `id` (kebab-case), one-line
   `description`, `owner` (the one module, or a package glob), optional `target_owner` +
   `target_pr` if the restructure will move it, `section` (an ADR heading anchor) and
   `detect` rules that would catch a re-implementation elsewhere: prefer specific call
   names (`call`), attribute chains (`attr`), imports (`import`) and literals
   (`string_prefix`). Run `make ownership`; it must report no new hits. If a rule hits
   legitimate code, narrow the rule or add the module to `allowed` with a comment saying
   why. Never add the hit to `known_violations.toml`.
3. **New stored table:** add a `[[table]]` with exactly one producing `owner`.
4. **Moving a responsibility** (a restructure PR): move the code to `target_owner`, make
   that the new `owner`, then run `make ownership-update` and `make dupes-update` to shrink
   the ratchets. Both fail when counts go down without the update, on purpose. If the move
   makes a `[[pending_contract]]` true, add it to `pyproject.toml` (`make arch`) and delete
   it from the registry.
5. **Boundary change?** If the new owner crosses a layer or app boundary, or a rule R1-R5
   changes, write an ADR (`.claude/skills/write-adr`) and update `docs/architecture.md`
   section 13 and the Ownership table in `CLAUDE.md`.
6. **Site settings:** a new key in `config/site/*.toml` must be read by the settings owner
   and drive code (`tests/architecture/test_ownership.py`).
7. Run `make check`.
