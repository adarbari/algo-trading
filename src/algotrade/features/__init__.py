"""Features: versioned rollups computed from stored data (ADR 0007).

- ``framework/``  the ``Rollup`` declaration, column typing, input loading (through
                  ``algotrade.data``) and the per-session runner
- ``rollups/``    the definitions: pure ``compute(inputs, session, params) -> frame``
- ``registry``    every rollup by key (``<name>@v<N>``); the selection catalogue, the
                  ``rollups`` ingestion task and the fitness tests are built from it

Definitions never read or write storage. The ``rollups`` ingestion task stores their output
as ``rollups/instrument/<name>@v<N>``, one partition per session.
"""
