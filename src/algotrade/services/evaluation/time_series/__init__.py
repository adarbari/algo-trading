"""The time-series base of the edge evaluation (ADR 0073): an edge whose ``base`` is
``out_of_window`` times a few named instruments by a calendar window and is judged against the
same instrument's returns outside every window, not against a cross-section of names. Windows and
their tiled out-of-window stretches are ``periods.py``; the one module that reads outcomes (and the
bill rate, and turns a symbol into an id) is ``harness.py``; ``measures.py`` turns the two series
into the ``SliceMeasure`` rows the verdict already reads; ``random_windows.py`` draws the seeded
random window sets; ``evaluate.py`` runs one edge. ``cross_section/harness.py`` calls it and
wraps the result as an ``EdgeEvaluation``."""
