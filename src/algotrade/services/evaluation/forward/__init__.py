"""The forward paper record (ADR 0053 amendment 2026-10-09): what a followed edge would have
bought and sold, kept as it happens. ``signals.py`` makes tonight's picks of the edges a user
follows (the harness's own picker, only what was known at the session), ``settle.py`` closes the
trades whose window has a stored outcome and ``results.py`` frames the rows and publishes the
night atomically into ``results/edge_paper``."""
