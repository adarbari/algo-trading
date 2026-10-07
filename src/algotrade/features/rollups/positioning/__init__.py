"""Options positioning and chain-shape feature groups (ADR 0031): flow, implied move, skew and
term structure, from the same chain inputs ``features/rollups/options`` reads. One module per
group (its documented ``FEATURES``, a pure ``compute`` and its ``GROUP`` declaration), plus
``chain_inputs.py``, the readings of the stored chain they share (spot, days to expiry,
two-sided quotes). The definitions are in ``docs/data/positioning.md``."""
