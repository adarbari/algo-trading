"""Read objects about events for one session (ADR 0037, ADR 0050): an instrument's stored
events by event date, what is ahead of it (its own and its reference's next earnings, the macro
releases, the market-structure days), its 8-K filings, its expiry ladder and fund reference
(``InstrumentEvents``), and the cross-name event calendar (``EventCalendar``). Event tables are
read by event date among the rows known on or before the session (``known_from``)."""
