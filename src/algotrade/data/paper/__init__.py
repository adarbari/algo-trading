"""Reads of the forward paper record (``results/edge_paper``, ADR 0053 amendment 2026-10-09): the
trades the nightly ``edge-signals`` job made for the edges a user follows. Written only by
``services/evaluation/forward``; read by it (to settle open trades) and by the read model (the
Ideas signals and an edge's live record), always as of a session the caller names."""

from algotrade.data.paper.reading import LOOKBACK_DAYS, PAPER_COLUMNS, job_name, read_paper

__all__ = ["LOOKBACK_DAYS", "PAPER_COLUMNS", "job_name", "read_paper"]
