# ADR 0004: Four apps, shared libraries, one repo

**Status:** accepted (2026-10-02). Implemented in roadmap phase 0.

## Context
We are building several applications: backtesting, a web UI with its API, and a data
ingestion pipeline. Each has a different lifecycle, dependencies and failure modes. We
also want to run locally now and be able to host later without a rewrite.

## Decision
- Four apps under `apps/`: `ingestion`, `backtest`, `api`, `web`. Each has its own
  entry point and dependency list. Python apps are members of a **uv workspace**;
  `web` is a pnpm workspace.
- Shared logic lives in libraries under `src/algotrade/`. Apps contain wiring, config and
  scheduling, not business logic.
- **Apps never import each other.** They talk through storage (data) and, for the web UI,
  through HTTP to `apps/api`.
- `services/` is the backend's real interface. `api/` is a thin HTTP wrapper over it.
  The backtest app calls `services/` in-process.
- Hostable later: all config comes from environment variables (12-factor style), storage is
  addressed by URL, and the API serves the built web app.

## Consequences
- import-linter gets an "apps are independent" contract.
- Each app can be tested and deployed on its own; a vendor outage cannot take down the UI.
- No microservices overhead: one repo, one CI, shared types.
