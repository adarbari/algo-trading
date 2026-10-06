"""The regime episode scorecard on a synthetic store with two engineered episodes: a recession
bear the macro score saw 104 sessions early and the stress score 5 sessions after its peak,
and a shock the stress score caught only 20 sessions late; two false alarms (a STRESS blip, a
CRISIS blip) outside the windows; lagged UNRATE vintages; the probit fitted on month-end macro
rows. Dating, leads, alarms, acceptance and the probit are checked by hand, the text twice."""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algotrade.config.site.regime.episodes import Episode
from algotrade.config.user import UserContext
from algotrade.core.model.instruments import index_id, macro_id
from algotrade.core.time.calendar import sessions_between, sessions_ending
from algotrade.data import StoreReader
from algotrade.data.macro.series import TABLE as MACRO_SERIES
from algotrade.features.rollups.market import macro, regime
from algotrade.services.evaluation import regime_scorecard as sc
from algotrade.services.evaluation.regime_report import render
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import store, write_rows
from tests.helpers.stored_frames import stamped

START, END = date(2000, 6, 1), date(2005, 12, 30)
A_PEAK, A_TROUGH = date(2001, 6, 1), date(2002, 3, 1)  # -35%
B_PEAK, B_TROUGH = date(2004, 6, 1), date(2004, 9, 1)  # -25%
MACRO_ON = date(2001, 1, 2)  # 104 sessions before A's peak
STRESS_BLIP = date(2005, 6, 1)  # 3 STRESS sessions, outside every window
CRISIS_BLIP = date(2003, 3, 3)  # 4 CRISIS sessions, outside every window
SESSIONS = sessions_between(START, END)


def episode(key: str, peak: date, trough: date, depth: float, kind: str) -> Episode:
    recession = kind == "recession"
    nber = {"nber_start": date(2001, 3, 1), "nber_end": date(2001, 11, 1)} if recession else {}
    return Episode(key, peak, trough, depth, depth, recession, kind, "c", trough, "n", **nber)


EPISODES = (
    episode("a_recession", A_PEAK, A_TROUGH, -0.35, "recession"),
    episode("b_shock", B_PEAK, B_TROUGH, -0.25, "shock"),
)


def path() -> np.ndarray:
    """Log-linear legs between the engineered turning points."""
    knots = [(START, 100.0), (A_PEAK, 150.0), (A_TROUGH, 97.5), (B_PEAK, 160.0),
             (B_TROUGH, 120.0), (END, 170.0)]  # fmt: skip
    where = {d: i for i, d in enumerate(SESSIONS)}
    xs = [where[d] for d, _ in knots]
    return np.exp(np.interp(np.arange(len(SESSIONS)), xs, np.log([v for _, v in knots])))


def run_of(first: date, n: int) -> set[date]:
    i = SESSIONS.index(first)
    return set(SESSIONS[i : i + n])


def regime_rows() -> dict[date, dict[str, object]]:
    stress_a = {d for d in SESSIONS if sessions_between(A_PEAK, d)[5:] and d <= A_TROUGH}
    stress_b = {d for d in SESSIONS if len(sessions_between(B_PEAK, d)) > 21 and d <= B_TROUGH}
    stress = stress_a | stress_b | run_of(STRESS_BLIP, 3) | run_of(CRISIS_BLIP, 4)
    high_macro = {d for d in SESSIONS if MACRO_ON <= d <= A_TROUGH} | run_of(CRISIS_BLIP, 4)
    out = {}
    for d in SESSIONS:
        m, k = d in high_macro, d in stress
        label = ("CALM", "CAUTION", "STRESS", "CRISIS")[2 * k + m]
        scores = {"macro_risk": 60.0 if m else 10.0, "market_stress": 70.0 if k else 20.0}
        out[d] = {"instrument_id": "MKT:US", "label": label, "raw_label": label, **scores}
    return out


def macro_rows() -> dict[date, dict[str, object]]:
    """Month-end rows: the curve inverted before a bear, plus seeded noise so the classes
    overlap (no separation)."""
    noise = np.random.default_rng(3)
    month_ends = (
        pd.Series(SESSIONS).groupby(pd.to_datetime(pd.Series(SESSIONS)).dt.to_period("M")).max()
    )
    out = {}
    for d in month_ends:
        ahead = d + timedelta(days=183)
        bear = A_PEAK <= ahead <= A_TROUGH or B_PEAK <= ahead <= B_TROUGH
        curve = (-0.004 if bear else 0.01) + noise.normal(0, 0.008)
        cpi, hy = 0.025 + noise.normal(0, 0.005), 0.045 + noise.normal(0, 0.01)
        out[d] = {"instrument_id": "MKT:US", "curve_10y3m": curve, "cpi_yoy": cpi, "hy_oas": hy}
    return out


def write_levels(writer: StoreWriter) -> None:
    closes = path()
    rows = [
        {"instrument_id": index_id(k), "series": k, "obs_date": d, "vintage_date": d,
         "value": float(v * scale), "vintage_kind": "lagged"}
        for k, scale in (("SPX", 1.0), ("COMP", 20.0))
        for d, v in zip(SESSIONS, closes, strict=True)
    ]  # fmt: skip
    unrate = [
        {"instrument_id": macro_id("UNRATE"), "series": "UNRATE", "obs_date": d,
         "vintage_date": d + timedelta(days=40), "value": 4.2, "vintage_kind": kind}
        for d, kind in ((date(2000, 10, 1), "lagged"), (date(2003, 1, 1), "alfred"))
    ]  # fmt: skip
    writer.write_table(MACRO_SERIES, END, "macro-1", stamped(rows + unrate, END, "macro-1"))


CONFIGS = FileConfigStore(Path(__file__).resolve().parents[4] / "config")


def read_history(reader: StoreReader) -> sc.History:
    return sc.load_history(reader, CONFIGS, UserContext("local"))


@pytest.fixture(scope="module")
def reader() -> StoreReader:
    writer, reader = store()
    write_levels(writer)
    for d, row in regime_rows().items():
        write_rows(writer, regime.GROUP.table, d, [row])
    for d, row in macro_rows().items():
        write_rows(writer, macro.GROUP.table, d, [row])
    return reader


def test_both_rules_date_the_engineered_bears_on_both_indices(reader: StoreReader) -> None:
    matches = sc.agreement(read_history(reader), EPISODES)
    assert [(m.index, m.method, m.episode.key) for m in matches] == [
        (i, r, e) for i in ("SPX", "COMP") for r in ("PS", "LT") for e in ("a_recession", "b_shock")
    ]
    assert all(m.agree and m.peak_off == 0 and m.trough_off == 0 for m in matches)
    assert matches[0].dated is not None and matches[0].dated.depth == pytest.approx(-0.35)


def test_leads_paths_and_lagged_vintages(reader: StoreReader) -> None:
    a, b = sc.leads(read_history(reader), EPISODES, revised={"UNRATE"})
    assert a.macro == -len(sessions_between(MACRO_ON, A_PEAK)) + 1 == -104
    assert a.stress == 5 and a.lagged == ("UNRATE",)  # UNRATE's 2000 value: no ALFRED vintage
    assert b.macro is None and b.stress == 21 and b.lagged == ()
    crisis = len(sessions_between(A_PEAK, A_TROUGH)) - 5
    assert a.path == f"CAUTION {63 + 5} > CRISIS {crisis}"  # 63 before the peak, 5 after


def test_false_alarms_and_acceptance(reader: StoreReader) -> None:
    history = read_history(reader)
    alarms = sc.false_alarms(history, EPISODES)
    assert alarms is not None and alarms.by_decade == {2000: (7, 2, 1)}
    assert alarms.years == pytest.approx(len(SESSIONS) / 252)
    text = render(history, EPISODES, {"UNRATE"})
    macro_line = "PASS     macro_risk >= 50 at least 63 sessions before each recession bear's peak"
    stress_line = "FAIL     market_stress >= 50 within 15 sessions of each peak: 1 of 2"
    assert f"{macro_line}: 1 of 1" in text
    assert f"{stress_line} (failed: b_shock)" in text
    assert "PASS     fewer than one false CRISIS per 3 years: 1 over" in text
    assert "no data" not in text
    assert text == render(read_history(reader), EPISODES, {"UNRATE"})  # deterministic


def test_the_probit_is_fitted_on_month_end_rows(reader: StoreReader) -> None:
    result = sc.fit_probit(read_history(reader))
    assert result is not None and result.fit.converged
    assert result.fit.coef[1] < 0  # an inverted curve raises the bear probability
    assert result.hit_rate > 0.7 and 0 < result.base_rate < 0.5
    text = render(read_history(reader), EPISODES, ())
    assert '["market_bear_probit@v1"]' in text and "fitted = true" in text


def test_without_data_every_section_says_so() -> None:
    _, empty = store()
    text = render(read_history(empty), EPISODES, ())
    assert text.count(sc.NO_DATA) == 5 and sc.BACKFILL in text
    assert sc.offset(date(2004, 6, 1), date(2004, 5, 28)) == -1
    assert sessions_ending(date(2004, 6, 1), 2)[0] == date(2004, 5, 28)
