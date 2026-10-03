# ADR 0015: Configs, selections and users

**Status:** accepted (2026-10-03). Implemented in phase 0.5. Amends [0013](0013-universe.md).
Spec: [docs/design/phase-0.md](../design/phase-0.md) (Data Layers L3/L4, D2, D3).

## Context
The owner wants the universe to be every ticker and ETF, with each strategy working on a
subset chosen by conditions that are configurable, and different users able to keep their
own configurations.

## Decision
- **The universe is coverage, not a filter.** Ingestion covers every instrument (L1
  `instruments/reference` + the `universe` snapshot). Nothing is hard-coded as "production".
- **Selections** are typed rules (`{field, op, value}` with `all` / `any` / `not` groups),
  validated against a field catalogue (`instrument.*`, `rollup.<name>@vN.*`). They are
  evaluated with three-valued logic: missing data is UNKNOWN and excluded, never passed.
  Each run stores a per-rule audit.
- **Configs** are TOML. L3 site presets live in `config/site/` (reviewed via PR); L4 user
  configs live in `config/users/<id>/` (git-ignored; a database later, behind `ConfigStore`).
  Resolution: built-in defaults < site < user < run overrides. A user either narrows a
  preset (`selection_overrides`, AND-ed with it) or replaces it (own `selection`), or
  `extends` a preset under a new id.
- **Users** are a validated label (`--user`, default `local`; `site` for runs scheduled from
  presets). Identity and auth come with the API (phase 4).
- **Market data and rollups are global; configs, results and jobs are per user.** Every
  result and run record carries `user_id`, `config_id` and the SHA-256 `config_hash`.

## Consequences
- Adding a strategy subset is a config change, not a code change.
- Results are reproducible: the config hash identifies exactly what produced them.
- A user can never widen coverage; covering a new instrument is a site change.
