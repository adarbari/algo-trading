"""Expression features: a small, safe, typed formula language over features (ADR 0023 step 3).

Definitions live in ``config/site/features/*.toml`` (loaded by ``config/site/settings.py``).
A formula is parsed (``lexer``, ``parser`` -> ``nodes``), type checked against the catalogue
(``checker``) and evaluated vectorised over a frame of stored feature columns
(``evaluator``, ``functions``); nothing is ever passed to Python ``eval``. ``definitions``
turns the TOML definitions into ``Feature``s with a dependency graph, ``frame`` joins stored
group rows into evaluation columns, and ``feature_set`` puts the code groups, the expression
features and the materialised expression groups into one catalogue.

Pure: numpy, pandas, ``core`` and the feature declarations only (no storage, data or
services; import-linter).
"""
