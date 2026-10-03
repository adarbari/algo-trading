# ADR 0010: Long-running work is a job

**Status:** accepted (2026-10-02)

## Context
Backtests will be launched from the web UI. On-request data pulls must be possible later,
and nightly runs are the same kind of work.

## Decision
- `services/jobs` defines `submit(kind, params) -> job_id`, `status(job_id)` and `result(job_id)`.
  Job kinds include `backtest`, `screen` and `ingest` (more to come).
- Phase 0 ships a **local in-process runner** and a job table in the catalog. A real queue
  (for example Redis/RQ or Postgres-backed) can replace the runner later without changing callers.
- Jobs are idempotent and resumable where possible. Ingestion jobs record checkpoints so a
  rate-limited vendor (for example IBKR pacing) can pick up where it stopped.
- **Pulling data on request** is an `ingest` job with an explicit instrument and date scope.
  The interface exists from phase 0; the feature is built later.

## Consequences
- The API never blocks on long work; it returns a `job_id` and the UI polls or streams status.
- One mechanism covers nightly, on-request and UI-triggered work.
