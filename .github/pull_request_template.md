## What & why

<!-- This PR merges automatically once every CI check passes. Mark it as a draft or add
     the `no-automerge` label to keep it open for review. -->

## Ownership (ADR 0019)
- Owner module(s) this change extends (from `architecture/ownership.toml`):
- [ ] No responsibility re-implemented outside its owner; a new responsibility has an entry + owner in `architecture/ownership.toml`
- [ ] A new stored table has exactly one producing owner (`[[table]]` in `architecture/tables.toml`)
- [ ] `make ownership` passes; `architecture/known_violations.toml` did not grow (shrunk if violations were fixed)
- [ ] `make dupes` passes; `architecture/dupes_baseline.txt` did not grow
- [ ] Architecture checks pass (`make arch`, `tests/architecture/`); boundary changes come with an ADR and the matching contract

## Directory layout (ADR 0020)
<!-- Paste the warning list from `make layout` (folders at 8+ of 10 modules) if this PR adds
     modules to any of them, and say whether a split is planned. -->
- [ ] Placed per the "Where does this go?" table (CLAUDE.md); nothing parked in a neighbouring folder
- [ ] New folders declared in `architecture/layout.toml` with a purpose (+ `__init__.py` docstring, contracts if a boundary guards them)
- [ ] No directory over 10 modules; folders in the `make layout` warning band considered (split planned or not needed)
- [ ] Tests mirror the source folders; no grab-bag module names (`utils`, `helpers`, `common`, ...)

## Web UI (ADR 0025; skip if `apps/web` is untouched)
- [ ] Placed per `docs/ui/architecture.md` ("Where does it go?"); new folders declared as `[[web_dir]]` in `architecture/layout.toml`
- [ ] Layers import only downward; other slices only via `index.ts`; no sibling-slice imports
- [ ] No HTML elements, `className` / `style`, CSS, colours or px outside `design-system/`; only `src/shared/api` talks HTTP
- [ ] New / changed design-system component: stories (Default, Loading, Empty, Error, Dense), test with axe, screenshots updated (`npm run visual:update`) and reviewed; `COMPONENTS.md` regenerated
- [ ] API changes: `npm run api:generate` run and the generated schema committed
- [ ] `make web-check` passes

## Checklist
- [ ] `make check` passes locally
- [ ] Fits the target architecture (`docs/architecture.md`) and existing ADRs, or a new ADR is included
- [ ] New code has unit tests in the mirrored `tests/unit/<layer>/` folder
- [ ] No layer boundary changes (or `pyproject.toml` contracts + `docs/architecture.md` updated with an ADR)
- [ ] Data: keyed by `instrument_id`, point-in-time columns present, no paths built outside `storage/backends/`
- [ ] Backtests and screeners read only from stores (no vendor calls)
- [ ] If `benchmarks/baseline.json` changed: the scorecard diff is explained below and is intended
- [ ] New strategy? Registered, passes property tests, beats `buy_and_hold` somewhere meaningful (not only on `random_walk`)

## Baseline / scorecard changes
<!-- Paste the relevant rows of the scorecard before/after, or "none". -->
