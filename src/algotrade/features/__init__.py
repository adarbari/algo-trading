"""Features: named, typed, documented columns, computed in versioned feature groups from
stored data (ADRs 0007, 0023).

- ``framework/``  the ``Feature`` and ``FeatureGroup`` declarations, column typing, the
                  dependency graph and the per-session runner (inputs are asked of
                  ``algotrade.data.feature_inputs`` by table name)
- ``rollups/``    the groups: ``FEATURES`` + a pure ``compute(inputs, session, params)``
- ``registry``    every group by key (``<name>@v<N>``) and every feature; the selection
                  catalogue, the ``rollups`` ingestion task and the fitness tests use it
- ``catalogue``   the feature catalogue (``docs/data/features.md``, ``make features-doc``)

Groups never read or write storage. The ``rollups`` ingestion task stores their output as
``rollups/instrument/<name>@v<N>``, one partition per session.
"""
