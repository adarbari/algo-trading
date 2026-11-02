"""One expiry and right of an underlying's session chain priced at the mid (ownership
``option-calculators``): each listed strike with a two-sided quote, its mid and our delta (the
grid's convention, ``band_pick.OurDeltas``: BSM with the session's rate and dividend yield, NaN
where no vol inverts) and open interest. The vendor bid and ask stop here: nothing downstream
sees them.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.rollups.positioning.chain_inputs import two_sided_mid
from algotrade.features.rollups.premium.band_pick import OurDeltas
from algotrade.quant.rates import DAYS_PER_YEAR
from algotrade.services.read.options.session_inputs import SessionInputs

PUT, CALL = "put", "call"
RIGHT_CODE = {PUT: "P", CALL: "C"}  # the chain's ``right`` values
COLUMNS = ["strike", "mid", "delta", "open_interest"]


def listed_expiries(inputs: SessionInputs, right: str, session: date) -> list[date]:
    """The expiries after ``session`` with a ``right`` listed, in order."""
    chain = inputs.chain
    found = chain.loc[chain["right"] == RIGHT_CODE[right], "expiry"]
    return sorted(e for e in set(found) if e > session)


def priced_pool(
    inputs: SessionInputs, deltas: OurDeltas, session: date, expiry: date, right: str
) -> pd.DataFrame:
    """``COLUMNS`` of the two-sided ``right`` contracts at ``expiry``, by strike (empty when
    none is two-sided)."""
    chain = inputs.chain
    pool = chain[(chain["right"] == RIGHT_CODE[right]) & (chain["expiry"] == expiry)]
    mid = two_sided_mid(pool["bid"], pool["ask"])
    keep = np.isfinite(mid)
    if not keep.any():
        return pd.DataFrame(columns=COLUMNS)
    strikes = pool["strike"].to_numpy(dtype=float)[keep]
    mids = mid[keep]
    t = (expiry - session).days / DAYS_PER_YEAR
    delta = deltas(mids, inputs.spot, strikes, t, right == CALL)
    out = pd.DataFrame(
        {
            "strike": strikes,
            "mid": mids,
            "delta": delta,
            "open_interest": pool["open_interest"].to_numpy()[keep],
        }
    )
    return out.sort_values("strike").drop_duplicates("strike").reset_index(drop=True)


def figures(pool: pd.DataFrame) -> list[tuple[float, float, float]]:
    """``(strike, mid, delta)`` of each row of a priced pool, in its order."""
    columns = (pool[c].to_numpy(dtype=float) for c in ("strike", "mid", "delta"))
    return [(float(k), float(m), float(d)) for k, m, d in zip(*columns, strict=True)]
