"""Market-entity feature groups (ADR 0047): one ``MKT:US`` row per session describing the
whole market (index trend, universe breadth, cross-asset stress), each a module with its
documented ``FEATURES``, a pure ``compute`` and its ``GROUP`` declaration; ``tickers`` is the
symbol lookup and close panel they share."""
