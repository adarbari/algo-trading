"""The option-structure engine (ADR 0088, design 2.4): marks a position of option legs to each
close of its window from the stored chains of those sessions, hands the daily delta hedge its net
delta, values it at expiry and at an exit quote, and never fills a missing session from an
earlier one. Pure: the callers (the option-outcomes task, the history writer) load each session's
chain and pass it in, so this folder imports ``features`` (the leg selector), ``config`` and
``quant``, never ``data`` or ``storage``. The exits of design 2.4a and a share leg held with the
options (a covered call) land in the next slice (E3b)."""
