"""GraphQL types about events (ADR 0037, ADR 0050; mirrors services/read/events): a stored
``Event``, an instrument's ``InstrumentEvents`` (ahead, filings, expiry ladder, fund reference)
and the cross-name ``EventCalendar``; each mirrors a ``services.read.events`` dataclass through
one ``.of()``."""
