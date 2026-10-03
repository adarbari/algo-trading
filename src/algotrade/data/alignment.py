"""Align multiple symbols onto a common timestamp index."""

from collections.abc import Mapping

import numpy as np

from algotrade.core.series import FIELDS, PriceSeries


def align(series: Mapping[str, PriceSeries]) -> dict[str, PriceSeries]:
    """Restrict every series to the timestamps present in *all* of them.

    Dropping (rather than forward-filling) keeps the engine honest: a strategy never
    trades on a bar that did not exist for one of its symbols.
    """
    if not series:
        return {}
    common = None
    for s in series.values():
        common = s.timestamps if common is None else np.intersect1d(common, s.timestamps)
    assert common is not None
    out: dict[str, PriceSeries] = {}
    for symbol, s in series.items():
        mask = np.isin(s.timestamps, common)
        out[symbol] = PriceSeries(
            instrument_id=symbol,
            timestamps=s.timestamps[mask].copy(),
            **{f: s.field(f)[mask].copy() for f in FIELDS},
        )
    return out
