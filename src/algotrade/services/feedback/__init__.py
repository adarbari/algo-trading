"""The feedback of Describe it (ADR 0066): the events of a drafting session built here
(``events``: what a row holds and how it is clipped, hashed and emitted without ever failing a
request; ``diff``: what a save changed against the draft the model returned) and recorded in
the background to ``feedback/drafting_events`` (``recorder``, the only writer of the table).
The raw material of the golden set; a trader's rows are read back only through the read model."""
