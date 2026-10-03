"""Which underlyings have options liquid enough to sell premium on (put side, call side).

Reads ``option_liquidity@v1``. The original pipeline called a pass ``process_further``;
here that is ``Decision.QUALIFIED``. Missing or failed data is ``UNKNOWN`` (fail closed).
"""

from algotrade.core.feature_view import FeatureView
from algotrade.strategies.screeners.base import Decision, Screener, ScreenRow

FEATURE = "rollups/instrument/option_liquidity@v1"
_TIER_SCORE = {"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.0}
_NO_MARKET = {"NO_CHAIN", "NO_STANDARD_SERIES", "NO_TARGET_EXPIRY"}


class ShortPremiumLiquidity(Screener):
    name = "short_premium_liquidity"
    requires = (FEATURE,)

    def screen(self, view: FeatureView) -> list[ScreenRow]:
        return [self._row(view, instrument) for instrument in view]

    def _row(self, view: FeatureView, instrument: str) -> ScreenRow:
        values = view.row(instrument)
        status = values.get("liq_status")
        if status is None or str(status).startswith(("FETCH_ERROR", "STALE")):
            reason = "no liquidity data" if status is None else str(status)
            return ScreenRow(instrument, Decision.UNKNOWN, reasons=(reason,), values=values)
        if status in _NO_MARKET:
            return ScreenRow(instrument, Decision.REJECT, 0.0, (str(status),), values)
        put, call = str(values.get("put_tier", "D")), str(values.get("call_tier", "D"))
        score = max(_TIER_SCORE.get(put, 0.0), _TIER_SCORE.get(call, 0.0))
        reasons = (f"put tier {put}", f"call tier {call}")
        ok = bool(values.get("short_put_ok")) or bool(values.get("short_call_ok"))
        decision = Decision.QUALIFIED if ok else Decision.LIQUIDITY_RISK
        return ScreenRow(instrument, decision, score, reasons, values)
