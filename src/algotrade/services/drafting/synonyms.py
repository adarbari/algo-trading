"""Words a trader uses for what the catalogue's descriptions say another way, by field family
(data only; ``retrieval`` expands a sentence word to its whole family before matching). Add a
family when a held-out golden sentence misses a field because the words differ, never a
sentence: each family is a general vocabulary (a direction, a volatility word, a relative
measure), not a phrase."""

FAMILIES: tuple[tuple[str, ...], ...] = (
    ("rising", "increasing", "growing", "surging", "climbing", "building", "pick", "expanding"),
    ("falling", "declining", "dropping", "fading", "shrinking", "contracting"),
    ("cheap", "undervalued", "discount", "inexpensive"),
    ("expensive", "overvalued", "premium", "pricey"),
    ("volatile", "volatility", "swingy", "choppy", "realised", "realized"),
    ("earnings", "reaction", "report", "reported"),
    ("gap", "gapped", "gapping", "gaps"),
    ("outperform", "outperforming", "outperformed", "beat", "beating", "relative", "strength"),
    ("underperform", "underperforming", "lagging", "weaker", "relative", "strength"),
)
