"""The feature-group framework: the ``Feature`` and ``FeatureGroup`` declarations, column
typing, the dependency graph between groups, and the runner that computes groups per
session (one session or a backfilled range). Inputs are asked of ``algotrade.data`` by table
name (``data.feature_inputs``); the framework never reads storage or a domain reader."""
