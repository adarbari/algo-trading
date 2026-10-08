"""Edge documents (ADR 0053 decision 1): the typed ``Edge`` of each ``config/site/edges/<id>.toml``
(a user may draft one under ``config/users/<id>/edges/``, layered per ADR 0015), validated fail
closed (``document.py``), loaded with its layers and checked against the screener and selection
presets that exist (``loading.py``), and rendered to ``docs/edges.md`` by ``make features-doc``
(``page.py``)."""
