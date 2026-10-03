# ADR 0001: Layered architecture enforced by import-linter

**Status:** accepted

## Context
Trading codebases rot in a specific way: strategies start reading files, risk checks get
bypassed for "just this one" strategy, and backtest and live paths diverge.

## Decision
Use a strict layered package structure (see `docs/architecture.md`) and enforce it
mechanically with `import-linter` contracts in CI and pre-commit. Strategies may import only
`core`. `core` may not import pandas or any other `algotrade` package.

## Consequences
- Boundary violations fail the build instead of relying on code review.
- Adding a cross-layer dependency requires changing `pyproject.toml` *and* writing an ADR,
  which forces the conversation.
