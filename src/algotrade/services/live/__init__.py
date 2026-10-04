"""Use case: live option quotes for the API (ADR 0028): read from a quote feed (IB Gateway,
read-only) with a short cache and the stored delayed chain as the fallback (``quotes``), and
recorded in the background to ``live/*`` tables (``recorder``: the API's one write)."""
