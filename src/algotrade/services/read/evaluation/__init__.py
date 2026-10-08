"""Read objects over the edge evaluation (ADR 0053): the edge documents with their status
(``edges``), the evaluation runs of an edge and their rows (``runs``), and a screener's track
record (``track_record``). Run records, not session data: ``results/edge_eval`` is partitioned
by the range end, so it is read by run, as the run left it, never by session."""
