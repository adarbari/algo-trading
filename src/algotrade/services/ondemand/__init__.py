"""Use case: the API's on-request screen runs (ADR 0033): ``screens`` hosts a local job runner
for the ``screen`` job, holds the store's writer lock around each run and writes only result
tables and run records."""
