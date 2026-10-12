"""Use case: the contract of the drafting model's answer (ADR 0041, amended 2026-10-11): its JSON
Schema and local check (``answer_schema``), and what the server decides of each kind of item the
model proposes: B1 formulas (``formulas``), missing features and unresolved terms (``gaps``) and
suggested checks (``suggestions``). Pure over the answer and the caller's catalogue; writes
nothing (split from services/drafting, at its module cap)."""
