# Working in this repo (for humans and AI agents)

Read `docs/architecture.md` first. These rules are enforced by CI, so follow them up front:

1. **Respect layers.** `strategies/` imports only `algotrade.core`. `core/` imports no other
   `algotrade` package and no pandas. Check with `make arch`.
2. **No file over 1000 lines** (aim for under 300). Split by responsibility. Check with `make filelen`.
3. **Every module starts with a docstring** stating its single responsibility.
4. **Tests mirror src**: code in `src/algotrade/<layer>/x.py` is tested in
   `tests/unit/<layer>/`. Coverage gate is 90%.
5. **UTC, timezone-aware datetimes only.** No `print` outside `cli/`.
6. **Never hand-edit** `datasets/golden/*` or `benchmarks/baseline.json`. Use
   `make datasets-build` / `make baseline`, and explain baseline diffs in the PR.
7. **Strategies must be deterministic** and pass `tests/property` (look-ahead, accounting, long-only).
8. Before finishing any change run `make check`.

Commands: `make install`, `make check`, `make test`, `make evaluate`, `make baseline`.
