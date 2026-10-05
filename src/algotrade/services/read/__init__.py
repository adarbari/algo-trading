"""The read model (ADR 0037): every read a page shows, for exactly one resolved session
(ADR 0036). Holds the session resolver, the UNKNOWN vocabulary and scalar coercion, and the
read context the GraphQL layer builds per request; one loader module per domain object lives
in the subfolders (``instruments``, ``screens``, ``ops``). Read-only: no writers, no jobs.

Empty until read-model PR 2 (``session.py``, ``values.py``, ``context.py``); the plan is
``docs/api/read-model.md``."""
