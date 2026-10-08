"""The edge harness (ADR 0053 decisions 5 to 7, ``docs/edges-plan.md`` ED3): per edge, the
sessions of its schedule spaced a horizon apart (``sessions``), each screener's picks and the
eligible names at each (``picks``), whether a stored outcome counts as a hit (``hit``), the
measures per slice with the statistics of ``quant.edge_statistics`` (``measures``), the run
that joins the closed outcomes (``harness``, the only module that reads them) and the rows it
writes to ``results/edge_eval`` (``results``)."""
