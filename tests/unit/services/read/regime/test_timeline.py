"""``load_episode_signals`` (ADR 0047): per indicator and for the gate, the first session of the
first ON run overlapping the window and the first session after it that was not ON, from each
session's own stored verdict, in sessions from the peak (negative: before) and from the trough;
what a session did not yet know (rows after ``ctx.session``) is never read, a null verdict is
neither a flag nor a clear, and a signal with no stored verdict is unknown, never
``never_fired``."""

from datetime import date
from typing import Any

from algotrade.services.read.context import ReadContext
from algotrade.services.read.regime.timeline import (
    GATE,
    EpisodeSignals,
    SignalKind,
    SignalState,
    SignalTiming,
    load_episode_signals,
)
from algotrade.services.read.values import UnknownCode
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with
from tests.unit.services.read.regime.conftest import with_regime, write_indicators, write_regime

SEP17, SEP18, SEP21, SEP22, SEP23 = (date(2026, 9, d) for d in (17, 18, 21, 22, 23))
SEP24, SEP25, SEP28, SEP29 = (date(2026, 9, d) for d in (24, 25, 28, 29))
PEAK, TROUGH = SEP22, SEP28  # lookback 3 sessions: the window starts 17 Sep
ODD_PEAK = date(2026, 8, 3)  # an episode no row falls in
EPISODE: dict[str, Any] = {
    "key": "ep",
    "name": "Test drawdown",
    "peak": PEAK,
    "trough": TROUGH,
    "spx_drawdown": -0.2,
    "nasdaq_drawdown": -0.25,
    "recession": False,
    "kind": "shock",
    "cause": "A test.",
    "known_from": TROUGH,
    "notes": "A test.",
}
DOC = {
    "episode": [
        EPISODE,
        {**EPISODE, "key": "empty", "peak": ODD_PEAK, "trough": date(2026, 8, 10),
         "known_from": date(2026, 8, 10)},
        {**EPISODE, "key": "late", "peak": D1, "trough": date(2026, 10, 2),
         "known_from": date(2026, 10, 2)},
    ],
    "timeline": {"lookback_sessions": 3, "clear_horizon_sessions": 4,
                 "gate_labels": ["STRESS", "CRISIS"]},
}  # fmt: skip


def _write(rows: dict[date, dict[str, Any]]) -> Any:
    def write(writer: Any) -> None:
        for day, values in rows.items():
            if "label" in values:
                write_regime(writer, day, values["label"])
            verdicts = {k: v for k, v in values.items() if k != "label"}
            if verdicts:
                write_indicators(writer, day, **verdicts)

    return write


def signals(rows: dict[date, dict[str, Any]], key: str = "ep", day: date | None = None) -> Any:
    ctx: ReadContext = with_regime(
        context(store_with(_write(rows)), day), docs={("site", "regime", "episodes"): DOC}
    )
    return load_episode_signals(ctx, key)


def timing(found: EpisodeSignals, key: str) -> SignalTiming:
    return next(t for t in found.indicators if t.indicator == key)


ROWS: dict[date, dict[str, Any]] = {
    SEP17: {"label": "CALM", "curve_on": False, "trend_on": False},
    SEP18: {"label": "CALM", "curve_on": False, "trend_on": False},
    SEP21: {"label": "CALM", "curve_on": True, "trend_on": False},
    SEP22: {"label": "CALM", "curve_on": True, "trend_on": False},
    SEP23: {"label": "CALM", "curve_on": None, "trend_on": False},
    SEP24: {"label": "CALM", "curve_on": True, "trend_on": False},
    SEP25: {"label": "STRESS", "curve_on": False, "trend_on": False},
    SEP28: {"label": "CRISIS", "curve_on": False, "trend_on": False},
    SEP29: {"label": "CAUTION", "curve_on": True, "trend_on": False},
}


def test_flagged_and_cleared_days_count_sessions_from_the_peak_and_the_trough() -> None:
    found = signals(ROWS)
    curve = timing(found, "curve")
    # on from 21 Sep (one session before the peak); the null on 23 Sep neither clears nor
    # flags; first not ON on 25 Sep (3 sessions after the peak); 5 sessions before the trough
    assert (curve.kind, curve.flagged_day, curve.cleared_day) == (SignalKind.SLOW, -1, 3)
    assert curve.state is SignalState.LED and curve.first_known_day is None  # rows from the start
    assert (curve.flagged_day_from_trough, curve.never_fired, curve.unknown_reason) == (
        -5,
        False,
        None,
    )
    assert timing(found, "trend").kind is SignalKind.FAST


def test_the_gate_is_the_regime_label_in_the_gate_labels() -> None:
    gate = signals(ROWS).gate
    # STRESS on 25 Sep (3 after the peak), CRISIS keeps it shut, CAUTION on 29 Sep opens it
    assert (gate.indicator, gate.kind) == (GATE, SignalKind.GATE)
    assert (gate.flagged_day, gate.cleared_day, gate.flagged_day_from_trough) == (3, 5, -1)


def test_a_signal_false_on_every_stored_session_never_fired() -> None:
    trend = timing(signals(ROWS), "trend")
    assert trend.never_fired and trend.unknown_reason is None
    assert trend.state is SignalState.NEVER_FIRED
    assert (trend.flagged_day, trend.cleared_day, trend.flagged_day_from_trough) == (None,) * 3


def test_rows_after_the_session_are_ignored_and_a_run_still_on_has_no_clear() -> None:
    rows = {
        **ROWS,
        SEP29: {"label": "CRISIS", "curve_on": True, "trend_on": False},
        D0: {"label": "CRISIS", "curve_on": True, "trend_on": False},
        D1: {"label": "CAUTION", "curve_on": False, "trend_on": True},
    }
    seen = {**rows, SEP25: {"label": "STRESS", "curve_on": True, "trend_on": False},
            SEP28: {"label": "CRISIS", "curve_on": True, "trend_on": False}}  # fmt: skip
    at_d0 = signals(seen, day=D0)
    # still ON at the session (30 Sep): no clear; the 1 Oct rows (after the session) are unseen
    curve = timing(at_d0, "curve")
    assert (curve.flagged_day, curve.cleared_day) == (-1, None)
    assert at_d0.gate.cleared_day is None
    assert timing(at_d0, "trend").never_fired  # its 1 Oct ON is after the session
    # the same store read as of 1 Oct: the trend turned ON only after the trough
    late = timing(signals(rows, day=D1), "trend")
    # LATE: the first ON session after the trough, 7 sessions after the peak, 3 after the trough
    assert (late.state, late.flagged_day, late.flagged_day_from_trough) == (SignalState.LATE, 7, 3)
    assert (late.never_fired, late.unknown_reason) == (False, None)


def test_no_stored_verdict_in_the_window_is_unknown_never_never_fired() -> None:
    found = signals(ROWS, key="empty")
    for t in (found.gate, timing(found, "curve"), timing(found, "trend")):
        assert (t.never_fired, t.flagged_day, t.cleared_day) == (False, None, None)
        assert t.unknown_reason is not None and t.unknown_reason.code is UnknownCode.NO_ROW


def test_a_card_without_a_verdict_column_is_not_in_the_catalogue() -> None:
    found = signals(ROWS)
    for key in ("hy", "vix"):  # no ``_on`` column in the test groups
        t = timing(found, key)
        assert (
            t.unknown_reason is not None and t.unknown_reason.code is UnknownCode.NOT_IN_CATALOGUE
        )
        assert not t.never_fired
    assert [t.indicator for t in found.indicators] == ["curve", "hy", "trend", "vix"]


def test_an_unknown_or_an_unlisted_episode_is_none() -> None:
    assert signals(ROWS, key="nope") is None
    assert signals(ROWS, key="late", day=D1) is None  # its trough (2 Oct) has not come


def test_an_unknown_label_neither_shuts_nor_opens_the_gate() -> None:
    rows = {
        SEP24: {"label": "CALM"},
        SEP25: {"label": "STRESS"},
        SEP28: {"label": "SUNNY"},  # not a regime label: unknown, so the gate stays shut
        SEP29: {"label": "CAUTION"},
    }
    gate = signals(rows).gate
    assert (gate.state, gate.flagged_day, gate.cleared_day) == (SignalState.LED, 3, 5)


def test_verdicts_stored_only_after_the_trough_are_unknown_not_never_fired() -> None:
    found = signals({SEP29: {"label": "CALM", "trend_on": False}})
    for t in (found.gate, timing(found, "trend")):
        assert (t.state, t.never_fired) == (SignalState.UNKNOWN, False)
        assert t.unknown_reason is not None and t.unknown_reason.code is UnknownCode.NO_ROW


def test_first_known_day_says_when_stored_verdicts_start_mid_window() -> None:
    rows = {d: v for d, v in ROWS.items() if d >= SEP21}
    curve = timing(signals(rows), "curve")
    assert (curve.flagged_day, curve.first_known_day) == (-1, -1)  # on from the first stored day
